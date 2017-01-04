import requests

from cumin.backends import BaseQuery, InvalidQueryError


class PuppetDBQuery(BaseQuery):
    """ PuppetDB query builder

        The 'direct' backend allow to use an existing PuppetDB instance for the hosts selection.
        At the moment only PuppetDB v3 API are implemented.
    """

    base_url_template = 'https://{host}:{port}/v3/'
    endpoints = {'R': 'resources', 'F': 'nodes'}
    hosts_keys = {'R': 'certname', 'F': 'name'}

    def __init__(self, config, logger=None):
        """ Query Builder constructor

            Arguments: according to BaseQuery interface
        """
        super(PuppetDBQuery, self).__init__(config, logger)
        self.grouped_tokens = {'parent': None, 'bool': None, 'tokens': []}
        self.current_group = self.grouped_tokens
        self._category = None
        puppetdb_config = self.config.get('puppetdb', {})
        self.url = self.base_url_template.format(
            host=puppetdb_config.get('host', 'localhost'),
            port=puppetdb_config.get('port', 443))

    @property
    def category(self):
        """Getter for the property category with a default value"""
        return self._category or 'F'

    @category.setter
    def category(self, value):
        """ Setter for the property category with validation

            Arguments:
            value -- the value to set the category to
        """
        if value not in self.endpoints.keys():
            raise RuntimeError("Invalid value '{category}' for category property".format(category=value))
        if self._category is not None and value != self._category:
            raise RuntimeError('Mixed F: and R: queries are currently not supported')

        self._category = value

    def add_category(self, category, key, value=None, operator='=', neg=False):
        """Required by BaseQuery"""
        self.category = category
        if operator == '~':
            value = value.replace(r'\\', r'\\\\')  # Required by PuppetDB API
        elif operator == '!=':
            raise RuntimeError("PuppetDB backend doesn't support the '!=' operator")

        if category == 'R':
            query = self._get_resource_query(key, value, operator)
        elif category == 'F':
            query = '["{op}", ["fact", "{key}"], "{val}"]'.format(op=operator, key=key, val=value)

        if neg:
            query = '["not", {query}]'.format(query=query)

        self.current_group['tokens'].append(query)

    def add_hosts(self, hosts, neg=False):
        """Required by BaseQuery"""
        if len(hosts) == 0:
            return

        hosts_tokens = []
        for host in hosts:
            operator = '='
            # Convert a glob expansion into a regex
            if '*' in host:
                operator = '~'
                host = host.replace('.', r'\\.').replace('*', '.*')

            hosts_tokens.append('["{op}", "{{host_key}}", "{host}"]'.format(op=operator, host=host))

        query = '["or", {hosts}]'.format(hosts=', '.join(hosts_tokens))
        if neg:
            query = '["not", {query}]'.format(query=query)

        self.current_group['tokens'].append(query)

    def open_subgroup(self):
        """Required by BaseQuery"""
        token = {'parent': self.current_group, 'bool': None, 'tokens': []}
        self.current_group['tokens'].append(token)
        self.current_group = token

    def close_subgroup(self):
        """Required by BaseQuery"""
        self.current_group = self.current_group['parent']

    def add_and(self):
        """Required by BaseQuery"""
        self._add_bool('and')

    def add_or(self):
        """Required by BaseQuery"""
        self._add_bool('or')

    def execute(self):
        """Required by BaseQuery"""
        query = self._get_query_string(group=self.grouped_tokens).format(host_key=self.hosts_keys[self.category])
        hosts = self._execute(query, self.endpoints[self.category])

        return {host[self.hosts_keys[self.category]] for host in hosts}  # Set comprehension

    def _get_resource_query(self, key, value=None, operator='='):
        """ Build a resource query based on the parameters, resolving the special cases for %params and @field

            Arguments:
            key      -- the key of the resource
            value    -- the value to match, if not specified the key itself will be matched [optional, default: None]
            operator -- the comparison operator to use, one of cumin.grammar.operators [optional: default: =]
        """
        if all(char in key for char in ('%', '@')):
            raise RuntimeError(("Resource key cannot contain both '%' (query a resource's parameter) and '@' (query a "
                                " resource's field)"))

        elif '%' in key:
            # Querying a specific parameter of the resource
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
            query_part = ', ["{op}", "title", "{value}"]'.format(op=operator, value=value)

        query = '["and", ["=", "type", "{type}"]{query_part}]'.format(type=key, query_part=query_part)

        return query

    def _get_query_string(self, group):
        """ Recursively build and return the PuppetDB query string

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
        """ Add a boolean AND or OR query block to the query and validate logic

            Arguments:
            bool_op -- the boolean operator (and|or) to add to the query
        """
        if self.current_group['bool'] is None:
            self.current_group['bool'] = bool_op
        elif self.current_group['bool'] != bool_op:
            raise InvalidQueryError("Got unexpected '{bool}' boolean operator, current operator was '{current}'".format(
                bool=bool_op, current=self.current_group['bool']))

    def _execute(self, query, endpoint):
        """ Execute a query to PuppetDB API and return the parsed JSON

            Arguments:
            query    -- the query parameter to send to the PuppetDB API
            endpoint -- the endpoint of the PuppetDB API to call
        """
        self.logger.debug('Querying puppetdb: {query}'.format(query=query))
        resources = requests.get(self.url + endpoint, params={'query': query}, verify=True)
        resources.raise_for_status()
        return resources.json()


query_class = PuppetDBQuery  # Required by the auto-loader in the cumin.query.Query factory
