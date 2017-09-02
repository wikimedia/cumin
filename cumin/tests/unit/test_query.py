"""Query handling tests."""
# pylint: disable=invalid-name

import pytest

from cumin import backends, nodeset
from cumin.query import Query


def test_execute_valid_global():
    """Executing a valid query should return the matching hosts."""
    query = Query({})
    hosts = query.execute('D{(host1 or host2) and host[1-5]}')
    assert hosts == nodeset('host[1-2]')


def test_execute_global_or():
    """Executing an 'or' between two queries should return the union of the hosts."""
    query = Query({})
    hosts = query.execute('D{host1} or D{host2}')
    assert hosts == nodeset('host[1-2]')


def test_execute_global_and():
    """Executing an 'and' between two queries should return the intersection of the hosts."""
    query = Query({})
    hosts = query.execute('D{host[1-5]} and D{host2}')
    assert hosts == nodeset('host2')


def test_execute_global_and_not():
    """Executing an 'and not' between two queries should return the difference of the hosts."""
    query = Query({})
    hosts = query.execute('D{host[1-5]} and not D{host2}')
    assert hosts == nodeset('host[1,3-5]')


def test_execute_global_xor():
    """Executing a 'xor' between two queries should return all the hosts that are in only in one of the queries."""
    query = Query({})
    hosts = query.execute('D{host[1-5]} xor D{host[3-7]}')
    assert hosts == nodeset('host[1-2,6-7]')


def test_execute_valid_global_with_aliases():
    """Executing a valid query with aliases should return the matching hosts."""
    query = Query({'aliases': {'group1': 'D{host1 or host2}'}})
    hosts = query.execute('A:group1')
    assert hosts == nodeset('host[1-2]')


def test_execute_valid_global_with_nested_aliases():
    """Executing a valid query with nested aliases should return the matching hosts."""
    query = Query({
        'aliases': {
            'group1': 'D{host1 or host2}',
            'group2': 'D{host3 or host4}',
            'all': 'A:group1 or A:group2',
        }})
    hosts = query.execute('A:all')
    assert hosts == nodeset('host[1-4]')


def test_execute_missing_alias():
    """Executing a valid query with a missing alias should raise InvalidQueryError."""
    query = Query({})
    with pytest.raises(backends.InvalidQueryError, match='Unable to find alias replacement for'):
        query.execute('A:non_existent_group')

    query = Query({'aliases': {}})
    with pytest.raises(backends.InvalidQueryError, match='Unable to find alias replacement for'):
        query.execute('A:non_existent_group')


def test_execute_invalid_global():
    """Executing a query with an invalid syntax should raise InvalidQueryError."""
    query = Query({})
    with pytest.raises(backends.InvalidQueryError, match='with the global grammar'):
        query.execute('invalid syntax')


def test_execute_subgroup():
    """Executing a query with a single subgroup should return the matching hosts."""
    query = Query({})
    hosts = query.execute('(D{host1})')
    assert hosts == nodeset('host1')


def test_execute_subgroups():
    """Executing a query with multiple subgroups should return the matching hosts."""
    query = Query({})
    hosts = query.execute('(D{host1} or D{host2}) and not (D{host1})')
    assert hosts == nodeset('host2')


def test_execute_missing_default_backend():
    """Executing a valid query with a missing default backend should raise InvalidQueryError."""
    query = Query({'default_backend': 'non_existent_backend'})
    with pytest.raises(backends.InvalidQueryError, match='is not registered'):
        query.execute('any_query')


def test_execute_valid_default_backend():
    """Executing a default backend valid query should return the matching hosts."""
    query = Query({'default_backend': 'direct'})
    hosts = query.execute('host1 or host2')
    assert hosts == nodeset('host[1-2]')


def test_execute_invalid_default_valid_global():
    """Executing a global grammar valid query in presence of a default backend should return the matching hosts."""
    query = Query({'default_backend': 'direct'})
    hosts = query.execute('D{host1 or host2}')
    assert hosts == nodeset('host[1-2]')


def test_execute_invalid_default_invalid_global():
    """Executing a query invalid for the default backend and the global grammar should raise InvalidQueryError."""
    query = Query({'default_backend': 'direct'})
    with pytest.raises(backends.InvalidQueryError, match='neither with the default backen'):
        query.execute('invalid syntax')


def test_execute_complex_global():
    """Executing a valid complex query should return the matching hosts."""
    query = Query({})
    hosts = query.execute(
        '(D{(host1 or host2) and host[1-5]}) or ((D{host[100-150]} and not D{host1[20-30]}) and D{host1[01,15,30]})')
    assert hosts == nodeset('host[1-2,101,115]')
