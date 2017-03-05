"""Transport tests."""
import unittest

import mock

from cumin import transports


class ConcreteBaseWorker(transports.BaseWorker):
    """Concrete class for BaseWorker."""

    def execute(self):
        """Required by BaseWorker"""

    def get_results(self):
        """Required by BaseWorker"""
        yield "node", "output"

    @property
    def mode(self):
        """Required by BaseWorker"""
        return self._mode

    @mode.setter
    def mode(self, value):
        """Required by BaseWorker"""
        self._mode = value

    @property
    def handler(self):
        """Required by BaseWorker"""
        return self._handler

    @handler.setter
    def handler(self, value):
        """Required by BaseWorker"""
        self._handler = value


class TestState(unittest.TestCase):
    """State class tests."""

    def test_instantiation_no_init(self):
        """A new State without an init value should start in the pending state."""
        state = transports.State()
        self.assertEqual(state._state, transports.State.pending)

    def test_instantiation_init_ok(self):
        """A new State with a valid init value should start in this state."""
        state = transports.State(init=transports.State.running)
        self.assertEqual(state._state, transports.State.running)

    def test_instantiation_init_ko(self):
        """A new State with an invalid init value should raise InvalidStateError."""
        with self.assertRaisesRegexp(transports.InvalidStateError, 'is not a valid state'):
            transports.State(init='invalid_state')

    def test_getattr_current(self):
        """Accessing the 'current' property should return the current state."""
        self.assertEqual(transports.State().current, transports.State.pending)

    def test_getattr_is_valid_state(self):
        """Accessing a property named is_{a_valid_state_name} should return a boolean."""
        state = transports.State(init=transports.State.failed)
        self.assertFalse(state.is_pending)
        self.assertFalse(state.is_scheduled)
        self.assertFalse(state.is_running)
        self.assertFalse(state.is_timeout)
        self.assertFalse(state.is_success)
        self.assertTrue(state.is_failed)

    def test_getattr_invalid_property(self):
        """Accessing a property with an invalid name should raise AttributeError."""
        state = transports.State(init=transports.State.failed)
        with self.assertRaisesRegexp(AttributeError, 'object has no attribute'):
            state.invalid_property

    def test_repr(self):
        """A State repr should return its representation that allows to recreate the same State instance."""
        self.assertEqual(
            repr(transports.State()), 'cumin.transports.State(init={state})'.format(state=transports.State.pending))
        state = transports.State.running
        self.assertEqual(
            repr(transports.State(init=state)), 'cumin.transports.State(init={state})'.format(state=state))

    def test_str(self):
        """A State string should return its string representation."""
        self.assertEqual(str(transports.State()), 'pending')
        self.assertEqual(str(transports.State(init=transports.State.running)), 'running')

    def test_cmp_state(self):
        """Two State instance can be compared between each other."""
        state = transports.State()
        greater_state = transports.State(init=transports.State.failed)
        same_state = transports.State()

        self.assertGreater(greater_state, state)
        self.assertGreaterEqual(greater_state, state)
        self.assertGreaterEqual(same_state, state)
        self.assertLess(state, greater_state)
        self.assertLessEqual(state, greater_state)
        self.assertLessEqual(state, same_state)
        self.assertEqual(state, same_state)
        self.assertNotEqual(state, greater_state)

    def test_cmp_int(self):
        """A State instance can be compared with integers."""
        state = transports.State()
        greater_state = transports.State.running
        same_state = transports.State.pending

        self.assertGreater(greater_state, state)
        self.assertGreaterEqual(greater_state, state)
        self.assertGreaterEqual(same_state, state)
        self.assertLess(state, greater_state)
        self.assertLessEqual(state, greater_state)
        self.assertLessEqual(state, same_state)
        self.assertEqual(state, same_state)
        self.assertNotEqual(state, greater_state)

    def test_cmp_invalid(self):
        """Trying to compare a State instance with an invalid object should raise ValueError."""
        state = transports.State()
        invalid_state = 'invalid_state'
        with self.assertRaisesRegexp(ValueError, 'Unable to compare instance'):
            self.assertEqual(state, invalid_state)

    def test_update_invalid_state(self):
        """Trying to update a State with an invalid value should raise ValueError."""
        state = transports.State()
        with self.assertRaisesRegexp(ValueError, 'State must be one of'):
            state.update('invalid_state')

    def test_update_invalid_transition(self):
        """Trying to update a State with an invalid transition should raise StateTransitionError."""
        state = transports.State()
        with self.assertRaisesRegexp(transports.StateTransitionError, 'the allowed states are'):
            state.update(transports.State.failed)

    def test_update_ok(self):
        """Properly updating a State should update it without errors."""
        state = transports.State()
        state.update(transports.State.scheduled)
        self.assertEqual(state.current, transports.State.scheduled)
        state.update(transports.State.running)
        self.assertEqual(state.current, transports.State.running)
        state.update(transports.State.success)
        self.assertEqual(state.current, transports.State.success)
        state.update(transports.State.pending)
        self.assertEqual(state.current, transports.State.pending)


