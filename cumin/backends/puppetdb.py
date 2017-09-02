# pylint: skip-file
# See https://github.com/PyCQA/astroid/issues/437
"""PuppetDB backend."""
from string import capwords

import pyparsing as pp
import requests

from requests.packages import urllib3

from cumin import nodeset, nodeset_fromlist
from cumin.backends import BaseQuery, InvalidQueryError


CATEGORIES = ('C', 'F', 'O', 'P', 'R')
""":py:func:`tuple`: available categories in the grammar.

* ``C``: shortcut for querying resources of type ``Class``, equivalent of `R:Class = class_path``.
* ``F``: for querying facts.
* ``O``: shortcut for querying resources of type ``Class`` that starts with ``Role::``.
* ``P``: shortcut for querying resources of type ``Class`` that starts with ``Profile::``.
* ``R``: for querying generic resources.
"""

OPERATORS = ('=', '>=', '<=', '<', '>', '~')
""":py:func:`tuple`: available operators in the grammar, the same available in PuppetDB API.

The ``~`` one is used for regex matching.
"""


def grammar():
    """Define the query grammar.

    Backus-Naur form (BNF) of the grammar::

            <grammar> ::= <item> | <item> <and_or> <grammar>
               <item> ::= [<neg>] <query-token> | [<neg>] "(" <grammar> ")"
        <query-token> ::= <token> | <hosts>
              <token> ::= <category>:<key> [<operator> <value>]

    Given that the pyparsing library defines the grammar in a BNF-like style, for the details of the tokens not
    specified above check directly the source code.

    Returns:
        pyparsing.ParserElement: the grammar parser.

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

    The `puppetdb` backend allow to use an existing PuppetDB instance for the hosts selection.
    The supported PuppetDB API versions are 3 and 4. It can be specified via the api_version configuration key, if
    not configured, the v4 will be used.

    * Each query part can be composed with the others using boolean operators (``and``, ``or``, ``not``)
    * Multiple query parts can be grouped together with parentheses (``(``, ``)``).
    * A query part can be of two different types:

      * ``Hostname matching``: this is a simple string that be used to match directly the hostname of the hosts in the
        selected backend. It allows for glob expansion (``*``) and the use of the powerful
        :py:class:`ClusterShell.NodeSet.NodeSet`.
      * ``Category matching``: an identifier composed by a category, a colon and a key, followed by a comparison
        operator and a value, as in ``F:key = value``.

    Some query examples:

    * All hosts: ``*``
    * Hosts globbing: ``host10*``
    * :py:class:`ClusterShell.NodeSet.NodeSet` syntax for hosts expansion: ``host10[10-42].domain``
    * Category based key-value selection:

      * ``R:Resource::Name``: query all the hosts that have a resource of type `Resource::Name`.
      * ``R:Resource::Name = 'resource-title'``: query all the hosts that have a resource of type `Resource::Name`
        whose title is ``resource-title``. For example ``R:Class = MyModule::MyClass``.
      * ``R:Resource::Name@field = 'some-value'``: query all the hosts that have a resource of type ``Resource::Name``
        whose field ``field`` has the value ``some-value``. The valid fields are: ``tag``, ``certname``, ``type``,
        ``title``, ``exported``, ``file``, ``line``. The previous syntax is a shortcut for this one with the field
        ``title``.
      * ``R:Resource::Name%param = 'some-value'``: query all the hosts that have a resource of type ``Resource::Name``
        whose parameter ``param`` has the value ``some-value``.
      * ``C:Class::Name``: special shortcut to query all the hosts that have a resource of type ``Class`` whose name
        is ``Class::Name``. The ``Class::Name`` part is completely arbitrary and depends on the puppet hierarchy
        chosen. It's equivalent to ``R:Class = Class::Name``, with the addition that the ``param`` and ``field``
        selectors described above can be used directly without the need to add another condition.
      * ``O:Module::Name``: special shortcut to query all the hosts that have a resource of type ``Class`` whose name
        is ``Role::Module::Name``. The ``Module::Name`` part is completely arbitrary and depends on the puppet
        hierarchy chosen. It's equivalent to ``R:Class = Role::Module::Name``, with the addition that the ``param`` and
        ``field`` selectors described above can be used directly without the need to add another condition, although
        usually roles should not have parameters in the role/profile Puppet paradigm.
      * ``P:Module::Name``: special shortcut to query all the hosts that have a resource of type ``Class`` whose name
        is ``Profile::Module::Name``. The ``Module::Name`` part is completely arbitrary and depends on the puppet
        hierarchy chosen. It's equivalent to ``R:Class = Profile::Module::Name``, with the addition that the ``param``
        and ``field`` selectors described above can be used directly without the need to add another condition.
      * ``F:FactName = value``: query all the hosts that have a fact ``FactName``, as reported by facter, with the
        value ``value``.
      * Mixed facts/resources queries are not supported, but the same result can be achieved using the main grammar
        with multiple subqueries for the PuppetDB backend.

    * A complex selection for facts:
      ``host10[10-42].*.domain or (not F:key1 = value1 and host10*) or (F:key2 > value2 and F:key3 ~ '^value[0-9]+')``
    """

    base_url_template = 'https://{host}:{port}'
    """:py:class:`str`: string template in the :py:meth:`str.format` style used to generate the base URL of the
    PuppetDB server."""

    endpoints = {'C': 'resources', 'F': 'nodes', 'O': 'resources', 'P': 'resources', 'R': 'resources'}
    """:py:class:`dict`: dictionary with the mapping of the available categories in the grammar to the PuppetDB API
    endpoints."""

    category_prefixes = {'C': '', 'O': 'Role', 'P': 'Profile'}
    """:py:class:`dict`: dictionary with the mapping of special categories to title prefixes."""

    grammar = grammar()
    """:py:class:`pyparsing.ParserElement`: load the grammar parser only once in a singleton-like way."""

    def __init__(self, config):
        """Query constructor for the PuppetDB backend.

        :Parameters:
            according to parent :py:meth:`cumin.backends.BaseQuery.__init__`.

        """
        super().__init__(config)
        self.grouped_tokens = None
        self.current_group = self.grouped_tokens
        self._endpoint = None
        puppetdb_config = self.config.get('puppetdb', {})
        base_url = self.base_url_template.format(
            host=puppetdb_config.get('host', 'localhost'),
            port=puppetdb_config.get('port', 443))

        self.api_version = puppetdb_config.get('api_version', 4)
        if self.api_version == 3:
            self.url = base_url + '/v3/'
            self.hosts_keys = {'nodes': 'name', 'resources': 'certname'}
        elif self.api_version == 4:
            self.url = base_url + '/pdb/query/v4/'
            self.hosts_keys = {'nodes': 'certname', 'resources': 'certname'}
        else:
            raise InvalidQueryError('Unsupported PuppetDB API version {ver}'.format(ver=self.api_version))

        for exception in puppetdb_config.get('urllib3_disable_warnings', []):
            urllib3.disable_warnings(category=getattr(urllib3.exceptions, exception))

    @property
    def endpoint(self):
        """Endpoint in the PuppetDB API for the current query.

        :Getter:
            Returns the current `endpoint` or a default value if not set.

        :Setter:
            :py:class:`str`: the value to set the `endpoint` to.

        Raises:
            cumin.backends.InvalidQueryError: if trying to set it to an invalid `endpoint` or mixing endpoints in a
                single query.

        """
        return self._endpoint or 'nodes'

    @endpoint.setter
    def endpoint(self, value):
        """Setter for the `endpoint` property. The relative documentation is in the getter."""
        if value not in self.endpoints.values():
            raise InvalidQueryError("Invalid value '{endpoint}' for endpoint property".format(endpoint=value))
        if self._endpoint is not None and value != self._endpoint:
            raise InvalidQueryError('Mixed endpoints are not supported, use the global grammar to mix them.')

        self._endpoint = value

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
        """Return an empty grouped tokens structure.

        Returns:
            dict: the dictionary with the empty grouped tokens structure.

        """
        return {'parent': None, 'bool': None, 'tokens': []}

    def _build(self, query_string):
        """Override parent class _build method to reset tokens and add logging.

        :Parameters:
            according to parent :py:meth:`cumin.backends.BaseQuery._build`.

        """
        self.grouped_tokens = PuppetDBQuery._get_grouped_tokens()
        self.current_group = self.grouped_tokens
        super()._build(query_string)
        self.logger.trace('Query tokens: %s', self.grouped_tokens)

    def _execute(self):
        """Concrete implementation of parent abstract method.

        :Parameters:
            according to parent :py:meth:`cumin.backends.BaseQuery._execute`.

        Returns:
            ClusterShell.NodeSet.NodeSet: with the FQDNs of the matching hosts.

        """
        query = self._get_query_string(group=self.grouped_tokens).format(host_key=self.hosts_keys[self.endpoint])
        hosts = self._api_call(query)
        unique_hosts = nodeset_fromlist([host[self.hosts_keys[self.endpoint]] for host in hosts])
        self.logger.debug("Queried puppetdb for '%s', got '%d' results.", query, len(unique_hosts))

        return unique_hosts

    def _add_category(self, category, key, value=None, operator='=', neg=False):
        """Add a category token to the query 'F:key = value'.

        Arguments:
            category (str): the category of the token, one of :py:const:`CATEGORIES`.
            key (str): the key for this category.
            value (str, optional): the value to match, if not specified the key itself will be matched.
            operator (str, optional): the comparison operator to use, one of :py:const:`OPERATORS`.
            neg (bool, optional): whether the token must be negated.

        Raises:
            cumin.backends.InvalidQueryError: on internal parsing error.

        """
        self.endpoint = self.endpoints[category]
        if operator == '~':
            value = value.replace(r'\\', r'\\\\')  # Required by PuppetDB API

        if category in ('C', 'O', 'P'):
            query = self._get_special_resource_query(category, key, value, operator)
        elif category == 'R':
            query = self._get_resource_query(key, value, operator)
        elif category == 'F':
            query = '["{op}", ["fact", "{key}"], "{val}"]'.format(op=operator, key=key, val=value)
        else:  # pragma: no cover - this should never happen
            raise InvalidQueryError(
                "Got invalid category '{category}', one of F|O|P|R expected".format(category=category))

        if neg:
            query = '["not", {query}]'.format(query=query)

        self.current_group['tokens'].append(query)

    def _add_hosts(self, hosts, neg=False):
        """Add a list of hosts to the query.

        Arguments:
            hosts (ClusterShell.NodeSet.NodeSet): with the list of hosts to search.
            neg (bool, optional): whether the token must be negated.
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
        """Concrete implementation of parent abstract method.

        :Parameters:
            according to parent :py:meth:`cumin.backends.BaseQuery._parse_token`.

        Raises:
            cumin.backends.InvalidQueryError: on internal parsing error.

        """
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
            token_dict['hosts'] = nodeset(token_dict['hosts'])
            self._add_hosts(**token_dict)

        elif 'category' in token_dict:
            self._add_category(**token_dict)

        else:  # pragma: no cover - this should never happen
            raise InvalidQueryError(
                "No valid key found in token, one of bool|hosts|category expected: {token}".format(token=token_dict))

    def _get_resource_query(self, key, value=None, operator='='):  # pylint: disable=no-self-use
        """Build a resource query based on the parameters, resolving the special cases for ``%params`` and ``@field``.

        Arguments:
            key (str): the key of the resource.
            value (str, optional): the value to match, if not specified the key itself will be matched.
            operator (str, optional): the comparison operator to use, one of :py:const:`OPERATORS`.

        Returns:
            str: the resource query.

        Raises:
            cumin.backends.InvalidQueryError: on invalid combinations of parameters.

        """
        if all(char in key for char in ('%', '@')):
            raise InvalidQueryError(("Resource key cannot contain both '%' (query a resource's parameter) and '@' "
                                     "(query a  resource's field)"))

        elif '%' in key:
            # Querying a specific parameter of the resource
            if operator == '~' and self.api_version == 3:
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

    def _get_special_resource_query(self, category, key, value, operator):
        """Build a query for Roles and Profiles, resolving the special cases for ``%params`` and ``@field``.

        Arguments:
            category (str): the category of the token, one of :py:data:`category_prefixes` keys.
            key (str): the key of the resource to use as a suffix for the Class title matching.
            value (str, optional): the value to match in case ``%params`` or ``@field`` is specified.
            operator (str, optional): the comparison operator to use if there is a value, one of :py:const:`OPERATORS`.

        Returns:
            str: the resource query.

        Raises:
            cumin.backends.InvalidQueryError: on invalid combinations of parameters.

        """
        if all(char in key for char in ('%', '@')):
            raise InvalidQueryError(("Resource key cannot contain both '%' (query a resource's parameter) and '@' "
                                     "(query a  resource's field)"))
        elif '%' in key:
            special = '%'
            key, param = key.split('%')
        elif '@' in key:
            special = '@'
            key, param = key.split('@')
        else:
            special = None
            if value is not None:
                raise InvalidQueryError(("Invalid query of the form '{category}:key = value'. The matching of a value "
                                         "is accepted only when using %param or @field.").format(category=category))

        if self.category_prefixes[category]:
            title = '{prefix}::{key}'.format(prefix=self.category_prefixes[category], key=key)
        else:
            title = key

        query = self._get_resource_query('Class', title, '=')

        if special is not None:
            param_query = self._get_resource_query(''.join(('Class', special, param)), value, operator)
            query = '["and", {query}, {param_query}]'.format(query=query, param_query=param_query)

        return query

    def _get_query_string(self, group):
        """Recursively build and return the PuppetDB query string.

        Arguments:
            group (dict): a dictionary with the grouped tokens.

        Returns:
            str: the query string for the PuppetDB API.

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
            bool_op (str): the boolean operator to add to the query: ``and``, ``or``.

        Raises:
            cumin.backends.InvalidQueryError: if an invalid boolean operator was found.

        """
        if self.current_group['bool'] is None:
            self.current_group['bool'] = bool_op
        elif self.current_group['bool'] == bool_op:
            return
        else:
            raise InvalidQueryError("Got unexpected '{bool}' boolean operator, current operator was '{current}'".format(
                bool=bool_op, current=self.current_group['bool']))

    def _api_call(self, query):
        """Execute a query to PuppetDB API and return the parsed JSON.

        Arguments:
            query (str): the query parameter to send to the PuppetDB API.

        Raises:
            requests.HTTPError: if the PuppetDB API call fails.

        """
        if self.api_version == 3:
            resources = requests.get(self.url + self.endpoint, params={'query': query}, verify=True)
        else:
            resources = requests.post(self.url + self.endpoint, json={'query': query}, verify=True)

        resources.raise_for_status()
        return resources.json()


GRAMMAR_PREFIX = 'P'
""":py:class:`str`: the prefix associate to this grammar, to register this backend into the general grammar.
Required by the backend auto-loader in :py:meth:`cumin.grammar.get_registered_backends`."""

query_class = PuppetDBQuery  # pylint: disable=invalid-name
"""Required by the backend auto-loader in :py:meth:`cumin.grammar.get_registered_backends`."""
