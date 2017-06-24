"""Direct backend tests."""

import pytest

from ClusterShell.NodeSet import NodeSet

from cumin.backends import BaseQuery, InvalidQueryError, direct


def test_direct_query_class():
    """An instance of query_class should be an instance of BaseQuery."""
    query = direct.query_class({})
    assert isinstance(query, BaseQuery)


class TestDirectQuery(object):
    """Direct backend query test class."""

    def setup_method(self, _):
        """Setup an instance of DirectQuery for each test."""
        self.query = direct.DirectQuery({})  # pylint: disable=attribute-defined-outside-init

    def test_instantiation(self):
        """An instance of DirectQuery should be an instance of BaseQuery."""
        assert isinstance(self.query, BaseQuery)
        assert self.query.config == {}

    def test_add_category_fact(self):
        """Calling add_category() should raise InvalidQueryError."""
        with pytest.raises(InvalidQueryError, match='Category tokens are not supported'):
            self.query.add_category('F', 'key', 'value')

    def test_add_hosts(self):
        """Calling add_hosts() should add the hosts to the NodeSet."""
        assert list(self.query.hosts) == []
        # No hosts
        self.query.add_hosts(NodeSet.fromlist([]))
        assert list(self.query.hosts) == []
        # Single host
        self.query.add_hosts(NodeSet.fromlist(['host']))
        assert list(self.query.hosts) == ['host']
        # Multiple hosts
        self.query.add_hosts(NodeSet.fromlist(['host1', 'host2']))
        assert list(self.query.hosts) == ['host', 'host1', 'host2']
        # Negated query
        self.query.add_hosts(NodeSet.fromlist(['host1']), neg=True)
        assert list(self.query.hosts) == ['host', 'host2']
        # Globbing is not supported
        with pytest.raises(InvalidQueryError, match='Hosts globbing is not supported'):
            self.query.add_hosts(NodeSet.fromlist(['host1*']))

    def test_open_subgroup(self):
        """Calling open_subgroup() should raise InvalidQueryError."""
        with pytest.raises(InvalidQueryError, matach='Subgroups are not supported'):
            self.query.open_subgroup()

    def test_close_subgroup(self):
        """Calling close_subgroup() should raise InvalidQueryError."""
        with pytest.raises(InvalidQueryError, match='Subgroups are not supported'):
            self.query.close_subgroup()

    def test_add_and(self):
        """Calling add_and() should raise InvalidQueryError."""
        with pytest.raises(InvalidQueryError, match='Boolean AND operator is not supported'):
            self.query.add_and()

    def test_add_or(self):
        """Calling add_or() should be a noop."""
        assert list(self.query.hosts) == []
        self.query.add_or()
        assert list(self.query.hosts) == []

    def test_execute(self):
        """Calling execute() should return the list of hosts."""
        assert list(self.query.hosts) == self.query.execute()
        self.query.add_hosts(NodeSet.fromlist(['host1', 'host2']))
        assert list(self.query.hosts) == self.query.execute()
