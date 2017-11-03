"""PuppetDB backend tests."""
# pylint: disable=invalid-name
import mock
import pytest
import requests_mock

from ClusterShell.NodeSet import NodeSet
from requests.exceptions import HTTPError

from cumin.backends import BaseQuery, InvalidQueryError, puppetdb


def test_puppetdb_query_class():
    """An instance of query_class should be an instance of BaseQuery."""
    query = puppetdb.query_class({})
    assert isinstance(query, BaseQuery)


def _get_category_key_token(category='F', key='key1', operator='=', value='value1'):
    """Generate and return a category token string and it's expected dictionary of tokens when parsed."""
    expected = {'category': category, 'key': key, 'operator': operator, 'value': value}
    token = '{category}:{key} {operator} {value}'.format(**expected)
    return token, expected


def test_single_category_key_token():
    """A valid single token with a category that has key is properly parsed and interpreted."""
    token, expected = _get_category_key_token()
    parsed = puppetdb.grammar().parseString(token, parseAll=True)
    assert parsed[0].asDict() == expected


def test_hosts_selection():
    """A host selection is properly parsed and interpreted."""
    hosts = {'hosts': 'host[10-20,30-40].domain'}
    parsed = puppetdb.grammar().parseString(hosts['hosts'], parseAll=True)
    assert parsed[0].asDict() == hosts


class TestPuppetDBQuery(object):
    """PuppetDB backend query test class."""

    def setup_method(self, _):
        """Setup an instace of PuppetDBQuery for each test."""
        self.query = puppetdb.PuppetDBQuery({})  # pylint: disable=attribute-defined-outside-init

    def test_instantiation(self):
        """An instance of PuppetDBQuery should be an instance of BaseQuery."""
        assert isinstance(self.query, BaseQuery)
        assert self.query.url == 'https://localhost:443/v3/'

    def test_endpoint_getter(self):
        """Access to endpoint property should return nodes by default."""
        assert self.query.endpoint == 'nodes'

    @pytest.mark.parametrize('endpoint', puppetdb.PuppetDBQuery.hosts_keys)
    def test_endpoint_setter_valid(self, endpoint):
        """Setting the endpoint property should accept valid values."""
        self.query.endpoint = endpoint
        assert self.query.endpoint == endpoint

    def test_endpoint_setter_invalid(self):
        """Setting the endpoint property should raise InvalidQueryError for an invalid value."""
        with pytest.raises(InvalidQueryError, match="Invalid value 'invalid_value'"):
            self.query.endpoint = 'invalid_value'

    def test_endpoint_setter_mixed1(self):
        """Setting the endpoint property twice to different values should raise InvalidQueryError (combination 1)."""
        assert self.query.endpoint == 'nodes'
        self.query.endpoint = 'resources'
        assert self.query.endpoint == 'resources'
        with pytest.raises(InvalidQueryError, match='Mixed endpoints are not supported'):
            self.query.endpoint = 'nodes'

    def test_endpoint_setter_mixed2(self):
        """Setting the endpoint property twice to different values should raise InvalidQueryError (combination 2)."""
        assert self.query.endpoint == 'nodes'
        self.query.endpoint = 'nodes'
        assert self.query.endpoint == 'nodes'
        with pytest.raises(InvalidQueryError, match='Mixed endpoints are not supported'):
            self.query.endpoint = 'resources'


