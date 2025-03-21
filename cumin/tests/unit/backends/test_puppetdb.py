"""PuppetDB backend tests."""
from unittest import mock

import pytest

from requests.exceptions import HTTPError

from cumin import nodeset
from cumin.backends import BaseQuery, InvalidQueryError, puppetdb


def test_puppetdb_query_class():
    """An instance of query_class should be an instance of BaseQuery."""
    query = puppetdb.query_class({})
    assert isinstance(query, BaseQuery)


def _get_category_key_token(category='F', key='key1', operator='=', value='value1'):
    """Generate and return a category token string and it's expected dictionary of tokens when parsed."""
    expected = {'category': category, 'key': key, 'operator': operator, 'quoted': value}
    token = '{category}:{key} {operator} {quoted}'.format(**expected)
    return token, expected


def test_single_category_key_token():
    """A valid single token with a category that has key is properly parsed and interpreted."""
    token, expected = _get_category_key_token()
    parsed = puppetdb.grammar().parseString(token, parseAll=True)
    assert parsed[0].asDict() == expected


def test_hosts_selection():
    """A host selection is properly parsed and interpreted."""
    hosts = 'host[10-20,30-40].domain'
    parsed = puppetdb.grammar().parseString(hosts, parseAll=True)
    # Backward compatibility with PyParsing<2.3.1, this check works both with a list or a string
    assert hosts in parsed[0].asDict()['hosts']


