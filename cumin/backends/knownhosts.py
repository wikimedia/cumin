"""Known hosts backend."""
import ipaddress

import pyparsing as pp

from ClusterShell.NodeSet import NodeSet
from ClusterShell.NodeUtils import GroupResolver, GroupSource

from cumin.backends import BaseQueryAggregator, InvalidQueryError


def grammar():
    """Define the query grammar.

    Some query examples:

    * Simple selection: ``host1.domain``
    * ClusterShell syntax for hosts expansion: ``host10[10-42].domain,host2010.other-domain``
    * ClusterShell syntax for hosts globbing: ``host10[10-42]*``
    * A complex selection: ``host100[1-5]* or (host10[30-40].domain and (host10[10-42].domain and not host33.domain))``

    Backus-Naur form (BNF) of the grammar::

        <grammar> ::= <item> | <item> <boolean> <grammar>
           <item> ::= <hosts> | "(" <grammar> ")"
        <boolean> ::= "and not" | "and" | "xor" | "or"

    Given that the pyparsing library defines the grammar in a BNF-like style, for the details of the tokens not
    specified above check directly the source code.

    Returns:
        pyparsing.ParserElement: the grammar parser.

    """
    # Boolean operators
    boolean = (pp.CaselessKeyword('and not').leaveWhitespace() | pp.CaselessKeyword('and') |
               pp.CaselessKeyword('xor') | pp.CaselessKeyword('or'))('bool')

    # Parentheses
    lpar = pp.Literal('(')('open_subgroup')
    rpar = pp.Literal(')')('close_subgroup')

    # Hosts selection: clustershell (,!&^[]) syntax is allowed: host10[10-42].domain
    hosts = (~(boolean) + pp.Word(pp.alphanums + '-_.,!&^[]*?'))('hosts')

    # Final grammar, see the docstring for its BNF based on the tokens defined above
    # Groups are used to split the parsed results for an easy access
    full_grammar = pp.Forward()
    item = hosts | lpar + full_grammar + rpar
    full_grammar << pp.Group(item) + pp.ZeroOrMore(pp.Group(boolean + item))  # pylint: disable=expression-not-assigned

    return full_grammar


class KnownHostsLineError(InvalidQueryError):
    """Custom exception class for invalid lines in SSH known hosts files."""


class KnownHostsSkippedLineError(InvalidQueryError):
    """Custom exception class for skipped lines in SSH known hosts files."""


