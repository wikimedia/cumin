"""Grammar tests."""

import os

from cumin.grammar import grammar
from cumin.tests import get_fixture


def _get_category_key_token(category='F', key='key1', operator='=', value='value1'):
    """Generate and return a category token string and it's expected dictionary of tokens when parsed."""
    expected = {'category': category, 'key': key, 'operator': operator, 'value': value}
    token = '{category}:{key} {operator} {value}'.format(**expected)
    return token, expected


def test_valid_strings():
    """Run quick pyparsing test over valid grammar strings."""
    results = grammar.runTests(get_fixture(os.path.join('grammar', 'valid_grammars.txt'), as_string=True))
    assert results[0]


def test_invalid_strings():
    """Run quick pyparsing test over invalid grammar strings."""
    results = grammar.runTests(
        get_fixture(os.path.join('grammar', 'invalid_grammars.txt'), as_string=True), failureTests=True)
    assert results[0]


def test_single_category_key_token():
    """A valid single token with a category that has key is properly parsed and interpreted."""
    token, expected = _get_category_key_token()
    parsed = grammar.parseString(token, parseAll=True)
    assert parsed[0].asDict() == expected


def test_hosts_selection():
    """A host selection is properly parsed and interpreted."""
    hosts = {'hosts': 'host[10-20,30-40].domain'}
    parsed = grammar.parseString(hosts['hosts'], parseAll=True)
    assert parsed[0].asDict() == hosts
