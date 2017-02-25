"""Abstract worker tests."""

import os
import unittest

import mock

from cumin.transports import BaseWorker


class ConcreteBaseWorker(BaseWorker):
    """Extend the BaseWorker."""

    def execute(self, hosts, commands, mode=None, handler=None, timeout=0, success_threshold=1):
        """Required by BaseWorker."""

    def get_results(self):
        """Required by BaseWorker."""


class TestBaseWorker(unittest.TestCase):
    """Class BaseWorker tests."""

    def test_instantiation(self):
        """Class BaseWorker rase it instantiated directly, should return an instance of BaseWorker if inherited."""
        with self.assertRaises(TypeError):
            BaseWorker({})

        self.assertIsInstance(ConcreteBaseWorker({}), BaseWorker)

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_init(self):
        """Constructor should save config and set environment variables."""
        env_dict = {'ENV_VARIABLE': 'env_value'}
        config = {'transport': 'test_transport',
                  'test_transport': {'environment': env_dict}}

        self.assertEqual(os.environ, {})
        worker = ConcreteBaseWorker(config)
        self.assertEqual(os.environ, env_dict)
        self.assertEqual(worker.config, config)
