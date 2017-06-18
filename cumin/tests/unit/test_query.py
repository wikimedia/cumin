"""Query handling tests."""

import logging
import os
import pkgutil
import unittest

import mock

from ClusterShell.NodeSet import NodeSet
from pyparsing import ParseException

from cumin.backends import BaseQuery
from cumin.query import Query, QueryBuilder


class QueryFactory(object):
    """Query factory class."""

    @staticmethod
    def new(config, logger=None):
        """Return an instance of the mocked query class."""
        if logger is not None and not isinstance(logger, logging.Logger):
            raise AssertionError('Expected logger parameter to be None or logging instance, got: {logger}'.format(
                logger=logger))
        if not isinstance(config, dict):
            raise AssertionError("Expected instance of dict, got type '{type}' for config.".format(type=type(config)))
        return mock.MagicMock(spec_set=BaseQuery)


class TestQuery(unittest.TestCase):
    """Query factory class tests."""

    def test_invalid_backend(self):
        """Passing an invalid backend should raise RuntimeError."""
        with self.assertRaisesRegexp(RuntimeError, r"ImportError\('No module named non_existent_backend'"):
            Query.new({'backend': 'non_existent_backend'})

    def test_missing_query_class(self):
        """Passing a backend without a defined query_class should raise RuntimeError."""
        module = mock.MagicMock()
        del module.query_class
        with mock.patch('importlib.import_module', lambda _: module):
            with self.assertRaisesRegexp(RuntimeError, r"AttributeError\('query_class'"):
                Query.new({'backend': 'invalid_backend'})

    def test_valid_backend(self):
        """Passing a valid backend should return an instance of BaseQuery."""
        backends = [name for _, name, _ in pkgutil.iter_modules([os.path.join('cumin', 'backends')])]
        for backend in backends:
            self.assertIsInstance(Query.new({'backend': backend}), BaseQuery)


class TestQueryBuilder(unittest.TestCase):
    """Class QueryBuilder tests."""

    query_string = 'host1 or (not F:key1 = value and R:key2 ~ regex) or host2'
    invalid_query_string = 'host1 and or not F:key1 value'
    config = {'backend': 'test_backend'}

    @mock.patch('cumin.query.Query', QueryFactory)
    def test_instantiation(self):
        """Class QueryBuilder should create an instance of a query_class for the given backend."""
        query_builder = QueryBuilder(self.query_string, self.config)
        self.assertIsInstance(query_builder, QueryBuilder)
        self.assertIsInstance(query_builder.query, BaseQuery)
        self.assertEqual(query_builder.query_string, self.query_string)
        self.assertEqual(query_builder.level, 0)

    @mock.patch('cumin.query.Query', QueryFactory)
    def test_build_valid(self):
        """QueryBuilder.build() should parse and build the query object for a valid query."""
        query_builder = QueryBuilder(self.query_string, self.config)
        query_builder.build()

        query_builder.query.add_hosts.assert_has_calls(
            [mock.call(hosts=NodeSet.fromlist(['host1'])), mock.call(hosts=NodeSet.fromlist(['host2']))])
        query_builder.query.add_or.assert_has_calls([mock.call(), mock.call()])
        query_builder.query.open_subgroup.assert_called_once_with()
        query_builder.query.add_category.assert_has_calls([
            mock.call(category='F', key='key1', operator='=', value='value', neg='not'),
            mock.call(category='R', key='key2', operator='~', value='regex')])
        query_builder.query.add_and.assert_called_once_with()
        query_builder.query.close_subgroup.assert_called_once_with()

    @mock.patch('cumin.query.Query', QueryFactory)
    def test_build_glob_host(self):
        """QueryBuilder.build() should parse a glob host."""
        query_builder = QueryBuilder('host1*', self.config)
        query_builder.build()
        query_builder.query.add_hosts.assert_called_once_with(hosts=NodeSet.fromlist(['host1*']))

    @mock.patch('cumin.query.Query', QueryFactory)
    def test_build_invalid(self):
        """QueryBuilder.build() should raise ParseException for an invalid query."""
        query_builder = QueryBuilder(self.invalid_query_string, self.config)
        with self.assertRaisesRegexp(ParseException, r"Expected end of text"):
            query_builder.build()

    @mock.patch('cumin.query.Query', QueryFactory)
    def test__parse_token(self):
        """QueryBuilder._parse_token() should raise RuntimeError for an invalid token."""
        query_builder = QueryBuilder(self.invalid_query_string, self.config)
        with self.assertRaisesRegexp(RuntimeError, r"Invalid query string syntax"):
            query_builder._parse_token('invalid_token')  # pylint: disable=protected-access
