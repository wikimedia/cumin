"""OpenStack backend tests."""
from collections import namedtuple
from unittest import mock

from cumin import nodeset
from cumin.backends import BaseQuery, openstack


Project = namedtuple('Project', ['name'])
Server = namedtuple('Server', ['name'])


def test_openstack_query_class():
    """An instance of query_class should be an instance of BaseQuery."""
    query = openstack.query_class({})
    assert isinstance(query, BaseQuery)


def test_openstack_query_class_init():
    """An instance of OpenStackQuery should be an instance of BaseQuery."""
    config = {'key': 'value'}
    query = openstack.OpenStackQuery(config)
    assert isinstance(query, BaseQuery)
    assert query.config == config


def test_all_selection():
    """A selection for all hosts is properly parsed and interpreted."""
    parsed = openstack.grammar().parseString('*', parseAll=True)
    assert parsed[0].asDict() == {'all': '*'}


def test_key_value_token():
    """A token is properly parsed and interpreted."""
    parsed = openstack.grammar().parseString('project:project_name', parseAll=True)
    assert parsed[0].asDict() == {'key': 'project', 'value': 'project_name'}


def test_key_value_tokens():
    """Multiple tokens are properly parsed and interpreted."""
    parsed = openstack.grammar().parseString('project:project_name name:hostname', parseAll=True)
    assert parsed[0].asDict() == {'key': 'project', 'value': 'project_name'}
    assert parsed[1].asDict() == {'key': 'name', 'value': 'hostname'}


@mock.patch('cumin.backends.openstack.nova_client.Client')
@mock.patch('cumin.backends.openstack.keystone_client.Client')
@mock.patch('cumin.backends.openstack.keystone_session.Session')
@mock.patch('cumin.backends.openstack.keystone_identity.Password')
class TestOpenStackQuery(object):
    """OpenStack backend query test class."""

    def setup_method(self, _):
        """Set an instance of OpenStackQuery for each test."""
        self.config = {'openstack': {}}  # pylint: disable=attribute-defined-outside-init
        self.query = openstack.OpenStackQuery(self.config)  # pylint: disable=attribute-defined-outside-init

    def test_execute_all(self, keystone_identity, keystone_session, keystone_client, nova_client):
        """Calling execute() with a query that select all hosts should return the list of all hosts."""
        keystone_client.return_value.projects.list.return_value = [Project('project1'), Project('project2')]
        nova_client.return_value.servers.list.side_effect = [
            [Server('host1'), Server('host2')], [Server('host1'), Server('host2')]]

        hosts = self.query.execute('*')
        assert hosts == nodeset('host[1-2].project[1-2]')

        assert keystone_identity.call_count == 3
        assert keystone_session.call_count == 3
        keystone_client.assert_called_once_with(session=keystone_session(), timeout=10)
        assert nova_client.call_args_list == [
            mock.call('2', endpoint_type='public', session=keystone_session(), timeout=10),
            mock.call('2', endpoint_type='public', session=keystone_session(), timeout=10)]
        assert nova_client().servers.list.call_args_list == [
            mock.call(search_opts={'vm_state': 'ACTIVE', 'status': 'ACTIVE'})] * 2

    def test_execute_project(self, keystone_identity, keystone_session, keystone_client, nova_client):
        """Calling execute() with a query that select all hosts in a project should return the list of hosts."""
        nova_client.return_value.servers.list.return_value = [Server('host1'), Server('host2')]

        hosts = self.query.execute('project:project1')
        assert hosts == nodeset('host[1-2].project1')

        assert keystone_identity.call_count == 1
        assert keystone_session.call_count == 1
        keystone_client.assert_not_called()
        nova_client.assert_called_once_with('2', endpoint_type='public', session=keystone_session(), timeout=10)
        nova_client().servers.list.assert_called_once_with(search_opts={'vm_state': 'ACTIVE', 'status': 'ACTIVE'})

    def test_execute_project_name(self, keystone_identity, keystone_session, keystone_client, nova_client):
        """Calling execute() with a query that select hosts matching a name in a project should return only those."""
        nova_client.return_value.servers.list.return_value = [Server('host1'), Server('host2')]

        hosts = self.query.execute('project:project1 name:host')
        assert hosts == nodeset('host[1-2].project1')

        assert keystone_identity.call_count == 1
        assert keystone_session.call_count == 1
        keystone_client.assert_not_called()
        nova_client.assert_called_once_with('2', endpoint_type='public', session=keystone_session(), timeout=10)
        nova_client().servers.list.assert_called_once_with(
            search_opts={'vm_state': 'ACTIVE', 'status': 'ACTIVE', 'name': 'host'})

    def test_execute_project_domain(self, keystone_identity, keystone_session, keystone_client, nova_client):
        """When the domain suffix is configured, it should append it to all hosts."""
        nova_client.return_value.servers.list.return_value = [Server('host1'), Server('host2')]
        self.config['openstack']['domain_suffix'] = 'servers.local'
        query = openstack.OpenStackQuery(self.config)

        hosts = query.execute('project:project1')
        assert hosts == nodeset('host[1-2].project1.servers.local')

        assert keystone_identity.call_count == 1
        assert keystone_session.call_count == 1
        keystone_client.assert_not_called()

    def test_execute_project_dot_domain(self, keystone_identity, keystone_session, keystone_client, nova_client):
        """When the domain suffix is configured with a dot, it should append it to all hosts without the dot."""
        nova_client.return_value.servers.list.return_value = [Server('host1'), Server('host2')]
        self.config['openstack']['domain_suffix'] = '.servers.local'
        query = openstack.OpenStackQuery(self.config)

        hosts = query.execute('project:project1')
        assert hosts == nodeset('host[1-2].project1.servers.local')

        assert keystone_identity.call_count == 1
        assert keystone_session.call_count == 1
        keystone_client.assert_not_called()

    def test_execute_query_params(self, keystone_identity, keystone_session, keystone_client, nova_client):
        """When the query_params are set, they must be loaded automatically."""
        nova_client.return_value.servers.list.return_value = [Server('host1'), Server('host2')]
        self.config['openstack']['query_params'] = {'project': 'project1'}
        query = openstack.OpenStackQuery(self.config)

        hosts = query.execute('*')
        assert hosts == nodeset('host[1-2].project1')

        assert keystone_identity.call_count == 1
        assert keystone_session.call_count == 1
        keystone_client.assert_not_called()
