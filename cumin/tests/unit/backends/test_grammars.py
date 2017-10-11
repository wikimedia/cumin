"""Backends basic grammar tests."""
import importlib
import os
import pkgutil

import pytest

from cumin import backends
from cumin.tests import get_fixture


BACKENDS = [name for _, name, ispkg in pkgutil.iter_modules(backends.__path__) if not ispkg]
BASE_PATH = os.path.join('backends', 'grammars')


@pytest.mark.parametrize('backend_name', BACKENDS)
def test_valid_grammars(backend_name):
    """Run quick pyparsing test over valid grammar strings for each backend that has the appropriate fixture."""
    try:
        backend = importlib.import_module('cumin.backends.{backend}'.format(backend=backend_name))
    except ImportError:
        return  # Backend not available

    results = backend.grammar().runTests(
        get_fixture(os.path.join(BASE_PATH, '{backend}_valid.txt'.format(backend=backend_name)), as_string=True))
    assert results[0]


@pytest.mark.parametrize('backend_name', BACKENDS)
def test_invalid_grammars(backend_name):
    """Run quick pyparsing test over invalid grammar strings for each backend that has the appropriate fixture."""
    try:
        backend = importlib.import_module('cumin.backends.{backend}'.format(backend=backend_name))
    except ImportError:
        return  # Backend not available

    results = backend.grammar().runTests(
        get_fixture(os.path.join(BASE_PATH, '{backend}_invalid.txt'.format(backend=backend_name)), as_string=True),
        failureTests=True)
    assert results[0]
