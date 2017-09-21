# pylint: skip-file
# See https://github.com/PyCQA/astroid/issues/437
"""PuppetDB backend."""
from string import capwords

import pyparsing as pp
import requests

from ClusterShell.NodeSet import NodeSet
from requests.packages import urllib3

from cumin.backends import BaseQuery, InvalidQueryError


# Available categories
CATEGORIES = (
    'F',  # Fact
    'R',  # Resource
)

# Available operators
OPERATORS = ('=', '>=', '<=', '<', '>', '~')


def grammar():
    """Define the query grammar.

    Some query examples:
    - All hosts: `*`
    - Hosts globbing: `host10*`
    - ClusterShell's NodeSet syntax (see https://clustershell.readthedocs.io/en/latest/api/NodeSet.html) for hosts
      expansion: `host10[10-42].domain`
    - Category based key-value selection:
      - `R:Resource::Name`: query all the hosts that have a resource of type `Resource::Name`.
      - `R:Resource::Name = 'resource-title'`: query all the hosts that have a resource of type `Resource::Name` whose
        title is `resource-title`. For example `R:Class = MyModule::MyClass`.
      - `R:Resource::Name@field = 'some-value'`: query all the hosts that have a resource of type `Resource::Name`
        whose field `field` has the value `some-value`. The valid fields are: `tag`, `certname`, `type`, `title`,
        `exported`, `file`, `line`. The previous syntax is a shortcut for this one with the field `title`.
      - `R:Resource::Name%param = 'some-value'`: query all the hosts that have a resource of type `Resource::Name`
        whose parameter `param` has the value `some-value`.
      - Mixed facts/resources queries are not supported, but the same result can be achieved by the main grammar using
        multiple subqueries.
    - A complex selection for facts:
      `host10[10-42].*.domain or (not F:key1 = value1 and host10*) or (F:key2 > value2 and F:key3 ~ '^value[0-9]+')`

    Backus-Naur form (BNF) of the grammar:
            <grammar> ::= <item> | <item> <and_or> <grammar>
               <item> ::= [<neg>] <query-token> | [<neg>] "(" <grammar> ")"
        <query-token> ::= <token> | <hosts>
              <token> ::= <category>:<key> [<operator> <value>]

    Given that the pyparsing library defines the grammar in a BNF-like style, for the details of the tokens not
    specified above check directly the code.
    """
    # Boolean operators
    and_or = (pp.CaselessKeyword('and') | pp.CaselessKeyword('or'))('bool')
    # 'neg' is used as label to allow the use of dot notation, 'not' is a reserved word in Python
    neg = pp.CaselessKeyword('not')('neg')

    operator = pp.oneOf(OPERATORS, caseless=True)('operator')  # Comparison operators
    quoted_string = pp.quotedString.copy().addParseAction(pp.removeQuotes)  # Both single and double quotes are allowed

    # Parentheses
    lpar = pp.Literal('(')('open_subgroup')
    rpar = pp.Literal(')')('close_subgroup')

    # Hosts selection: glob (*) and clustershell (,!&^[]) syntaxes are allowed:
    # i.e. host10[10-42].*.domain
    hosts = quoted_string | (~(and_or | neg) + pp.Word(pp.alphanums + '-_.*,!&^[]'))

    # Key-value token for allowed categories using the available comparison operators
    # i.e. F:key = value
    category = pp.oneOf(CATEGORIES, caseless=True)('category')
    key = pp.Word(pp.alphanums + '-_.%@:')('key')
    selector = pp.Combine(category + ':' + key)  # i.e. F:key
    # All printables characters except the parentheses that are part of this or the global grammar
    all_but_par = ''.join([c for c in pp.printables if c not in ('(', ')', '{', '}')])
    value = (quoted_string | pp.Word(all_but_par))('value')
    token = selector + pp.Optional(operator + value)

    # Final grammar, see the docstring for its BNF based on the tokens defined above
    # Groups are used to split the parsed results for an easy access
    full_grammar = pp.Forward()
    item = pp.Group(pp.Optional(neg) + (token | hosts('hosts'))) | pp.Group(
        pp.Optional(neg) + lpar + full_grammar + rpar)
    full_grammar << item + pp.ZeroOrMore(pp.Group(and_or) + full_grammar)  # pylint: disable=expression-not-assigned

    return full_grammar