class TestPuppetDBQueryV4:
    """PuppetDB backend query test class for API version 4."""

    def setup_method(self, _):
        """Set an instance of PuppetDBQuery for each test."""
        self.query = puppetdb.PuppetDBQuery({})  # pylint: disable=attribute-defined-outside-init

    def test_instantiation(self):
        """An instance of PuppetDBQuery should be an instance of BaseQuery."""
        assert isinstance(self.query, BaseQuery)
        assert self.query.url == 'https://localhost:443/pdb/query/v4/'

    def test_endpoint_getter(self):
        """Access to endpoint property should return nodes by default."""
        assert self.query.endpoint == 'nodes'

    @pytest.mark.parametrize('endpoint', set(puppetdb.PuppetDBQuery.endpoints.values()))
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
class TestPuppetDBQueryBuildV4:
    """PuppetDB backend API v4 query build test class."""

    def setup_method(self, _):
        """Set an instace of PuppetDBQuery for each test."""
        self.query = puppetdb.PuppetDBQuery({})  # pylint: disable=attribute-defined-outside-init

    @pytest.mark.parametrize('query, expected', (
        (  # Base fact
            'F:key=value',
            '["=", ["fact", "key"], "value"]'),
        (  # Negated
            'not F:key = value',
            '["not", ["=", ["fact", "key"], "value"]]'),
        (  # Different operator
            'F:key >= value',
            '[">=", ["fact", "key"], "value"]'),
        (  # Regex with backslash escaped
            r'F:key ~ value\\escaped',
            r'["~", ["fact", "key"], "value\\\\escaped"]'),
        (  # Regex with dot escaped
            r'F:key ~ value\.escaped',
            r'["~", ["fact", "key"], "value\\.escaped"]'),
    ))
    def test_add_category_fact(self, mocked_api_call, query, expected):
        """A fact query should add the proper query token to the current_group."""
        expected = f'["extract", ["certname"], {expected}, ["group_by", "certname"]]'
        self.query.execute(query)
        mocked_api_call.assert_called_with(expected)

    @pytest.mark.parametrize('query, expected', (
        (  # Base fact
            'I:facts.key=value',
            '["=", "facts.key", "value"]'),
        (  # Negated
            'not I:facts.key = value',
            '["not", ["=", "facts.key", "value"]]'),
        (  # Different operator
            'I:facts.key >= value',
            '[">=", "facts.key", "value"]'),
        (  # Regex with backslash escaped
            r'I:facts.key ~ value\\escaped',
            r'["~", "facts.key", "value\\\\escaped"]'),
        (  # Regex with dot escaped
            r'I:facts.key ~ value\.escaped',
            r'["~", "facts.key", "value\\.escaped"]'),
        (  # Fact path with array
            'I:facts.key[0].subkey = value',
            '["=", "facts.key[0].subkey", "value"]'),
        (  # Fact path with dot in the name
            'I:facts.key."sub.key" = value',
            r'["=", "facts.key.\"sub.key\"", "value"]'),
        (  # Multiple query fact and trusted
            'I:facts.key1 = 1 and I:trusted.key2 = 2',
            '["and", ["=", "facts.key1", 1], ["=", "trusted.key2", 2]]'),
    ))
    def test_add_category_inventory(self, mocked_api_call, query, expected):
        """An inventory query should add the proper query token to the current_group."""
        expected = f'["extract", ["certname"], {expected}, ["group_by", "certname"]]'
        self.query.execute(query)
        mocked_api_call.assert_called_with(expected)

    @pytest.mark.parametrize('query, expected', (
        (  # Base resource equality
            'R:key = value',
            '["and", ["=", "type", "Key"], ["=", "title", "value"]]'),
        (  # Class title
            'R:class = classtitle',
            '["and", ["=", "type", "Class"], ["=", "title", "Classtitle"]]'),
        (  # Class path
            'R:class = resource::path::to::class',
            '["and", ["=", "type", "Class"], ["=", "title", "Resource::Path::To::Class"]]'),
        (  # Negated
            'not R:key = value',
            '["not", ["and", ["=", "type", "Key"], ["=", "title", "value"]]]'),
        (  # Regex backslash escaped
            r'R:key ~ value\\escaped',
            r'["and", ["=", "type", "Key"], ["~", "title", "value\\\\escaped"]]'),
        (  # Regex dot escaped
            r'R:key ~ value\.escaped',
            r'["and", ["=", "type", "Key"], ["~", "title", "value\\.escaped"]]'),
        (  # Regex class
            r'R:Class ~ "Role::(One|Another)"',
            r'["and", ["=", "type", "Class"], ["~", "title", "Role::(One|Another)"]]'),
        (  # Resource parameter
            'R:resource%param = value',
            '["and", ["=", "type", "Resource"], ["=", ["parameter", "param"], "value"]]'),
        (  # Resource parameter regex
            'R:resource%param ~ value.*',
            '["and", ["=", "type", "Resource"], ["~", ["parameter", "param"], "value.*"]]'),
        (  # Resource field
            'R:resource@field = value',
            '["and", ["=", "type", "Resource"], ["=", "field", "value"]]'),
        (  # Resource type
            'R:Resource',
            '["and", ["=", "type", "Resource"]]'),
        (  # Class shortcut
            'C:class_name',
            '["and", ["=", "type", "Class"], ["=", "title", "Class_name"]]'),
        (  # Class shortcut with path
            'C:module::class::name',
            '["and", ["=", "type", "Class"], ["=", "title", "Module::Class::Name"]]'),
        (  # Class shortcut with parameter
            'C:class_name%param = value',
            ('["and", ["and", ["=", "type", "Class"], ["=", "title", "Class_name"]], '
             '["and", ["=", "type", "Class"], ["=", ["parameter", "param"], "value"]]]')),
        (  # Class shortcut with field
            'C:class_name@field = value',
            ('["and", ["and", ["=", "type", "Class"], ["=", "title", "Class_name"]], '
             '["and", ["=", "type", "Class"], ["=", "field", "value"]]]')),
        (  # Profile shortcut
            'P:profile_name',
            '["and", ["=", "type", "Class"], ["=", "title", "Profile::Profile_name"]]'),
        (  # Profile shortcut path
            'P:module::name',
            '["and", ["=", "type", "Class"], ["=", "title", "Profile::Module::Name"]]'),
        (  # Profile shortcut with parameter
            'P:profile_name%param = value',
            ('["and", ["and", ["=", "type", "Class"], ["=", "title", "Profile::Profile_name"]], '
             '["and", ["=", "type", "Class"], ["=", ["parameter", "param"], "value"]]]')),
        (  # Profile shortcut with field
            'P:profile_name@field = value',
            ('["and", ["and", ["=", "type", "Class"], ["=", "title", "Profile::Profile_name"]], '
             '["and", ["=", "type", "Class"], ["=", "field", "value"]]]')),
        (  # Role shortcut
            'O:role_name',
            '["and", ["=", "type", "Class"], ["=", "title", "Role::Role_name"]]'),
        (  # Role shortcut path
            'O:module::name',
            '["and", ["=", "type", "Class"], ["=", "title", "Role::Module::Name"]]'),
        (  # Role shortcut with parameter
            'O:role_name%param = value',
            ('["and", ["and", ["=", "type", "Class"], ["=", "title", "Role::Role_name"]], '
             '["and", ["=", "type", "Class"], ["=", ["parameter", "param"], "value"]]]')),
        (  # Role shortcut with field
            'O:role_name@field = value',
            ('["and", ["and", ["=", "type", "Class"], ["=", "title", "Role::Role_name"]], '
             '["and", ["=", "type", "Class"], ["=", "field", "value"]]]')),
    ))
    def test_add_category_resource(self, mocked_api_call, query, expected):
        """A resource query should add the proper query token to the current_group."""
        expected = f'["extract", ["certname"], {expected}, ["group_by", "certname"]]'
        self.query.execute(query)
        mocked_api_call.assert_called_with(expected)

    @pytest.mark.parametrize('query, message', (
        (  # Parameter and field
            'R:resource%param@field',
            'Resource key cannot contain both'),
        (  # Field and parameter
            'R:resource@field%param',
            'Resource key cannot contain both'),
        (  # Class shortcut with value
            'C:class_name = value',
            'The matching of a value is accepted only when using'),
        (  # Class shortcut with parameter and field
            'C:class_name%param@field',
            'Resource key cannot contain both'),
        (  # Class shortcut with field and parameter
            'C:class_name@field%param',
            'Resource key cannot contain both'),
        (  # Profile shortcut value
            'P:profile_name = value',
            'The matching of a value is accepted only when using'),
        (  # Profile shortcut with parameter and field
            'P:profile_name%param@field',
            'Resource key cannot contain both'),
        (  # Profile shortcut with field and parameter
            'P:profile_name@field%param',
            'Resource key cannot contain both'),
        (  # Role shortcut with value
            'O:role_name = value',
            'The matching of a value is accepted only when using'),
        (  # Role shortcut with parameter and field
            'O:role_name%param@field',
            'Resource key cannot contain both'),
        (  # Role shortcut with field and parameter
            'O:role_name@field%param',
            'Resource key cannot contain both'),
    ))
    def test_add_category_resource_raise(self, mocked_api_call, query, message):
        """A query with both a resource's parameter and field should raise InvalidQueryError."""
        with pytest.raises(InvalidQueryError, match=message):
            self.query.execute(query)
            assert not mocked_api_call.called

    @pytest.mark.parametrize('query, expected', (
        (  # No hosts
            'host1!host1',
            ''),
        (  # Single host
            'host',
            '["or", ["=", "certname", "host"]]'),
        (  # Multiple hosts
            'host[1-2]',
            '["or", ["=", "certname", "host1"], ["=", "certname", "host2"]]'),
        (  # Negated query
            'not host[1-2]',
            '["not", ["or", ["=", "certname", "host1"], ["=", "certname", "host2"]]]'),
        (  # Globbing hosts
            'host1*.domain',
            r'["or", ["~", "certname", "^host1.*\\.domain$"]]'),
    ))
    def test_add_hosts(self, mocked_api_call, query, expected):
        """A host query should add the proper query token to the current_group."""
        expected = f'["extract", ["certname"], {expected}, ["group_by", "certname"]]'
        self.query.execute(query)
        mocked_api_call.assert_called_with(expected)

    @pytest.mark.parametrize('query, operator, expected', (
        (  # AND
            'host1 and host2',
            'and',
            '["and", ["or", ["=", "certname", "host1"]], ["or", ["=", "certname", "host2"]]]'),
        (  # OR
            'host1 or host2',
            'or',
            '["or", ["or", ["=", "certname", "host1"]], ["or", ["=", "certname", "host2"]]]'),
        (  # Multiple AND
            'host1 and host2 and host3',
            'and',
            (
                '["and", ["or", ["=", "certname", "host1"]], ["or", ["=", "certname", "host2"]], '
                '["or", ["=", "certname", "host3"]]]')),
    ))
    def test_operator(self, mocked_api_call, query, operator, expected):
        """A query with boolean operators should set the boolean property to the current group."""
        expected = f'["extract", ["certname"], {expected}, ["group_by", "certname"]]'
        self.query.execute(query)
        assert self.query.current_group['bool'] == operator
        mocked_api_call.assert_called_with(expected)

    def test_and_or(self, mocked_api_call):
        """A query with 'and' and 'or' in the same group should raise InvalidQueryError."""
        with pytest.raises(InvalidQueryError, match='boolean operator, current operator was'):
            self.query.execute('host1 and host2 or host3')
            assert not mocked_api_call.called


