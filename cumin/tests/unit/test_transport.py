import os
import pkgutil
import unittest

import mock

from cumin.transport import Transport
from cumin.transports import BaseWorker


class TestTransport(unittest.TestCase):
    """Transport factory class tests"""

    def test_invalid_transport(self):
        """Passing an invalid transport should raise RuntimeError"""
        with self.assertRaisesRegexp(RuntimeError, r"ImportError\('No module named non_existent_transport'"):
            Transport.new({'transport': 'non_existent_transport'})

    def test_missing_worker_class(self):
        """Passing a transport without a defined worker_class should raise RuntimeError"""
        module = mock.MagicMock()
        del module.worker_class
        with mock.patch('importlib.import_module', lambda _: module):
            with self.assertRaisesRegexp(RuntimeError, r"AttributeError\('worker_class'"):
                Transport.new({'transport': 'invalid_transport'})

    def test_valid_transport(self):
        """Passing a valid transport should return an instance of BaseWorker"""
        transports = [name for _, name, _ in pkgutil.iter_modules([os.path.join('cumin', 'transports')])]
        for transport in transports:
            self.assertIsInstance(Transport.new({'transport': transport}), BaseWorker)
