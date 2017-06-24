"""Transport class tests."""

import os
import pkgutil

import pytest
import mock

from cumin.transport import Transport
from cumin.transports import BaseWorker


def test_invalid_transport():
    """Passing an invalid transport should raise RuntimeError."""
    with pytest.raises(RuntimeError, match=r"ImportError\('No module named non_existent_transport'"):
        Transport.new({'transport': 'non_existent_transport'})


def test_missing_worker_class():
    """Passing a transport without a defined worker_class should raise RuntimeError."""
    module = mock.MagicMock()
    del module.worker_class
    with mock.patch('importlib.import_module', lambda _: module):
        with pytest.raises(RuntimeError, match=r"AttributeError\('worker_class'"):
            Transport.new({'transport': 'invalid_transport'})


def test_valid_transport():
    """Passing a valid transport should return an instance of BaseWorker."""
    transports = [name for _, name, _ in pkgutil.iter_modules([os.path.join('cumin', 'transports')])]
    for transport in transports:
        assert isinstance(Transport.new({'transport': transport}), BaseWorker)
