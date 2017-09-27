"""Transport class tests."""

import pkgutil

import pytest
import mock

from cumin import CuminError, transports
from cumin.transport import Transport


def test_missing_transport():
    """Not passing a transport should raise CuminError."""
    with pytest.raises(CuminError, match=r"Missing required parameter 'transport'"):
        Transport.new({}, transports.Target([]))


def test_invalid_transport():
    """Passing an invalid transport should raise CuminError."""
    with pytest.raises(ImportError, match=r'No module named non_existent_transport'):
        Transport.new({'transport': 'non_existent_transport'}, transports.Target([]))


def test_missing_worker_class():
    """Passing a transport without a defined worker_class should raise CuminError."""
    module = mock.MagicMock()
    del module.worker_class
    with mock.patch('importlib.import_module', lambda _: module):
        with pytest.raises(AttributeError, match=r'worker_class'):
            Transport.new({'transport': 'invalid_transport'}, transports.Target([]))


@pytest.mark.parametrize('transport', [name for _, name, ispkg in pkgutil.iter_modules(transports.__path__)
                                       if not ispkg])
def test_valid_transport(transport):
    """Passing a valid transport should return an instance of BaseWorker."""
    assert isinstance(Transport.new({'transport': transport}, transports.Target([])), transports.BaseWorker)