class KnownHostsQuery(BaseQueryAggregator):
    """KnownHostsQuery query builder.

    The ``knownhosts`` backend allow to use Cumin taking advantage of existing SSH known hosts files that are not
    hashed.
    It allow to write arbitrarily complex queries with subgroups and boolean operators, but each item must be either
    the hostname itself, or using host expansion with the powerful :py:class:`ClusterShell.NodeSet.NodeSet` syntax.

    The typical use case for the ``knownhosts`` backend is when the known hosts file(s) are generated and kept updated
    by some external configuration manager or tool that is not yet supported as a backend for Cumin. It can also work
    as a fallback backend in case the primary backend is unavailable but the known hosts file(s) are still up to date.
    """

    grammar = grammar()
    """:py:class:`pyparsing.ParserElement`: load the grammar parser only once in a singleton-like way."""

    def __init__(self, config):
        """Known hosts query constructor, initialize the known hosts.

        :Parameters:
            according to parent :py:meth:`cumin.backends.BaseQuery.__init__`.
        """
        super().__init__(config)

        self.known_hosts = set()
        self.resolver = None

    def _build(self, query_string):
        """Override parent method to lazy-loading the known hosts if needed.

        :Parameters:
            according to parent :py:meth:`cumin.backends.BaseQuery._build`.
        """
        if not self.known_hosts:
            self._load_known_hosts()

        if self.resolver is None:
            source = GroupSource('all', allgroups='\n'.join(self.known_hosts))
            self.resolver = GroupResolver(default_source=source)

        super()._build(query_string)

    def _execute(self):
        """Override parent method to ensure to return only existing hosts.

        :Parameters:
            according to parent :py:meth:`cumin.backends.BaseQuery._execute`.
        """
        hosts = super()._execute()
        return hosts & NodeSet('*', resolver=self.resolver)

    def _parse_token(self, token):
        """Concrete implementation of parent abstract method.

        :Parameters:
            according to parent :py:meth:`cumin.backends.BaseQueryAggregator._parse_token`.
        """
        if not isinstance(token, pp.ParseResults):  # pragma: no cover - this should never happen
            raise InvalidQueryError('Expecting ParseResults object, got {type}: {token}'.format(
                type=type(token), token=token))

        token_dict = token.asDict()
        self.logger.trace('Token is: %s | %s', token_dict, token)

        if 'hosts' in token_dict:
            element = self._get_stack_element()
            element['hosts'] = NodeSet.fromlist(token_dict['hosts'], resolver=self.resolver)
            if 'bool' in token_dict:
                element['bool'] = token_dict['bool']
            self.stack_pointer['children'].append(element)
        elif 'open_subgroup' in token_dict and 'close_subgroup' in token_dict:
            self._open_subgroup()
            if 'bool' in token_dict:
                self.stack_pointer['bool'] = token_dict['bool']
            for subtoken in token:
                if isinstance(subtoken, str):  # Grammar literals, boolean operators and parentheses
                    continue
                self._parse_token(subtoken)
            self._close_subgroup()
        else:  # pragma: no cover - this should never happen
            raise InvalidQueryError('Got unexpected token: {token}'.format(token=token))

    def _load_known_hosts(self):
        """Load all known hosts file listed in the configuration."""
        config = self.config.get('knownhosts', {})
        known_hosts_filenames = config.get('files', [])

        for filename in known_hosts_filenames:
            hosts = set()
            with open(filename, 'r') as known_hosts_file:
                for lineno, line in enumerate(known_hosts_file, 1):
                    try:
                        found, skipped = KnownHostsQuery.parse_known_hosts_line(line)
                        if skipped:
                            self.logger.trace("Skipped patterns at line %d in known hosts file '%s': %s",
                                              lineno, filename, ', '.join(skipped))
                        hosts.update(found)
                    except KnownHostsLineError as e:
                        self.logger.warning("Discarded invalid line %d (%s) in known hosts file '%s': %s",
                                            lineno, e, filename, line)
                    except KnownHostsSkippedLineError as e:
                        self.logger.trace("Skipped %s line %d in known hosts file '%s': %s", e, lineno, filename, line)

            self.logger.debug("Loaded %d hosts from '%s'", len(hosts), filename)
            self.known_hosts.update(hosts)

    @staticmethod
    def parse_known_hosts_line(line):
        """Parse an SSH known hosts formatted line and extract the valid hostnames.

        See the ``SSH_KNOWN_HOSTS FILE FORMAT` in ``man sshd`` for the details of the file format.

        Arguments:
            line (str): the line to parse.

        Raises:
            KnownHostsSkippedLineError: if the line is skipped.
            KnownHostsLineError: if unable to parse the line.

        Returns:
            set: a set with the hostnames found in the given line.

        """
        line = line.strip()
        if not line:
            raise KnownHostsSkippedLineError('empty line')

        if line[0] == '#':
            raise KnownHostsSkippedLineError('comment')

        if line[0] == '|':
            raise KnownHostsSkippedLineError('hashed')

        fields = line.split()
        if len(fields) < 3:
            raise KnownHostsLineError('not enough fields')

        if line[0] == '@':
            if len(fields) < 4:
                raise KnownHostsLineError('not enough fields')

            if fields[0] == '@cert-authority':
                line_hosts = fields[1]
            elif fields[0] == '@revoked':
                raise KnownHostsSkippedLineError('revoked')
            else:
                raise KnownHostsLineError('unknown marker')
        else:
            line_hosts = fields[0]

        return KnownHostsQuery.parse_line_hosts(line_hosts)

    @staticmethod
    def parse_line_hosts(line_hosts):
        """Parse a comma-separated hostnamed from an SSH known hosts formatted line and extract the valid hostnames.

        Arguments:
            line_hosts (str): the hostnames to parse.

        Returns:
            tuple: a tuple with two sets, the hostnames found in the given line and the hostnames skipped.

        """
        hosts = set()
        skipped = set()
        for host in line_hosts.split(','):
            if not host:
                continue

            if host[0] == '!':
                host = host[1:]

            if host[0] == '[':
                host = host[1:].split(']')[0]

            if '*' in host or '?' in host:
                skipped.add(host)
            else:
                try:
                    ipaddress.ip_address(host)
                    skipped.add(host)
                except ValueError:
                    hosts.add(host)  # Add hostnames, skip IP addresses

        return hosts, skipped


GRAMMAR_PREFIX = 'K'
""":py:class:`str`: the prefix associate to this grammar, to register this backend into the general grammar.
Required by the backend auto-loader in :py:meth:`cumin.grammar.get_registered_backends`."""

query_class = KnownHostsQuery  # pylint: disable=invalid-name
"""Required by the backend auto-loader in :py:meth:`cumin.grammar.get_registered_backends`."""