@mock.patch.object(puppetdb.PuppetDBQuery, '_api_call')
class TestPuppetDBQueryBuild(object):
    """PuppetDB backend query build test class."""

    def setup_method(self, _):
        """Setup an instace of PuppetDBQuery for each test."""
        self.query = puppetdb.PuppetDBQuery({})  # pylint: disable=attribute-defined-outside-init

    def test_add_category_fact(self, mocked_api_call):
        """A fact query should add the proper query token to the current_group."""
        # Base fact query
        self.query.execute('F:key=value')
        mocked_api_call.assert_called_with('["=", ["fact", "key"], "value"]')
        # Negated query
        self.query.execute('not F:key = value')
        mocked_api_call.assert_called_with('["not", ["=", ["fact", "key"], "value"]]')
        # Different operator
        self.query.execute('F:key >= value')
        mocked_api_call.assert_called_with('[">=", ["fact", "key"], "value"]')
        # Regex operator
        self.query.execute(r'F:key ~ value\\escaped')
        mocked_api_call.assert_called_with(r'["~", ["fact", "key"], "value\\\\escaped"]')

    def test_add_category_resource_base(self, mocked_api_call):
        """A base resource query should add the proper query token to the current_group."""
        self.query.execute('R:key = value')
        mocked_api_call.assert_called_with('["and", ["=", "type", "Key"], ["=", "title", "value"]]')

    def test_add_category_resource_class(self, mocked_api_call):
        """A class resource query should add the proper query token to the current_group."""
        self.query.execute('R:class = classtitle')
        mocked_api_call.assert_called_with('["and", ["=", "type", "Class"], ["=", "title", "Classtitle"]]')

    def test_add_category_resource_class_path(self, mocked_api_call):
        """Executing a query with a class resource query should add the proper query token to the current_group."""
        self.query.execute('R:class = resource::path::to::class')
        mocked_api_call.assert_called_with(
            '["and", ["=", "type", "Class"], ["=", "title", "Resource::Path::To::Class"]]')

    def test_add_category_resource_neg(self, mocked_api_call):
        """A negated resource query should add the proper query token to the current_group."""
        self.query.execute('not R:key = value')
        mocked_api_call.assert_called_with('["not", ["and", ["=", "type", "Key"], ["=", "title", "value"]]]')

    def test_add_category_resource_regex(self, mocked_api_call):
        """A regex resource query should add the proper query token to the current_group."""
        self.query.execute(r'R:key ~ value\\escaped')
        mocked_api_call.assert_called_with(r'["and", ["=", "type", "Key"], ["~", "title", "value\\\\escaped"]]')

    def test_add_category_resource_class_regex(self, mocked_api_call):
        """A regex Class resource query should add the proper query token to the current_group."""
        self.query.execute(r'R:Class ~ "Role::(One|Another)"')
        mocked_api_call.assert_called_with(r'["and", ["=", "type", "Class"], ["~", "title", "Role::(One|Another)"]]')

    def test_add_category_resource_parameter(self, mocked_api_call):
        """A resource's parameter query should add the proper query token to the object."""
        self.query.execute('R:resource%param = value')
        mocked_api_call.assert_called_with(
            '["and", ["=", "type", "Resource"], ["=", ["parameter", "param"], "value"]]')

    def test_add_category_resource_parameter_regex(self, mocked_api_call):
        """A resource's parameter query with a regex should raise InvalidQueryError."""
        with pytest.raises(InvalidQueryError, match='Regex operations are not supported in PuppetDB'):
            self.query.execute('R:resource%param ~ value.*')
            assert not mocked_api_call.called

    def test_add_category_resource_field(self, mocked_api_call):
        """A resource's field query should add the proper query token to the current_group."""
        self.query.execute('R:resource@field = value')
        mocked_api_call.assert_called_with('["and", ["=", "type", "Resource"], ["=", "field", "value"]]')

    def test_add_category_resource(self, mocked_api_call):
        """A resource type should add the proper query token to the current_group."""
        self.query.execute('R:Resource')
        mocked_api_call.assert_called_with('["and", ["=", "type", "Resource"]]')

    def test_add_category_resource_parameter_field(self, mocked_api_call):
        """A query with both a resource's parameter and field should raise InvalidQueryError."""
        with pytest.raises(InvalidQueryError, match='Resource key cannot contain both'):
            self.query.execute('R:resource%param@field')
            assert not mocked_api_call.called

    def test_add_category_resource_field_parameter(self, mocked_api_call):
        """A query with both a resource's parameter and field should raise InvalidQueryError."""
        with pytest.raises(InvalidQueryError, match='Resource key cannot contain both'):
            self.query.execute('R:resource@field%param')
            assert not mocked_api_call.called

    def test_add_category_class(self, mocked_api_call):
        """A class resource query should add the proper query token to the current_group."""
        self.query.execute('C:class_name')
        mocked_api_call.assert_called_with('["and", ["=", "type", "Class"], ["=", "title", "Class_name"]]')

    def test_add_category_class_path(self, mocked_api_call):
        """A class resource path query should add the proper query token to the current_group."""
        self.query.execute('C:module::class::name')
        mocked_api_call.assert_called_with('["and", ["=", "type", "Class"], ["=", "title", "Module::Class::Name"]]')

    def test_add_category_class_value(self, mocked_api_call):
        """A class query with a value should raise InvalidQueryError."""
        with pytest.raises(InvalidQueryError, match='The matching of a value is accepted only when using'):
            self.query.execute('C:class_name = value')
            assert not mocked_api_call.called

    def test_add_category_class_parameter(self, mocked_api_call):
        """A class resource query with parameter should add the proper query token to the current_group."""
        self.query.execute('C:class_name%param = value')
        mocked_api_call.assert_called_with((
            '["and", ["and", ["=", "type", "Class"], ["=", "title", "Class_name"]], '
            '["and", ["=", "type", "Class"], ["=", ["parameter", "param"], "value"]]]'))

    def test_add_category_class_field(self, mocked_api_call):
        """A class resource query with field should add the proper query token to the current_group."""
        self.query.execute('C:class_name@field = value')
        mocked_api_call.assert_called_with((
            '["and", ["and", ["=", "type", "Class"], ["=", "title", "Class_name"]], '
            '["and", ["=", "type", "Class"], ["=", "field", "value"]]]'))

    def test_add_category_class_parameter_field(self, mocked_api_call):
        """A query with both a class's parameter and field should raise InvalidQueryError."""
        with pytest.raises(InvalidQueryError, match='Resource key cannot contain both'):
            self.query.execute('C:class_name%param@field')
            assert not mocked_api_call.called

    def test_add_category_class_field_parameter(self, mocked_api_call):
        """A query with both a class's field and parameter should raise InvalidQueryError."""
        with pytest.raises(InvalidQueryError, match='Resource key cannot contain both'):
            self.query.execute('C:class_name@field%param')
            assert not mocked_api_call.called

    def test_add_category_profile(self, mocked_api_call):
        """A profile resource query should add the proper query token to the current_group."""
        self.query.execute('P:profile_name')
        mocked_api_call.assert_called_with('["and", ["=", "type", "Class"], ["=", "title", "Profile::Profile_name"]]')

    def test_add_category_profile_module(self, mocked_api_call):
        """A profile resource module query should add the proper query token to the current_group."""
        self.query.execute('P:module::name')
        mocked_api_call.assert_called_with('["and", ["=", "type", "Class"], ["=", "title", "Profile::Module::Name"]]')

    def test_add_category_profile_value(self, mocked_api_call):
        """A profile query with a value should raise InvalidQueryError."""
        with pytest.raises(InvalidQueryError, match='The matching of a value is accepted only when using'):
            self.query.execute('P:profile_name = value')
            assert not mocked_api_call.called

    def test_add_category_profile_parameter(self, mocked_api_call):
        """A profile resource query with parameter should add the proper query token to the current_group."""
        self.query.execute('P:profile_name%param = value')
        mocked_api_call.assert_called_with((
            '["and", ["and", ["=", "type", "Class"], ["=", "title", "Profile::Profile_name"]], '
            '["and", ["=", "type", "Class"], ["=", ["parameter", "param"], "value"]]]'))

    def test_add_category_profile_field(self, mocked_api_call):
        """A profile resource query with field should add the proper query token to the current_group."""
        self.query.execute('P:profile_name@field = value')
        mocked_api_call.assert_called_with((
            '["and", ["and", ["=", "type", "Class"], ["=", "title", "Profile::Profile_name"]], '
            '["and", ["=", "type", "Class"], ["=", "field", "value"]]]'))

    def test_add_category_profile_parameter_field(self, mocked_api_call):
        """A query with both a profile's parameter and field should raise InvalidQueryError."""
        with pytest.raises(InvalidQueryError, match='Resource key cannot contain both'):
            self.query.execute('P:profile_name%param@field')
            assert not mocked_api_call.called

    def test_add_category_profile_field_parameter(self, mocked_api_call):
        """A query with both a profile's field and parameter should raise InvalidQueryError."""
        with pytest.raises(InvalidQueryError, match='Resource key cannot contain both'):
            self.query.execute('P:profile_name@field%param')
            assert not mocked_api_call.called

    def test_add_category_role(self, mocked_api_call):
        """A role resource query should add the proper query token to the current_group."""
        self.query.execute('O:role_name')
        mocked_api_call.assert_called_with('["and", ["=", "type", "Class"], ["=", "title", "Role::Role_name"]]')

    def test_add_category_role_module(self, mocked_api_call):
        """A role resource module query should add the proper query token to the current_group."""
        self.query.execute('O:module::name')
        mocked_api_call.assert_called_with('["and", ["=", "type", "Class"], ["=", "title", "Role::Module::Name"]]')

    def test_add_category_role_value(self, mocked_api_call):
        """A role query with a value should raise InvalidQueryError."""
        with pytest.raises(InvalidQueryError, match='The matching of a value is accepted only when using'):
            self.query.execute('O:role_name = value')
            assert not mocked_api_call.called

    def test_add_category_role_parameter(self, mocked_api_call):
        """A role resource query with parameter should add the proper query token to the current_group."""
        self.query.execute('O:role_name%param = value')
        mocked_api_call.assert_called_with((
            '["and", ["and", ["=", "type", "Class"], ["=", "title", "Role::Role_name"]], '
            '["and", ["=", "type", "Class"], ["=", ["parameter", "param"], "value"]]]'))

    def test_add_category_role_field(self, mocked_api_call):
        """A role resource query with field should add the proper query token to the current_group."""
        self.query.execute('O:role_name@field = value')
        mocked_api_call.assert_called_with((
            '["and", ["and", ["=", "type", "Class"], ["=", "title", "Role::Role_name"]], '
            '["and", ["=", "type", "Class"], ["=", "field", "value"]]]'))

    def test_add_category_role_parameter_field(self, mocked_api_call):
        """A query with both a role's parameter and field should raise InvalidQueryError."""
        with pytest.raises(InvalidQueryError, match='Resource key cannot contain both'):
            self.query.execute('O:role_name%param@field')
            assert not mocked_api_call.called

    def test_add_category_role_field_parameter(self, mocked_api_call):
        """A query with both a role's field and parameter should raise InvalidQueryError."""
        with pytest.raises(InvalidQueryError, match='Resource key cannot contain both'):
            self.query.execute('O:role_name@field%param')
            assert not mocked_api_call.called

    def test_add_hosts(self, mocked_api_call):
        """A host query should add the proper query token to the current_group."""
        # No hosts
        self.query.execute('host1!host1')
        mocked_api_call.assert_called_with('')
        # Single host
        self.query.execute('host')
        mocked_api_call.assert_called_with('["or", ["=", "name", "host"]]')
        # Multiple hosts
        self.query.execute('host[1-2]')
        mocked_api_call.assert_called_with('["or", ["=", "name", "host1"], ["=", "name", "host2"]]')
        # Negated query
        self.query.execute('not host[1-2]')
        mocked_api_call.assert_called_with('["not", ["or", ["=", "name", "host1"], ["=", "name", "host2"]]]')
        # Globbing hosts
        self.query.execute('host1*.domain')
        mocked_api_call.assert_called_with(r'["or", ["~", "name", "^host1.*\\.domain$"]]')

    def test_and(self, mocked_api_call):
        """A query with 'and' should set the boolean property to the current group to 'and'."""
        self.query.execute('host1 and host2')
        assert self.query.current_group['bool'] == 'and'
        mocked_api_call.assert_called_with('["and", ["or", ["=", "name", "host1"]], ["or", ["=", "name", "host2"]]]')

    def test_or(self, mocked_api_call):
        """A query with 'or' should set the boolean property to the current group to 'or'."""
        self.query.execute('host1 or host2')
        assert self.query.current_group['bool'] == 'or'
        mocked_api_call.assert_called_with('["or", ["or", ["=", "name", "host1"]], ["or", ["=", "name", "host2"]]]')

    def test_and_or(self, mocked_api_call):
        """A query with 'and' and 'or' in the same group should raise InvalidQueryError."""
        with pytest.raises(InvalidQueryError, match='boolean operator, current operator was'):
            self.query.execute('host1 and host2 or host3')
            assert not mocked_api_call.called

    def test_and_and(self, mocked_api_call):
        """A query with 'and' and 'and' should set the boolean property to the current group to 'and'."""
        self.query.execute('host1 and host2 and host3')
        assert self.query.current_group['bool'] == 'and'
        mocked_api_call.assert_called_with(
            '["and", ["or", ["=", "name", "host1"]], ["or", ["=", "name", "host2"]], ["or", ["=", "name", "host3"]]]')


