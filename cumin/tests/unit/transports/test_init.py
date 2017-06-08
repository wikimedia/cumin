"""Transport tests."""
import unittest

import mock

import cumin  # noqa: F401 (dynamically used in TestCommand)

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


class TestCommand(unittest.TestCase):
    """Command class tests."""

    def setUp(self):
        command_with_options = 'command --with "options" -a -n -d params with\ spaces'
        self.same_command_a = transports.Command(command_with_options)
        self.same_command_b = "command  --with  'options'  -a  -n  -d  params  with\ spaces"
        command_with_nested_quotes = 'command --with \'nested "quotes"\' -a -n -d params with\ spaces'

        self.commands = [
            {'command': 'command1'},
            {'command': 'command1', 'timeout': 5},
            {'command': 'command1', 'ok_codes': [0, 255]},
            {'command': 'command1', 'timeout': 5, 'ok_codes': [0, 255]},
            {'command': command_with_options},
            {'command': command_with_options, 'timeout': 5},
            {'command': command_with_options, 'ok_codes': [0, 255]},
            {'command': command_with_options, 'timeout': 5, 'ok_codes': [0, 255]},
            {'command': command_with_nested_quotes},
            {'command': command_with_nested_quotes, 'timeout': 5},
            {'command': command_with_nested_quotes, 'ok_codes': [0, 255]},
            {'command': command_with_nested_quotes, 'timeout': 5, 'ok_codes': [0, 255]},
        ]
        self.different_command = "command  --with  'other options'  -a  -n  -d  other_params  with\ spaces"
        for command in self.commands:
            command['obj'] = transports.Command(
                command['command'], timeout=command.get('timeout', None), ok_codes=command.get('ok_codes', None))

    def test_instantiation(self):
        """A new Command instance should set the command property to the given command."""
        for command in self.commands:
            self.assertIsInstance(command['obj'], transports.Command)
            self.assertEqual(command['obj'].command, command['command'])
            self.assertEqual(command['obj']._timeout, command.get('timeout', None))
            self.assertEqual(command['obj']._ok_codes, command.get('ok_codes', None))

    def test_repr(self):
        """A repr of a Command should allow to instantiate an instance with the same properties."""
        for command in self.commands:
            command_instance = eval(repr(command['obj']))
            self.assertIsInstance(command_instance, transports.Command)
            self.assertEqual(repr(command_instance), repr(command['obj']))
            self.assertEqual(command_instance.command, command['obj'].command)
            self.assertEqual(command_instance._timeout, command['obj']._timeout)
            self.assertEqual(command_instance._ok_codes, command['obj']._ok_codes)

    def test_str(self):
        """A cast to string of a Command should return its command."""
        for command in self.commands:
            self.assertEqual(str(command['obj']), command['command'])

    def test_eq(self):
        """A Command instance can be compared to another or to a string with the equality operator."""
        for command in self.commands:
            self.assertEqual(command['obj'], transports.Command(
                command['command'], timeout=command.get('timeout', None), ok_codes=command.get('ok_codes', None)))

            if command.get('timeout', None) is None and command.get('ok_codes', None) is None:
                self.assertEqual(command['obj'], command['command'])

            with self.assertRaisesRegexp(ValueError, 'Unable to compare instance of'):
                command['obj'] == 1

        self.assertEqual(self.same_command_a, self.same_command_b)

    def test_ne(self):
        """A Command instance can be compared to another or to a string with the inequality operator."""
        # Just a basic test, all the cases are covered by the test_eq test
        for command in self.commands:
            # Different command with same or differnt properties
            self.assertNotEqual(command['obj'], transports.Command(
                self.different_command, timeout=command.get('timeout', None), ok_codes=command.get('ok_codes', None)))
            self.assertNotEqual(command['obj'], transports.Command(
                self.different_command, timeout=999, ok_codes=command.get('ok_codes', None)))
            self.assertNotEqual(command['obj'], transports.Command(
                self.different_command, timeout=command.get('timeout', None), ok_codes=[99]))
            self.assertNotEqual(command['obj'], transports.Command(self.different_command, timeout=999, ok_codes=[99]))
            self.assertNotEqual(command['obj'], self.different_command)

            # Same command, properties different
            self.assertNotEqual(command['obj'], transports.Command(
                command['command'], timeout=999, ok_codes=command.get('ok_codes', None)))
            self.assertNotEqual(command['obj'], transports.Command(
                command['command'], timeout=command.get('timeout', None), ok_codes=[99]))
            self.assertNotEqual(command['obj'], transports.Command(command['command'], timeout=999, ok_codes=[99]))

            if command.get('timeout', None) is not None or command.get('ok_codes', None) is not None:
                self.assertNotEqual(command['obj'], command['command'])

            with self.assertRaisesRegexp(ValueError, 'Unable to compare instance of'):
                command['obj'] == 1

    def test_timeout_getter(self):
        """Should return the timeout set, None otherwise."""
        for command in self.commands:
            self.assertAlmostEqual(command['obj'].timeout, command['obj']._timeout)

    def test_timeout_setter(self):
        """Should set the timeout to its value, converted to float if integer. Unset it if None is passed."""
        command = transports.Command('command1')
        command.timeout = 1.0
        self.assertAlmostEqual(command._timeout, 1.0)
        command.timeout = None
        self.assertIsNone(command._timeout)
        command.timeout = 1
        self.assertAlmostEqual(command._timeout, 1.0)
        with self.assertRaisesRegexp(transports.WorkerError, 'timeout must be a positive float'):
            command.timeout = -1.0

    def test_ok_codes_getter(self):
        """Should return the ok_codes set, [0] otherwise."""
        for command in self.commands:
            self.assertListEqual(command['obj'].ok_codes, command.get('ok_codes', [0]))

    def test_ok_codes_setter(self):
        """Should set the ok_codes to its value, unset it if None is passed."""
        command = transports.Command('command1')
        self.assertIsNone(command._ok_codes)
        for i in xrange(256):
            codes = [i]
            command.ok_codes = codes
            self.assertListEqual(command._ok_codes, codes)
            codes.insert(0, 0)
            command.ok_codes = codes
            self.assertListEqual(command._ok_codes, codes)

        command.ok_codes = None
        self.assertIsNone(command._ok_codes)

        with self.assertRaisesRegexp(transports.WorkerError, r'ok_codes must be a list or None'):
            command.ok_codes = 'invalid_value'

        for i in (-1, 0.0, 100.0, 256, 'invalid_value'):
            codes = [i]
            with self.assertRaisesRegexp(transports.WorkerError, r'must be a list of integers in the range'):
                command.ok_codes = codes

            codes.insert(0, 0)
            with self.assertRaisesRegexp(transports.WorkerError, r'must be a list of integers in the range'):
                command.ok_codes = codes


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
        self.commands = [transports.Command('command1'), transports.Command('command2')]

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
        self.worker._commands = None
        self.assertListEqual(self.worker.commands, [])

    def test_commands_setter(self):
        """Raise WorkerError if trying to set it not to a list, set it otherwise."""
        with self.assertRaisesRegexp(transports.WorkerError, r'commands must be a list'):
            self.worker.commands = 'invalid_value'

        with self.assertRaisesRegexp(transports.WorkerError, r'commands must be a list of Command objects or strings'):
            self.worker.commands = [1, 'command2']

        self.worker.commands = self.commands
        self.assertListEqual(self.worker._commands, self.commands)
        self.worker.commands = None
        self.assertIsNone(self.worker._commands)
        self.worker.commands = ['command1', 'command2']
        self.assertListEqual(self.worker._commands, self.commands)

    def test_timeout_getter(self):
        """Return default value if not set, the value otherwise."""
        self.assertEqual(self.worker.timeout, 0)
        self.worker._timeout = 10
        self.assertEqual(self.worker.timeout, 10)

    def test_timeout_setter(self):
        """Raise WorkerError if not a positive integer, set it otherwise."""
        message = r'timeout must be a positive integer'
        with self.assertRaisesRegexp(transports.WorkerError, message):
            self.worker.timeout = -1

        with self.assertRaisesRegexp(transports.WorkerError, message):
            self.worker.timeout = 0

        self.worker.timeout = 10
        self.assertEqual(self.worker._timeout, 10)
        self.worker.timeout = None
        self.assertEqual(self.worker._timeout, None)

    def test_success_threshold_getter(self):
        """Return default value if not set, the value otherwise."""
        self.assertAlmostEqual(self.worker.success_threshold, 1.0)
        for success_threshold in (0.0, 0.0001, 0.5, 0.99):
            self.worker._success_threshold = success_threshold
            self.assertAlmostEqual(self.worker.success_threshold, success_threshold)

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

        with self.assertRaisesRegexp(transports.WorkerError, r'batch_size must be a positive integer'):
            self.worker.batch_size = 0

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
            self.worker.batch_sleep = 1

        with self.assertRaisesRegexp(transports.WorkerError, message):
            self.worker.batch_sleep = '1'

        with self.assertRaisesRegexp(transports.WorkerError, message):
            self.worker.batch_sleep = -1.0

        self.worker.batch_sleep = 10.0
        self.assertAlmostEqual(self.worker._batch_sleep, 10.0)


