"""Grammar tests."""

import os
import sys

import mock
import pytest

from cumin import CuminError, grammar
from cumin.tests import get_fixture


def test_valid_strings():
    """Run quick pyparsing test over valid grammar strings."""
    results = grammar.grammar().runTests(get_fixture(os.path.join('grammar', 'valid_grammars.txt'), as_string=True))
    assert results[0]


def test_invalid_strings():
    """Run quick pyparsing test over invalid grammar strings."""
    results = grammar.grammar().runTests(
        get_fixture(os.path.join('grammar', 'invalid_grammars.txt'), as_string=True), failureTests=True)
    assert results[0]


@mock.patch('cumin.grammar.pkgutil.iter_modules')
def test_duplicate_backend(mocked_iter_modules):
    """."""
    backend = mock.MagicMock()
    backend.GRAMMAR_PREFIX = 'D'
    sys.modules['cumin.backends.test_backend'] = backend
    mocked_iter_modules.return_value = ((None, name, False) for name in ('direct', 'puppetdb', 'test_backend'))
    with pytest.raises(CuminError, match='Unable to register backend'):
        grammar.get_registered_backends()
