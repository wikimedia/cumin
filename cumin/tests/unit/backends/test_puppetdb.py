"""PuppetDB backend tests."""
# pylint: disable=invalid-name
import pytest
import requests_mock

from requests.exceptions import HTTPError

from cumin.backends import BaseQuery, InvalidQueryError, puppetdb


def test_puppetdb_query_class():
    """An instance of query_class should be an instance of BaseQuery."""
    query = puppetdb.query_class({})
    assert isinstance(query, BaseQuery)


class TestPuppetDBQuery(object):
    """PuppetDB backend query test class."""

    def setup_method(self, _):
        """Setup an instace of PuppetDBQuery for each test."""
        self.query = puppetdb.PuppetDBQuery({})  # pylint: disable=attribute-defined-outside-init

    def test_instantiation(self):
        """An instance of PuppetDBQuery should be an instance of BaseQuery."""
        assert isinstance(self.query, BaseQuery)
        assert self.query.url == 'https://localhost:443/v3/'

    def test_category_getter(self):
        """Access to category property should return facts by default."""
        assert self.query.category == 'F'

    def test_category_setter(self):
        """Setting category property should accept only valid values, raise InvalidQueryError otherwise."""
        self.query.category = 'F'
        assert self.query.category == 'F'

        with pytest.raises(InvalidQueryError, match="Invalid value 'invalid_value'"):
            self.query.category = 'invalid_value'

        with pytest.raises(InvalidQueryError, match='Mixed F: and R: queries are currently not supported'):
            self.query.category = 'R'

        # Get a new query object to test also setting a resource before a fact
        query = puppetdb.query_class({})
        assert query.category == 'F'
        query.category = 'R'
        assert query.category == 'R'

        with pytest.raises(InvalidQueryError, match='Mixed F: and R: queries are currently not supported'):
            query.category = 'F'

    def test_add_category_fact(self):
        """Calling add_category() with a fact should add the proper query token to the object."""
        assert self.query.current_group['tokens'] == []
        # Base fact query
        self.query.add_category('F', 'key', 'value')
        assert self.query.current_group['tokens'] == ['["=", ["fact", "key"], "value"]']
        self.query.current_group['tokens'] = []
        # Negated query
        self.query.add_category('F', 'key', 'value', neg=True)
        assert self.query.current_group['tokens'] == ['["not", ["=", ["fact", "key"], "value"]]']
        self.query.current_group['tokens'] = []
        # Different operator
        self.query.add_category('F', 'key', 'value', operator='>=')
        assert self.query.current_group['tokens'] == ['[">=", ["fact", "key"], "value"]']
        self.query.current_group['tokens'] = []
        # Regex operator
        self.query.add_category('F', 'key', r'value\\escaped', operator='~')
        assert self.query.current_group['tokens'] == [r'["~", ["fact", "key"], "value\\\\escaped"]']
        # != is not supported by PuppetDB
        with pytest.raises(InvalidQueryError, match="PuppetDB backend doesn't support"):
            self.query.add_category('F', 'key', 'value', operator='!=')

    def test_add_category_resource_base(self):
        """Calling add_category() with a base resource query should add the proper query token to the object."""
        assert self.query.current_group['tokens'] == []
        self.query.add_category('R', 'key', 'value')
        assert self.query.current_group['tokens'] == ['["and", ["=", "type", "Key"], ["=", "title", "value"]]']

    def test_add_category_resource_class(self):
        """Calling add_category() with a class resource query should add the proper query token to the object."""
        assert self.query.current_group['tokens'] == []
        self.query.add_category('R', 'class', 'classtitle')
        assert self.query.current_group['tokens'] == ['["and", ["=", "type", "Class"], ["=", "title", "Classtitle"]]']

    def test_add_category_resource_class_path(self):
        """Calling add_category() with a class resource query should add the proper query token to the object."""
        assert self.query.current_group['tokens'] == []
        self.query.add_category('R', 'class', 'resource::path::to::class')
        assert self.query.current_group['tokens'] == \
            ['["and", ["=", "type", "Class"], ["=", "title", "Resource::Path::To::Class"]]']

    def test_add_category_resource_neg(self):
        """Calling add_category() with a negated resource query should add the proper query token to the object."""
        self.query.add_category('R', 'key', 'value', neg=True)
        assert self.query.current_group['tokens'] == \
            ['["not", ["and", ["=", "type", "Key"], ["=", "title", "value"]]]']

    def test_add_category_resource_regex(self):
        """Calling add_category() with a regex resource query should add the proper query token to the object."""
        self.query.add_category('R', 'key', r'value\\escaped', operator='~')
        assert self.query.current_group['tokens'] == \
            [r'["and", ["=", "type", "Key"], ["~", "title", "value\\\\escaped"]]']

    def test_add_category_resource_class_regex(self):
        """Calling add_category() with a regex Class resource query should add the proper query token to the object."""
        self.query.add_category('R', 'Class', r'Role::(One|Another)', operator='~')
        assert self.query.current_group['tokens'] == \
            [r'["and", ["=", "type", "Class"], ["~", "title", "Role::(One|Another)"]]']

    def test_add_category_resource_parameter(self):
        """Calling add_category() with a resource's parameter query should add the proper query token to the object."""
        self.query.add_category('R', 'resource%param', 'value')
        assert self.query.current_group['tokens'] == \
            ['["and", ["=", "type", "Resource"], ["=", ["parameter", "param"], "value"]]']

    def test_add_category_resource_parameter_regex(self):
        """Calling add_category() with a resource's parameter query with a regex should raise InvalidQueryError."""
        with pytest.raises(InvalidQueryError, match='Regex operations are not supported in PuppetDB'):
            self.query.add_category('R', 'resource%param', 'value.*', operator='~')

    def test_add_category_resource_field(self):
        """Calling add_category() with a resource's field query should add the proper query token to the object."""
        self.query.add_category('R', 'resource@field', 'value')
        assert self.query.current_group['tokens'] == \
            ['["and", ["=", "type", "Resource"], ["=", "field", "value"]]']

    def test_add_category_resource(self):
        """Calling add_category() with a resource type should add the proper query token to the object."""
        self.query.add_category('R', 'Resource')
        assert self.query.current_group['tokens'] == ['["and", ["=", "type", "Resource"]]']

    def test_add_category_resource_parameter_field(self):
        """Calling add_category() with both a parameter and a field should raise InvalidQueryError."""
        with pytest.raises(InvalidQueryError, match='Resource key cannot contain both'):
            self.query.add_category('R', 'resource@field%param')

    def test_add_hosts(self):
        """Calling add_hosts() with a resource should add the proper query token to the object."""
        assert self.query.current_group['tokens'] == []
        # No hosts
        self.query.add_hosts([])
        assert self.query.current_group['tokens'] == []
        # Single host
        self.query.add_hosts(['host'])
        assert self.query.current_group['tokens'] == ['["or", ["=", "{host_key}", "host"]]']
        self.query.current_group['tokens'] = []
        # Multiple hosts
        self.query.add_hosts(['host1', 'host2'])
        assert self.query.current_group['tokens'] == \
            ['["or", ["=", "{host_key}", "host1"], ["=", "{host_key}", "host2"]]']
        self.query.current_group['tokens'] = []
        # Negated query
        self.query.add_hosts(['host1', 'host2'], neg=True)
        assert self.query.current_group['tokens'] == \
            ['["not", ["or", ["=", "{host_key}", "host1"], ["=", "{host_key}", "host2"]]]']
        self.query.current_group['tokens'] = []
        # Globbing hosts
        self.query.add_hosts(['host1*.domain'])
        assert self.query.current_group['tokens'] == [r'["or", ["~", "{host_key}", "^host1.*\\.domain$"]]']

    def test_open_subgroup(self):
        """Calling open_subgroup() should open a subgroup and relate it to it's parent."""
        parent = {'parent': None, 'bool': None, 'tokens': []}
        child = {'parent': parent, 'bool': None, 'tokens': ['["or", ["=", "{host_key}", "host"]]']}
        parent['tokens'].append(child)
        self.query.open_subgroup()
        self.query.add_hosts(['host'])
        assert self.query.current_group['tokens'] == child['tokens']
        assert self.query.current_group['parent'] is not None

    def test_close_subgroup(self):
        """Calling close_subgroup() should close a subgroup and return to the parent's context."""
        self.query.open_subgroup()
        self.query.close_subgroup()
        assert len(self.query.current_group['tokens']) == 1
        assert self.query.current_group['tokens'][0]['tokens'] == []
        assert self.query.current_group['parent'] is None

    def test_add_and(self):
        """Calling add_and() should set the boolean property to the current group to 'and'."""
        assert self.query.current_group['bool'] is None
        self.query.add_and()
        assert self.query.current_group['bool'] == 'and'

    def test_add_or(self):
        """Calling add_or() should set the boolean property to the current group to 'or'."""
        assert self.query.current_group['bool'] is None
        self.query.add_or()
        assert self.query.current_group['bool'] == 'or'

    def test_add_and_or(self):
        """Calling add_or() and add_and() in the same group should raise InvalidQueryError."""
        self.query.add_hosts(['host1'])
        self.query.add_or()
        self.query.add_hosts(['host2'])

        with pytest.raises(InvalidQueryError):
            self.query.add_and()


