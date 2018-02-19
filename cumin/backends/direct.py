"""Direct backend."""
import pyparsing as pp

from cumin import nodeset_fromlist
from cumin.backends import BaseQueryAggregator, InvalidQueryError


def grammar():
    """Define the query grammar.

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
    hosts = (~(boolean) + pp.Word(pp.alphanums + '-_.,!&^[]'))('hosts')

    # Final grammar, see the docstring for its BNF based on the tokens defined above
    # Groups are used to split the parsed results for an easy access
    full_grammar = pp.Forward()
    item = hosts | lpar + full_grammar + rpar
    full_grammar << pp.Group(item) + pp.ZeroOrMore(pp.Group(boolean + item))  # pylint: disable=expression-not-assigned

    return full_grammar


class DirectQuery(BaseQueryAggregator):
    """DirectQuery query builder.

    The `direct` backend allow to use Cumin without any external dependency for the hosts selection.
    It allow to write arbitrarily complex queries with subgroups and boolean operators, but each item must be either the
    hostname itself, or the using host expansion using the powerful :py:class:`ClusterShell.NodeSet.NodeSet` syntax.

    The typical usage for the `direct` backend is as a reliable alternative in cases in which the primary host
    selection mechanism is not working and also for testing the transports without any external backend dependency.

    Some query examples:

    * Simple selection: ``host1.domain``
    * ClusterShell syntax for hosts expansion: ``host10[10-42].domain,host2010.other-domain``
    * A complex selection:
      ``host100[1-5].domain or (host10[30-40].domain and (host10[10-42].domain and not host33.domain))``
    """

    grammar = grammar()
    """:py:class:`pyparsing.ParserElement`: load the grammar parser only once in a singleton-like way."""

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
            element['hosts'] = nodeset_fromlist(token_dict['hosts'])
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


GRAMMAR_PREFIX = 'D'
""":py:class:`str`: the prefix associate to this grammar, to register this backend into the general grammar.
Required by the backend auto-loader in :py:meth:`cumin.grammar.get_registered_backends`."""

query_class = DirectQuery  # pylint: disable=invalid-name
"""Required by the backend auto-loader in :py:meth:`cumin.grammar.get_registered_backends`."""