@requests_mock.Mocker()
class TestPuppetDBQueryExecute(object):
    """PuppetDBQuery test execute() method class."""

    def setup_method(self, _):
        """Setup an instace of PuppetDBQuery for each test."""
        # pylint: disable=attribute-defined-outside-init
        self.query = puppetdb.PuppetDBQuery({'puppetdb': {'urllib3_disable_warnings': ['SubjectAltNameWarning']}})

    def _register_requests_uris(self, requests):
        """Setup the requests library mock for each test."""
        # Register a requests valid response for each endpoint
        for endpoint, key in self.query.hosts_keys.items():
            requests.register_uri('GET', self.query.url + endpoint + '?query=', status_code=200, json=[
                {key: endpoint + '_host1', 'key': 'value1'}, {key: endpoint + '_host2', 'key': 'value2'}])

        # Register a requests response for a non matching query
        requests.register_uri(
            'GET', self.query.url + self.query.endpoints['F'] + '?query=["or", ["=", "name", "non_existent_host"]]',
            status_code=200, json=[], complete_qs=True)
        # Register a requests response for an invalid query
        requests.register_uri(
            'GET', self.query.url + self.query.endpoints['F'] + '?query=["or", ["=", "name", "invalid_query"]]',
            status_code=400, complete_qs=True)

    def test_nodes_endpoint(self, requests):
        """Calling execute() with a query that goes to the nodes endpoint should return the list of hosts."""
        self._register_requests_uris(requests)
        hosts = self.query.execute('nodes_host[1-2]')
        assert hosts == NodeSet('nodes_host[1-2]')
        assert requests.call_count == 1

    def test_resources_endpoint(self, requests):
        """Calling execute() with a query that goes to the resources endpoint should return the list of hosts."""
        self._register_requests_uris(requests)
        hosts = self.query.execute('R:Class = value')
        assert hosts == NodeSet('resources_host[1-2]')
        assert requests.call_count == 1

    def test_with_boolean_operator(self, requests):
        """Calling execute() with a query with a boolean operator should return the list of hosts."""
        self._register_requests_uris(requests)
        hosts = self.query.execute('nodes_host1 or nodes_host2')
        assert hosts == NodeSet('nodes_host[1-2]')
        assert requests.call_count == 1

    def test_with_subgroup(self, requests):
        """Calling execute() with a query with a subgroup return the list of hosts."""
        self._register_requests_uris(requests)
        hosts = self.query.execute('(nodes_host1 or nodes_host2)')
        assert hosts == NodeSet('nodes_host[1-2]')
        assert requests.call_count == 1

    def test_empty(self, requests):
        """Calling execute() with a query that return no hosts should return an empty list."""
        self._register_requests_uris(requests)
        hosts = self.query.execute('non_existent_host')
        assert hosts == NodeSet()
        assert requests.call_count == 1

    def test_error(self, requests):
        """Calling execute() if the request fails it should raise the requests exception."""
        self._register_requests_uris(requests)
        with pytest.raises(HTTPError):
            self.query.execute('invalid_query')
            assert requests.call_count == 1

    def test_complex_query(self, requests):
        """Calling execute() with a complex query should return the exptected structure."""
        category = 'R'
        endpoint = self.query.endpoints[category]
        key = self.query.hosts_keys[endpoint]
        requests.register_uri('GET', self.query.url + endpoint + '?query=', status_code=200, json=[
            {key: endpoint + '_host1', 'key': 'value1'}, {key: endpoint + '_host2', 'key': 'value2'}])

        hosts = self.query.execute('(resources_host1 or resources_host2) and R:Class = MyClass')
        assert hosts == NodeSet('resources_host[1-2]')
        assert requests.call_count == 1
