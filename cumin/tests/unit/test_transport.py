"""Transport class tests."""

import pkgutil

import pytest
import mock

from cumin import transports
from cumin.transport import Transport


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


@pytest.mark.parametrize('transport', [name for _, name, ispkg in pkgutil.iter_modules(transports.__path__)
                                       if not ispkg])
def test_valid_transport(transport):
    """Passing a valid transport should return an instance of BaseWorker."""
    assert isinstance(Transport.new({'transport': transport}), transports.BaseWorker)