@requests_mock.Mocker()
class TestPuppetDBQueryExecute(object):
    """PuppetDBQuery test execute() method class."""

    def setup_method(self, _):
        """Setup an instace of PuppetDBQuery for each test."""
        # pylint: disable=attribute-defined-outside-init
        self.query = puppetdb.PuppetDBQuery({'puppetdb': {'urllib3_disable_warnings': ['SubjectAltNameWarning']}})

    def _register_uris(self, requests):
        """Setup the requests library mock for each test."""
        # Register a requests valid response for each endpoint
        for category in self.query.endpoints:
            endpoint = self.query.endpoints[category]
            key = self.query.hosts_keys[category]
            requests.register_uri('GET', self.query.url + endpoint + '?query=', status_code=200, json=[
                {key: endpoint + '_host1', 'key': 'value1'}, {key: endpoint + '_host2', 'key': 'value2'}])

        # Register a requests response for an empty query
        requests.register_uri('GET', self.query.url + self.query.endpoints['F'] + '?query=', status_code=200,
                              json=[], complete_qs=True)
        # Register a requests response for an invalid query
        requests.register_uri('GET', self.query.url + self.query.endpoints['F'] + '?query=invalid_query',
                              status_code=400, complete_qs=True)

    def test_nodes_endpoint(self, requests):
        """Calling execute() with a query that goes to the nodes endpoint should return the list of hosts."""
        self._register_uris(requests)
        self.query.add_hosts(['nodes_host1', 'nodes_host2'])
        hosts = self.query.execute()
        assert sorted(hosts) == ['nodes_host1', 'nodes_host2']
        assert requests.call_count == 1

    def test_resources_endpoint(self, requests):
        """Calling execute() with a query that goes to the resources endpoint should return the list of hosts."""
        self._register_uris(requests)
        self.query.add_category('R', 'Class', 'value')
        hosts = self.query.execute()
        assert sorted(hosts) == ['resources_host1', 'resources_host2']
        assert requests.call_count == 1

    def test_with_boolean_operator(self, requests):
        """Calling execute() with a query with a boolean operator should return the list of hosts."""
        self._register_uris(requests)
        self.query.add_hosts(['nodes_host1'])
        self.query.add_or()
        self.query.add_hosts(['nodes_host2'])
        hosts = self.query.execute()
        assert sorted(hosts) == ['nodes_host1', 'nodes_host2']
        assert requests.call_count == 1

    def test_with_subgroup(self, requests):
        """Calling execute() with a query with a subgroup return the list of hosts."""
        self._register_uris(requests)
        self.query.open_subgroup()
        self.query.add_hosts(['nodes_host1'])
        self.query.add_or()
        self.query.add_hosts(['nodes_host2'])
        self.query.close_subgroup()
        hosts = self.query.execute()
        assert sorted(hosts) == ['nodes_host1', 'nodes_host2']
        assert requests.call_count == 1

    def test_empty(self, requests):
        """Calling execute() with a query that return no hosts should return an empty list."""
        self._register_uris(requests)
        hosts = self.query.execute()
        assert hosts == []
        assert requests.call_count == 1

    def test_error(self, requests):
        """Calling execute() if the request fails it should raise the requests exception."""
        self._register_uris(requests)
        self.query.current_group['tokens'].append('invalid_query')
        with pytest.raises(HTTPError):
            self.query.execute()
            assert requests.call_count == 1

    def test_complex_query(self, requests):
        """Calling execute() with a complex query should return the exptected structure."""
        category = 'R'
        endpoint = self.query.endpoints[category]
        key = self.query.hosts_keys[category]
        requests.register_uri('GET', self.query.url + endpoint + '?query=', status_code=200, json=[
            {key: endpoint + '_host1', 'key': 'value1'}, {key: endpoint + '_host2', 'key': 'value2'}])

        self.query.open_subgroup()
        self.query.add_hosts(['resources_host1'])
        self.query.add_or()
        self.query.add_hosts(['resources_host2'])
        self.query.close_subgroup()
        self.query.add_and()
        self.query.add_category('R', 'Class', value='MyClass', operator='=')
        hosts = self.query.execute()
        assert sorted(hosts) == ['resources_host1', 'resources_host2']
        assert requests.call_count == 1