class TestBaseWorker(unittest.TestCase):
    """Concrete BaseWorker class for tests."""

    def test_instantiation(self):
        """Raise if instantiated directly, should return an instance of BaseWorker if inherited."""
        with self.assertRaises(TypeError):
            transports.BaseWorker({})

        self.assertIsInstance(ConcreteBaseWorker({}), transports.BaseWorker)

    @mock.patch.dict(transports.os.environ, {}, clear=True)
    def test_init(self):
        """Constructor should save config and set environment variables."""
        env_dict = {'ENV_VARIABLE': 'env_value'}
        config = {'transport': 'test_transport',
                  'environment': env_dict}

        self.assertEqual(transports.os.environ, {})
        worker = ConcreteBaseWorker(config)
        self.assertEqual(transports.os.environ, env_dict)
        self.assertEqual(worker.config, config)


class TestConcreteBaseWorker(unittest.TestCase):
    """BaseWorker test class."""

    def setUp(self):
        """Initialize default properties and instances."""
        self.worker = ConcreteBaseWorker({})
        self.hosts = ['node1', 'node2']
        self.commands = ['command1', 'command2']

    def test_hosts_getter(self):
        """Access to hosts property should return an empty list if not set and the list of hosts otherwise."""
        self.assertListEqual(self.worker.hosts, [])
        self.worker._hosts = self.hosts
        self.assertListEqual(self.worker.hosts, self.hosts)

    def test_hosts_setter(self):
        """Raise WorkerError if trying to set it not to an iterable, set it otherwise."""
        with self.assertRaisesRegexp(transports.WorkerError, r'hosts must be a list'):
            self.worker.hosts = 'not-list'

        self.worker.hosts = self.hosts
        self.assertListEqual(self.worker._hosts, self.hosts)

    def test_commands_getter(self):
        """Access to commands property should return an empty list if not set and the list of commands otherwise."""
        self.assertListEqual(self.worker.commands, [])
        self.worker._commands = self.commands
        self.assertListEqual(self.worker.commands, self.commands)

    def test_commands_setter(self):
        """Raise WorkerError if trying to set it not to a list, set it otherwise."""
        with self.assertRaisesRegexp(transports.WorkerError, r'commands must be a list'):
            self.worker.commands = 'not-list'

        self.worker.commands = self.commands
        self.assertListEqual(self.worker._commands, self.commands)

    def test_timeout_getter(self):
        """Return default value if not set, the value otherwise."""
        self.assertEqual(self.worker.timeout, 0)
        self.worker._timeout = 10
        self.assertEqual(self.worker.timeout, 10)

    def test_timeout_setter(self):
        """Raise WorkerError if not positive integer, set it otherwise."""
        with self.assertRaisesRegexp(transports.WorkerError, r'timeout must be a positive integer'):
            self.worker.timeout = -1

        with self.assertRaisesRegexp(transports.WorkerError, r'timeout must be a positive integer'):
            self.worker.timeout = '1'

        self.worker.timeout = 10
        self.assertEqual(self.worker._timeout, 10)

    def test_success_threshold_getter(self):
        """Return default value if not set, the value otherwise."""
        self.assertAlmostEqual(self.worker.success_threshold, 1.0)
        self.worker._success_threshold = 0.5
        self.assertAlmostEqual(self.worker.success_threshold, 0.5)

    def test_success_threshold_setter(self):
        """Raise WorkerError if not float between 0 and 1, set it otherwise."""
        message = r'success_threshold must be a float beween 0 and 1'
        with self.assertRaisesRegexp(transports.WorkerError, message):
            self.worker.success_threshold = 1

        with self.assertRaisesRegexp(transports.WorkerError, message):
            self.worker.success_threshold = -0.1

        self.worker.success_threshold = 0.3
        self.assertAlmostEqual(self.worker._success_threshold, 0.3)

    def test_batch_size_getter(self):
        """Return default value if not set, the value otherwise."""
        self.worker.hosts = self.hosts
        self.assertEqual(self.worker.batch_size, len(self.hosts))
        self.worker._batch_size = 1
        self.assertEqual(self.worker.batch_size, 1)

    def test_batch_size_setter(self):
        """Raise WorkerError if not positive integer, set it otherwise forcing it to len(hosts) if greater."""
        with self.assertRaisesRegexp(transports.WorkerError, r'batch_size must be a positive integer'):
            self.worker.batch_size = -1

        self.worker.hosts = self.hosts
        self.worker.batch_size = 10
        self.assertEqual(self.worker._batch_size, len(self.hosts))
        self.worker.batch_size = 1
        self.assertEqual(self.worker._batch_size, 1)

    def test_batch_sleep_getter(self):
        """Return default value if not set, the value otherwise."""
        self.assertAlmostEqual(self.worker.batch_sleep, 0.0)
        self.worker._batch_sleep = 10.0
        self.assertAlmostEqual(self.worker.batch_sleep, 10.0)

    def test_batch_sleep_setter(self):
        """Raise WorkerError if not positive integer, set it otherwise."""
        message = r'batch_sleep must be a positive float'
        with self.assertRaisesRegexp(transports.WorkerError, message):
            self.worker.batch_sleep = -1

        with self.assertRaisesRegexp(transports.WorkerError, message):
            self.worker.batch_sleep = '1'

        self.worker.batch_sleep = 10.0
        self.assertAlmostEqual(self.worker._batch_sleep, 10.0)
