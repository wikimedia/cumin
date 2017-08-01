"""Query handling tests."""

import logging
import pkgutil

import mock
import pytest

from ClusterShell.NodeSet import NodeSet
from pyparsing import ParseException

from cumin import backends
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
        return mock.MagicMock(spec_set=backends.BaseQuery)


class TestQuery(object):
    """Query factory class tests."""

    # pylint: disable=no-self-use

    def test_invalid_backend(self):
        """Passing an invalid backend should raise RuntimeError."""
        with pytest.raises(RuntimeError, match=r"ImportError\('No module named non_existent_backend'"):
            Query.new({'backend': 'non_existent_backend'})

    def test_missing_query_class(self):
        """Passing a backend without a defined query_class should raise RuntimeError."""
        module = mock.MagicMock()
        del module.query_class
        with mock.patch('importlib.import_module', lambda _: module):
            with pytest.raises(RuntimeError, match=r"AttributeError\('query_class'"):
                Query.new({'backend': 'invalid_backend'})

    @pytest.mark.parametrize('backend', [name for _, name, ispkg in pkgutil.iter_modules(backends.__path__)
                                         if not ispkg])
    def test_valid_backend(self, backend):
        """Passing a valid backend should return an instance of BaseQuery."""
        assert isinstance(Query.new({'backend': backend}), backends.BaseQuery)


class TestQueryBuilder(object):
    """Class QueryBuilder tests."""

    query_string = 'host1 or (not F:key1 = value and R:key2 ~ regex) or host2'
    invalid_query_string = 'host1 and or not F:key1 value'
    config = {
        'backend': 'test_backend',
        'test_backend': {
            'aliases': {
                'group1': 'host1 or host10[10-22]',
                'nested_group': 'host10[40-42] or A:group1',
            },
        },
    }

    @mock.patch('cumin.query.Query', QueryFactory)
    def setup_method(self, _):
        """Set method for each test, init a QueryBuilder."""
        self.query_builder = QueryBuilder(self.config)  # pylint: disable=attribute-defined-outside-init

    def test_instantiation(self):
        """Class QueryBuilder should create an instance of a query_class for the given backend."""
        assert isinstance(self.query_builder, QueryBuilder)
        assert isinstance(self.query_builder.query, backends.BaseQuery)
        assert self.query_builder.level is None

    def test_build_valid(self):
        """QueryBuilder.build() should parse and build the query object for a valid query."""
        self.query_builder.build(self.query_string)

        self.query_builder.query.add_hosts.assert_has_calls(
            [mock.call(hosts=NodeSet('host1')), mock.call(hosts=NodeSet('host2'))])
        self.query_builder.query.add_or.assert_has_calls([mock.call(), mock.call()])
        self.query_builder.query.open_subgroup.assert_called_once_with()
        self.query_builder.query.add_category.assert_has_calls([
            mock.call(category='F', key='key1', operator='=', value='value', neg='not'),
            mock.call(category='R', key='key2', operator='~', value='regex')])
        self.query_builder.query.add_and.assert_called_once_with()
        self.query_builder.query.close_subgroup.assert_called_once_with()
        assert self.query_builder.level == 0

    def test_build_valid_with_aliases(self):
        """QueryBuilder.build() should replace any aliases and build the query object for a valid query."""
        self.query_builder.build('host100 or A:group1 or host2')

        self.query_builder.query.add_hosts.assert_has_calls(
            [mock.call(hosts=NodeSet('host100')), mock.call(hosts=NodeSet('host1')),
             mock.call(hosts=NodeSet('host10[10-22]')), mock.call(hosts=NodeSet('host2'))])
        self.query_builder.query.add_or.assert_has_calls([mock.call(), mock.call(), mock.call()])
        self.query_builder.query.open_subgroup.assert_called_once_with()
        self.query_builder.query.close_subgroup.assert_called_once_with()
        assert self.query_builder.level == 0

    def test_build_valid_with_nested_aliases(self):  # pylint: disable=invalid-name
        """QueryBuilder.build() should replace any aliases and build the query object for a valid query."""
        self.query_builder.build('host100 or A:nested_group')

        self.query_builder.query.add_hosts.assert_has_calls(
            [mock.call(hosts=NodeSet('host100')), mock.call(hosts=NodeSet('host10[40-42]')),
             mock.call(hosts=NodeSet('host1')), mock.call(hosts=NodeSet('host10[10-22]'))])
        self.query_builder.query.add_or.assert_has_calls([mock.call(), mock.call()])
        self.query_builder.query.open_subgroup.assert_has_calls([mock.call(), mock.call()])
        self.query_builder.query.close_subgroup.assert_has_calls([mock.call(), mock.call()])
        assert self.query_builder.level == 0

    def test_build_invalid_alias_syntax(self):
        """QueryBuilder.build() should raise InvalidQueryError if an alias has invalid syntax."""
        with pytest.raises(backends.InvalidQueryError, match='Invalid alias syntax, aliases can be only of the form'):
            self.query_builder.build('host1 or A:name = value')

    def test_build_missing_alias(self):
        """QueryBuilder.build() should raise InvalidQueryError if a non existent alias is found."""
        with pytest.raises(backends.InvalidQueryError, match='Unable to find alias replacement for'):
            self.query_builder.build('host1 or A:non_existent_group')

    def test_build_glob_host(self):
        """QueryBuilder.build() should parse a glob host."""
        self.query_builder.build('host1*')
        self.query_builder.query.add_hosts.assert_called_once_with(hosts=NodeSet('host1*'))
        assert self.query_builder.level == 0

    def test_build_invalid(self):
        """QueryBuilder.build() should raise ParseException for an invalid query."""
        with pytest.raises(ParseException, match='Expected end of text'):
            self.query_builder.build(self.invalid_query_string)

    def test_build_subgroup(self):
        """QueryBuilder.build() should open and close a subgroup properly."""
        self.query_builder.build('(host1)')

        self.query_builder.query.add_hosts.assert_has_calls([mock.call(hosts=NodeSet('host1'))])
        self.query_builder.query.open_subgroup.assert_called_once_with()
        self.query_builder.query.close_subgroup.assert_called_once_with()
        assert self.query_builder.level == 0

    def test_build_subgroups(self):
        """QueryBuilder.build() should open and close multiple subgroups properly."""
        self.query_builder.build('(host1 or (host2 or host3))')

        self.query_builder.query.add_hosts.assert_has_calls(
            [mock.call(hosts=NodeSet('host1')), mock.call(hosts=NodeSet('host2')),
             mock.call(hosts=NodeSet('host3'))])
        self.query_builder.query.open_subgroup.assert_has_calls([mock.call(), mock.call()])
        self.query_builder.query.close_subgroup.assert_has_calls([mock.call(), mock.call()])
        assert self.query_builder.level == 0