@pytest.mark.parametrize('query, expected', (
    ('nodes_host[1-2]', 'nodes_host[1-2]'),  # Nodes
    ('R:Class = value', 'resources_host[1-2]'),  # Resources
    ('I:facts.structured.property = value', 'inventory_host[1-2]'),  # Inventory
    ('nodes_host1 or nodes_host2', 'nodes_host[1-2]'),  # Nodes with AND
    ('(nodes_host1 or nodes_host2)', 'nodes_host[1-2]'),  # Nodes with subgroup
    ('non_existent_host', None),  # No match
))
def test_endpoints(query_requests, query, expected):
    """Calling execute() with a query should go to the proper endpoint and return the list of hosts."""
    hosts = query_requests[0].execute(query)
    assert hosts == nodeset(expected)
    assert query_requests[1].call_count == 1


def test_error(query_requests):
    """Calling execute() if the request fails it should raise the requests exception."""
    with pytest.raises(HTTPError):
        query_requests[0].execute('invalid_query')
        assert query_requests[1].call_count == 1


def test_complex_query(query_requests):
    """Calling execute() with a complex query should return the expected structure."""
    category = 'R'
    endpoint = query_requests[0].endpoints[category]
    query_requests[1].register_uri('POST', query_requests[0].url + endpoint + '?query=', status_code=200, json=[
        {'certname': endpoint + '_host1', 'key': 'value1'}, {'certname': endpoint + '_host2', 'key': 'value2'}])

    hosts = query_requests[0].execute('(resources_host1 or resources_host2) and R:Class = MyClass')
    assert hosts == nodeset('resources_host[1-2]')
    assert query_requests[1].call_count == 1
