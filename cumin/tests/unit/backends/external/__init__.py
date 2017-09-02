"""External backends package for testing."""
import pyparsing as pp

from cumin import nodeset
from cumin.backends import BaseQuery


def grammar():
    """Define the query grammar for the external backend used for testing."""
    # Hosts selection: clustershell (,!&^[]) syntax is allowed: host10[10-42].domain
    hosts = pp.Word(pp.alphanums + '-_.,!&^[]')('hosts')

    # Final grammar, see the docstring for its BNF based on the tokens defined above
    # Groups are used to split the parsed results for an easy access
    full_grammar = pp.Forward()
    full_grammar << pp.Group(hosts) + pp.ZeroOrMore(pp.Group(hosts))  # pylint: disable=expression-not-assigned

    return full_grammar


class ExternalBackendQuery(BaseQuery):
    """External backend test query class."""

    grammar = grammar()
    """:py:class:`pyparsing.ParserElement`: load the grammar parser only once in a singleton-like way."""

    def __init__(self, config):
        """Query constructor for the test external backend.

        :Parameters:
            according to parent :py:meth:`cumin.backends.BaseQuery.__init__`.

        """
        super().__init__(config)
        self.hosts = nodeset()

    def _execute(self):
        """Concrete implementation of parent abstract method.

        :Parameters:
            according to parent :py:meth:`cumin.backends.BaseQuery._execute`.

        Returns:
            ClusterShell.NodeSet.NodeSet: with the FQDNs of the matching hosts.

        """
        return self.hosts

    def _parse_token(self, token):
        """Concrete implementation of parent abstract method.

        :Parameters:
            according to parent :py:meth:`cumin.backends.BaseQuery._parse_token`.
        """
        if isinstance(token, str):
            return

        token_dict = token.asDict()
        self.hosts |= nodeset(token_dict['hosts'])
