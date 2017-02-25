"""Direct backend tests"""
import unittest

from ClusterShell.NodeSet import NodeSet

from cumin.backends import BaseQuery, InvalidQueryError, direct


class TestDirectQueryClass(unittest.TestCase):
    """Direct backend query_class test class"""

    def test_query_class(self):
        """An instance of query_class should be an instance of BaseQuery"""
        query = direct.query_class({})
        self.assertIsInstance(query, BaseQuery)


class TestDirectQuery(unittest.TestCase):
    """Direct backend query test class"""

    def setUp(self):
        """Setup an instace of DirectQuery for each test"""
        self.query = direct.DirectQuery({})

    def test_instantiation(self):
        """An instance of DirectQuery should be an instance of BaseQuery"""
        self.assertIsInstance(self.query, BaseQuery)
        self.assertDictEqual(self.query.config, {})

    def test_add_category_fact(self):
        """Calling add_category() should raise InvalidQueryError"""
        with self.assertRaisesRegexp(InvalidQueryError, r"Category tokens are not supported"):
            self.query.add_category('F', 'key', 'value')

    def test_add_hosts(self):
        """Calling add_hosts() should add the hosts to the NodeSet"""
        self.assertListEqual(list(self.query.hosts), [])
        # No hosts
        self.query.add_hosts(NodeSet.fromlist([]))
        self.assertListEqual(list(self.query.hosts), [])
        # Single host
        self.query.add_hosts(NodeSet.fromlist(['host']))
        self.assertListEqual(list(self.query.hosts), ['host'])
        # Multiple hosts
        self.query.add_hosts(NodeSet.fromlist(['host1', 'host2']))
        self.assertListEqual(list(self.query.hosts), ['host', 'host1', 'host2'])
        # Negated query
        self.query.add_hosts(NodeSet.fromlist(['host1']), neg=True)
        self.assertListEqual(list(self.query.hosts), ['host', 'host2'])
        # Globbing is not supported
        with self.assertRaisesRegexp(InvalidQueryError, r"Hosts globbing is not supported"):
            self.query.add_hosts(NodeSet.fromlist(['host1*']))

    def test_open_subgroup(self):
        """Calling open_subgroup() should raise InvalidQueryError"""
        with self.assertRaisesRegexp(InvalidQueryError, r"Subgroups are not supported"):
            self.query.open_subgroup()

    def test_close_subgroup(self):
        """Calling close_subgroup() should raise InvalidQueryError"""
        with self.assertRaisesRegexp(InvalidQueryError, r"Subgroups are not supported"):
            self.query.close_subgroup()

    def test_add_and(self):
        """Calling add_and() should raise InvalidQueryError"""
        with self.assertRaisesRegexp(InvalidQueryError, r"Boolean AND operator is not supported"):
            self.query.add_and()

    def test_add_or(self):
        """Calling add_or() should be a noop"""
        self.assertListEqual(list(self.query.hosts), [])
        self.query.add_or()
        self.assertListEqual(list(self.query.hosts), [])

    def test_execute(self):
        """Calling execute() should return the list of hosts"""
        self.assertListEqual(list(self.query.hosts), self.query.execute())
        self.query.add_hosts(NodeSet.fromlist(['host1', 'host2']))
        self.assertListEqual(list(self.query.hosts), self.query.execute())
