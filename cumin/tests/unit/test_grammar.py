"""Grammar tests."""

import os
import sys

from unittest import mock

import pytest

from cumin import CuminError, grammar
from cumin.tests import get_fixture
from cumin.tests.unit.backends.external import ExternalBackendQuery


REGISTERED_BACKENDS = grammar.get_registered_backends()


def test_valid_strings():
    """Run quick pyparsing test over valid grammar strings."""
    results = grammar.grammar(REGISTERED_BACKENDS.keys()).runTests(
        get_fixture(os.path.join('grammar', 'valid_grammars.txt'), as_string=True))
    assert results[0]


def test_invalid_strings():
    """Run quick pyparsing test over invalid grammar strings."""
    results = grammar.grammar(REGISTERED_BACKENDS.keys()).runTests(
        get_fixture(os.path.join('grammar', 'invalid_grammars.txt'), as_string=True), failureTests=True)
    assert results[0]


# Built-in backends registration tests
@mock.patch('cumin.grammar.pkgutil.iter_modules')
def test_duplicate_backend(mocked_iter_modules):
    """Trying to register a backend with the same key of another should raise CuminError."""
    backend = mock.MagicMock()
    backend.GRAMMAR_PREFIX = 'D'
    sys.modules['cumin.backends.test_backend'] = backend
    mocked_iter_modules.return_value = ((None, name, False) for name in ('direct', 'puppetdb', 'test_backend'))
    with pytest.raises(CuminError, match='Unable to register backend'):
        grammar.get_registered_backends()
    del sys.modules['cumin.backends.test_backend']


@mock.patch('cumin.grammar.importlib.import_module')
def test_backend_import_error(mocked_import_modules):
    """If an internal backend raises ImportError because of missing dependencies, it should be skipped."""
    mocked_import_modules.side_effect = ImportError
    backends = grammar.get_registered_backends()
    assert backends == {}


@mock.patch('cumin.grammar.importlib.import_module')
def test_backend_import_error_ext(mocked_import_modules):
    """If an external backend raises ImportError because of missing dependencies, it should raise CuminError."""
    mocked_import_modules.side_effect = ImportError
    with pytest.raises(CuminError, match='Unable to import backend'):
        grammar.get_registered_backends(external=['cumin.tests.unit.backends.external.ok'])


@mock.patch('cumin.grammar.pkgutil.iter_modules')
def test_import_error_backend(mocked_iter_modules):
    """Trying to register a backend that raises ImportError should silently skip it (missing optional dependencies)."""
    # Using a non-existent backend as it will raise ImportError like an existing backend with missing dependencies.
    mocked_iter_modules.return_value = ((None, name, False) for name in ('direct', 'puppetdb', 'non_existent'))
    backends = grammar.get_registered_backends()
    assert len(backends.keys()) == 2
    assert sorted(backends.keys()) == ['D', 'P']


# External backends registration tests
def test_register_ok():
    """An external backend should be properly registered."""
    backends = grammar.get_registered_backends(external=['cumin.tests.unit.backends.external.ok'])
    assert '_Z' in backends
    assert backends['_Z'].keyword == '_Z'
    assert backends['_Z'].name == 'ok'
    assert backends['_Z'].cls == ExternalBackendQuery


def test_register_missing_prefix():
    """Registering an external backend missing the GRAMMAR_PREFIX should raise CuminError."""
    with pytest.raises(CuminError, match='GRAMMAR_PREFIX module attribute not found'):
        grammar.get_registered_backends(external=['cumin.tests.unit.backends.external.missing_grammar_prefix'])


def test_register_duplicate_prefix():
    """Registering an external backend with an already registered GRAMMAR_PREFIX should raise CuminError."""
    with pytest.raises(CuminError, match='already registered'):
        grammar.get_registered_backends(external=['cumin.tests.unit.backends.external.duplicate_prefix'])


def test_register_missing_class():
    """Registering an external backend missing the query_class should raise CuminError."""
    with pytest.raises(CuminError, match='query_class module attribute not found'):
        grammar.get_registered_backends(external=['cumin.tests.unit.backends.external.missing_query_class'])


def test_register_inheritance():
    """Registering an external backend with a query_class with the wrong inheritance should raise CuminError."""
    with pytest.raises(CuminError, match='query_class module attribute is not a subclass'):
        grammar.get_registered_backends(external=['cumin.tests.unit.backends.external.wrong_inheritance'])