class TestModuleFunctions(unittest.TestCase):
    """Transports module functions test class."""

    def test_validate_list(self):
        """Should raise a WorkerError if the argument is not a list or None."""
        transports.validate_list('Test', None)
        transports.validate_list('Test', [])
        transports.validate_list('Test', ['value1'])
        transports.validate_list('Test', ['value1', 'value2'])

        message = r'Test must be a list'
        func = transports.validate_list
        for invalid_value in (0, 'invalid_value', {'invalid': 'value'}):
            self.assertRaisesRegexp(transports.WorkerError, message, func, 'Test', invalid_value)

    def test_validate_positive_integer(self):
        """Should raise a WorkerError if the argument is not a positive integer or None."""
        transports.validate_positive_integer('Test', None)
        transports.validate_positive_integer('Test', 1)
        transports.validate_positive_integer('Test', 100)

        message = r'Test must be a positive integer'
        func = transports.validate_positive_integer
        for invalid_value in (0, -1, 'invalid_value', ['invalid_value']):
            self.assertRaisesRegexp(transports.WorkerError, message, func, 'Test', invalid_value)

    def test_raise_error(self):
        """Should raise a WorkerError."""
        with self.assertRaisesRegexp(transports.WorkerError, 'Test message'):
            transports.raise_error('Test', 'message', 'value')