class PuppetDBQuery(BaseQuery):
    """PuppetDB query builder.

    The 'puppetdb' backend allow to use an existing PuppetDB instance for the hosts selection.
    At the moment only PuppetDB v3 API are implemented.
    """

    base_url_template = 'https://{host}:{port}/v3/'
    endpoints = {'R': 'resources', 'F': 'nodes'}
    hosts_keys = {'R': 'certname', 'F': 'name'}
    grammar = grammar()

    def __init__(self, config, logger=None):
        """Query constructor for the PuppetDB backend.

        Arguments: according to BaseQuery interface
        """
        super(PuppetDBQuery, self).__init__(config, logger=logger)
        self.grouped_tokens = None
        self.current_group = self.grouped_tokens
        self._category = None
        puppetdb_config = self.config.get('puppetdb', {})
        self.url = self.base_url_template.format(
            host=puppetdb_config.get('host', 'localhost'),
            port=puppetdb_config.get('port', 443))

        for exception in puppetdb_config.get('urllib3_disable_warnings', []):
            urllib3.disable_warnings(category=getattr(urllib3.exceptions, exception))

    @property
    def category(self):
        """Getter for the property category with a default value."""
        return self._category or 'F'

    @category.setter
    def category(self, value):
        """Setter for the property category with validation.

        Arguments:
        value -- the value to set the category to
        """
        if value not in self.endpoints:
            raise InvalidQueryError("Invalid value '{category}' for category property".format(category=value))
        if self._category is not None and value != self._category:
            raise InvalidQueryError('Mixed F: and R: queries are currently not supported')

        self._category = value

    def _open_subgroup(self):
        """Handle subgroup opening."""
        token = PuppetDBQuery._get_grouped_tokens()
        token['parent'] = self.current_group
        self.current_group['tokens'].append(token)
        self.current_group = token

    def _close_subgroup(self):
        """Handle subgroup closing."""
        self.current_group = self.current_group['parent']

    @staticmethod
    def _get_grouped_tokens():
        """Return an empty grouped tokens structure."""
        return {'parent': None, 'bool': None, 'tokens': []}

    def _build(self, query_string):
        """Override parent class _build method to reset tokens and add logging."""
        self.grouped_tokens = PuppetDBQuery._get_grouped_tokens()
        self.current_group = self.grouped_tokens
        super(PuppetDBQuery, self)._build(query_string)
        self.logger.trace('Query tokens: {tokens}'.format(tokens=self.grouped_tokens))

    def _execute(self):
        """Required by BaseQuery."""
        query = self._get_query_string(group=self.grouped_tokens).format(host_key=self.hosts_keys[self.category])
        hosts = self._api_call(query, self.endpoints[self.category])
        unique_hosts = NodeSet.fromlist([host[self.hosts_keys[self.category]] for host in hosts])
        self.logger.debug("Queried puppetdb for '{query}', got '{num}' results.".format(
            query=query, num=len(unique_hosts)))

        return unique_hosts

    def _add_category(self, category, key, value=None, operator='=', neg=False):
        """Add a category token to the query 'F:key = value'.

        Arguments:
        category -- the category of the token, one of CATEGORIES excluding the alias one.
        key      -- the key for this category
        value    -- the value to match, if not specified the key itself will be matched [optional, default: None]
        operator -- the comparison operator to use, one of cumin.grammar.OPERATORS [optional: default: =]
        neg      -- whether the token must be negated [optional, default: False]
        """
        self.category = category
        if operator == '~':
            value = value.replace(r'\\', r'\\\\')  # Required by PuppetDB API

        if category == 'R':
            query = self._get_resource_query(key, value, operator)
        elif category == 'F':
            query = '["{op}", ["fact", "{key}"], "{val}"]'.format(op=operator, key=key, val=value)
        else:  # pragma: no cover - this should never happen
            raise InvalidQueryError(
                "Got invalid category '{category}', one of F|R expected".format(category=category))

        if neg:
            query = '["not", {query}]'.format(query=query)

        self.current_group['tokens'].append(query)

    def _add_hosts(self, hosts, neg=False):
        """Add a list of hosts to the query.

        Arguments:
        hosts -- a list of hosts to match
        neg   -- whether the token must be negated [optional, default: False]
        """
        if not hosts:
            return

        hosts_tokens = []
        for host in hosts:
            operator = '='
            # Convert a glob expansion into a regex
            if '*' in host:
                operator = '~'
                host = r'^' + host.replace('.', r'\\.').replace('*', '.*') + r'$'

            hosts_tokens.append('["{op}", "{{host_key}}", "{host}"]'.format(op=operator, host=host))

        query = '["or", {hosts}]'.format(hosts=', '.join(hosts_tokens))
        if neg:
            query = '["not", {query}]'.format(query=query)

        self.current_group['tokens'].append(query)

    def _parse_token(self, token):
        """Required by BaseQuery."""
        if isinstance(token, str):
            return

        token_dict = token.asDict()

        # Based on the token type build the corresponding query object
        if 'open_subgroup' in token_dict:
            self._open_subgroup()
            for subtoken in token:
                self._parse_token(subtoken)
            self._close_subgroup()

        elif 'bool' in token_dict:
            self._add_bool(token_dict['bool'])

        elif 'hosts' in token_dict:
            token_dict['hosts'] = NodeSet(token_dict['hosts'])
            self._add_hosts(**token_dict)

        elif 'category' in token_dict:
            self._add_category(**token_dict)

        else:  # pragma: no cover - this should never happen
            raise InvalidQueryError(
                "No valid key found in token, one of bool|hosts|category expected: {token}".format(token=token_dict))

    def _get_resource_query(self, key, value=None, operator='='):  # pylint: disable=no-self-use
        """Build a resource query based on the parameters, resolving the special cases for %params and @field.

        Arguments:
        key      -- the key of the resource
        value    -- the value to match, if not specified the key itself will be matched [optional, default: None]
        operator -- the comparison operator to use, one of cumin.grammar.OPERATORS [optional: default: =]
        """
        if all(char in key for char in ('%', '@')):
            raise InvalidQueryError(("Resource key cannot contain both '%' (query a resource's parameter) and '@' "
                                     "(query a  resource's field)"))

        elif '%' in key:
            # Querying a specific parameter of the resource
            if operator == '~':
                raise InvalidQueryError('Regex operations are not supported in PuppetDB API v3 for resource parameters')
            key, param = key.split('%', 1)
            query_part = ', ["{op}", ["parameter", "{param}"], "{value}"]'.format(op=operator, param=param, value=value)

        elif '@' in key:
            # Querying a specific field of the resource
            key, field = key.split('@', 1)
            query_part = ', ["{op}", "{field}", "{value}"]'.format(op=operator, field=field, value=value)

        elif value is None:
            # Querying a specific resource type
            query_part = ''

        else:
            # Querying a specific resource title
            if key.lower() == 'class' and operator != '~':
                value = capwords(value, '::')  # Auto ucfirst the class title
            query_part = ', ["{op}", "title", "{value}"]'.format(op=operator, value=value)

        query = '["and", ["=", "type", "{type}"]{query_part}]'.format(type=capwords(key, '::'), query_part=query_part)

        return query

    def _get_query_string(self, group):
        """Recursively build and return the PuppetDB query string.

        Arguments:
        group -- a dictionary with the grouped tokens
        """
        if group['bool']:
            query = '["{bool}", '.format(bool=group['bool'])
        else:
            query = ''

        last_index = len(group['tokens'])
        for i, token in enumerate(group['tokens']):
            if isinstance(token, dict):
                query += self._get_query_string(group=token)
            else:
                query += token

            if i < last_index - 1:
                query += ', '

        if group['bool']:
            query += ']'

        return query

    def _add_bool(self, bool_op):
        """Add a boolean AND or OR query block to the query and validate logic.

        Arguments:
        bool_op -- the boolean operator (and|or) to add to the query
        """
        if self.current_group['bool'] is None:
            self.current_group['bool'] = bool_op
        elif self.current_group['bool'] == bool_op:
            return
        else:
            raise InvalidQueryError("Got unexpected '{bool}' boolean operator, current operator was '{current}'".format(
                bool=bool_op, current=self.current_group['bool']))

    def _api_call(self, query, endpoint):
        """Execute a query to PuppetDB API and return the parsed JSON.

        Arguments:
        query    -- the query parameter to send to the PuppetDB API
        endpoint -- the endpoint of the PuppetDB API to call
        """
        resources = requests.get(self.url + endpoint, params={'query': query}, verify=True)
        resources.raise_for_status()
        return resources.json()


# Required by the backend auto-loader in cumin.grammar.get_registered_backends()
GRAMMAR_PREFIX = 'P'
query_class = PuppetDBQuery  # pylint: disable=invalid-name
