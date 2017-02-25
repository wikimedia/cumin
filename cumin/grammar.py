"""Query grammar definition"""

import pyparsing as pp

# Available categories
categories = (
    'F',  # Fact
    'R',  # Resource
)
# Available operators
operators = ('=', '!=', '>=', '<=', '<', '>', '~')


def _grammar():
    """ Define the query grammar

        Some query examples:
        - All hosts: *
        - Hosts globbing: host10*
        - ClusterShell syntax for hosts expansion: host10[10-42].domain,host2010.other-domain
        - Category based key-value selection: F:key = value
        - A complex selection:
          host10[10-42].*.domain or (not F:key1 = value1 and host10*) or (F:key2 > value2 and F:key3 ~ '[v]alue[0-9]+')

        Backus-Naur form (BNF) of the grammar:
                  <query> ::= <item> | <item> <and_or> <query>
                   <item> ::= [<neg>] <query-token> | [<neg>] "(" <query> ")"
            <query-token> ::= <token> | <hosts>
                  <token> ::= <category>:<key> [<operator> <value>]

        Given that the pyparsing library defines the grammar in a BNF-like style, for the details of the tokens not
        specified above check directly the code.
    """

    # Boolean operators
    and_or = (pp.Keyword('and', caseless=True) | pp.Keyword('or', caseless=True))('bool')
    neg = pp.Keyword('not', caseless=True)('neg')  # 'neg' is used to allow the use of dot notation, 'not' is reserved

    operator = pp.oneOf(operators, caseless=True)('operator')  # Comparison operators
    quoted_string = pp.quotedString.addParseAction(pp.removeQuotes)  # Both single and double quotes are allowed

    # Parentheses
    lpar = pp.Literal('(').suppress()
    rpar = pp.Literal(')').suppress()

    # Hosts selection: glob (*) and clustershell (,!&^[]) syntaxes are allowed:
    # i.e. host10[10-42].*.domain
    hosts = quoted_string | (~(and_or | neg) + pp.Word(pp.alphanums + '-_.*,!&^[]'))

    # Key-value token for allowed categories using the available comparison operators
    # i.e. F:key = value
    category = pp.oneOf(categories, caseless=True)('category')
    key = pp.Word(pp.alphanums + '-_.%@:')('key')
    selector = pp.Combine(category + ':' + key)  # i.e. F:key
    # All printables characters except the parentheses that are part of the grammar
    all_but_par = ''.join([c for c in pp.printables if c not in ('(', ')')])
    value = (quoted_string | pp.Word(all_but_par))('value')
    token = selector + pp.Optional(operator + value)

    # Final grammar, see the docstring for it's BNF based on the tokens defined above
    # Groups are used to split the parsed results for an easy access
    grammar = pp.Forward()
    item = pp.Group(pp.Optional(neg) + (token | hosts('hosts'))) | pp.Group(
        pp.Optional(neg) + lpar + grammar + rpar)
    grammar << item + pp.ZeroOrMore(pp.Group(and_or) + grammar)

    return grammar


grammar = _grammar()
