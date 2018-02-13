"""Transport tests."""
# pylint: disable=protected-access,no-self-use
from unittest import mock

import pytest

from ClusterShell.NodeSet import NodeSet

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
    def handler(self):
        """Required by BaseWorker"""
        return self._handler

    @handler.setter
    def handler(self, value):
        """Required by BaseWorker"""
        self._handler = value


class Commands(object):
    """Helper class to define a list of commands to test."""

    command_with_options = r'command --with "options" -a -n -d params with\ spaces'
    command_with_options_equivalent = r"command  --with  'options'  -a  -n  -d  params  with\ spaces"
    command_with_nested_quotes = 'command --with \'nested "quotes"\' -a -n -d params with\\ spaces'
    different_command = r"command  --with  'other options'  -a  -n  -d  other_params  with\ spaces"

    def __init__(self):
        """Initialize test commands."""
        self.commands = [
            {'command': 'command1'},
            {'command': 'command1', 'timeout': 5},
            {'command': 'command1', 'ok_codes': [0, 255]},
            {'command': 'command1', 'timeout': 5, 'ok_codes': [0, 255]},
            {'command': self.command_with_options},
            {'command': self.command_with_options, 'timeout': 5},
            {'command': self.command_with_options, 'ok_codes': [0, 255]},
            {'command': self.command_with_options, 'timeout': 5, 'ok_codes': [0, 255]},
            {'command': self.command_with_nested_quotes},
            {'command': self.command_with_nested_quotes, 'timeout': 5},
            {'command': self.command_with_nested_quotes, 'ok_codes': [0, 255]},
            {'command': self.command_with_nested_quotes, 'timeout': 5, 'ok_codes': [0, 255]},
        ]

        for command in self.commands:
            command['obj'] = transports.Command(
                command['command'], timeout=command.get('timeout', None), ok_codes=command.get('ok_codes', None))


@pytest.mark.parametrize('command', Commands().commands)
class TestCommandParametrized(object):
    """Command class tests executed for each parametrized command."""

    def test_instantiation(self, command):
        """A new Command instance should set the command property to the given command."""
        assert isinstance(command['obj'], transports.Command)
        assert command['obj'].command == command['command']
        assert command['obj']._timeout == command.get('timeout', None)
        assert command['obj']._ok_codes == command.get('ok_codes', None)

    def test_repr(self, command):
        """A repr of a Command should allow to instantiate an instance with the same properties."""
        # Bandit and pylint would require to use ast.literal_eval, but it will not work with objects
        command_instance = eval(repr(command['obj']))  # nosec pylint: disable=eval-used
        assert isinstance(command_instance, transports.Command)
        assert repr(command_instance) == repr(command['obj'])
        assert command_instance.command == command['obj'].command
        assert command_instance._timeout == command['obj']._timeout
        assert command_instance._ok_codes == command['obj']._ok_codes

    def test_str(self, command):
        """A cast to string of a Command should return its command."""
        assert str(command['obj']) == command['command']

    def test_eq(self, command):
        """A Command instance can be compared to another or to a string with the equality operator."""
        assert command['obj'] == transports.Command(
            command['command'], timeout=command.get('timeout', None), ok_codes=command.get('ok_codes', None))

        if command.get('timeout', None) is None and command.get('ok_codes', None) is None:
            assert command['obj'] == command['command']

        with pytest.raises(ValueError, match='Unable to compare instance of'):
            command['obj'] == 1  # pylint: disable=pointless-statement

    def test_ne(self, command):
        """A Command instance can be compared to another or to a string with the inequality operator."""
        # Different command with same or differnt properties
        assert command['obj'] != transports.Command(
            Commands.different_command, timeout=command.get('timeout', None),
            ok_codes=command.get('ok_codes', None))
        assert command['obj'] != transports.Command(
            Commands.different_command, timeout=999, ok_codes=command.get('ok_codes', None))
        assert command['obj'] != transports.Command(
            Commands.different_command, timeout=command.get('timeout', None), ok_codes=[99])
        assert command['obj'] != transports.Command(Commands.different_command, timeout=999, ok_codes=[99])
        assert command['obj'] != Commands.different_command

        # Same command, properties different
        assert command['obj'] != transports.Command(
            command['command'], timeout=999, ok_codes=command.get('ok_codes', None))
        assert command['obj'] != transports.Command(
            command['command'], timeout=command.get('timeout', None), ok_codes=[99])
        assert command['obj'] != transports.Command(command['command'], timeout=999, ok_codes=[99])

        if command.get('timeout', None) is not None or command.get('ok_codes', None) is not None:
            assert command['obj'] != command['command']

        with pytest.raises(ValueError, match='Unable to compare instance of'):
            command['obj'] == 1  # pylint: disable=pointless-statement

    def test_timeout_getter(self, command):
        """Should return the timeout set, None otherwise."""
        if command['obj'].timeout is not None and command['obj']._timeout is not None:
            assert command['obj'].timeout == pytest.approx(command['obj']._timeout)

    def test_ok_codes_getter(self, command):
        """Should return the ok_codes set, [0] otherwise."""
        assert command['obj'].ok_codes == command.get('ok_codes', [0])


class TestCommand(object):
    """Command class non parametrized tests."""

    def test_eq_equivalent(self):
        """Two Commadn instances with equivalent comamnds just formatted differently should be considered equal."""
        command1 = transports.Command(Commands.command_with_options)
        command2 = transports.Command(Commands.command_with_options_equivalent)
        assert command1 == command2

    def test_timeout_setter(self):
        """Should set the timeout to its value, converted to float if integer. Unset it if None is passed."""
        command = transports.Command('command1')
        command.timeout = 1.0
        assert command._timeout == pytest.approx(1.0)
        command.timeout = None
        assert command._timeout is None
        command.timeout = 1
        assert command._timeout == pytest.approx(1.0)
        with pytest.raises(transports.WorkerError, match='timeout must be a positive float'):
            command.timeout = -1.0

    def test_ok_codes_getter_empty(self):
        """Should return the ok_codes set, [0] otherwise."""
        # Test empty list
        command = transports.Command('command1')
        assert command.ok_codes == [0]
        command.ok_codes = []
        assert command.ok_codes == []
        command.ok_codes = [1, 255]
        assert command.ok_codes == [1, 255]

    def test_ok_codes_setter(self):
        """Should set the ok_codes to its value, unset it if None is passed."""
        command = transports.Command('command1')
        assert command._ok_codes is None
        for i in range(256):
            codes = [i]
            command.ok_codes = codes
            assert command._ok_codes == codes
            codes.insert(0, 0)
            command.ok_codes = codes
            assert command._ok_codes == codes

        command.ok_codes = None
        assert command._ok_codes is None

        command.ok_codes = []
        assert command._ok_codes == []

        with pytest.raises(transports.WorkerError, match='ok_codes must be a list'):
            command.ok_codes = 'invalid_value'

        message = 'must be a list of integers in the range'
        for i in (-1, 0.0, 100.0, 256, 'invalid_value'):
            codes = [i]
            with pytest.raises(transports.WorkerError, match=message):
                command.ok_codes = codes

            codes.insert(0, 0)
            with pytest.raises(transports.WorkerError, match=message):
                command.ok_codes = codes


class TestState(object):
    """State class tests."""

    def test_instantiation_no_init(self):
        """A new State without an init value should start in the pending state."""
        state = transports.State()
        assert state._state == transports.State.pending

    def test_instantiation_init_ok(self):
        """A new State with a valid init value should start in this state."""
        state = transports.State(init=transports.State.running)
        assert state._state == transports.State.running

    def test_instantiation_init_ko(self):
        """A new State with an invalid init value should raise InvalidStateError."""
        with pytest.raises(transports.InvalidStateError, match='is not a valid state'):
            transports.State(init='invalid_state')

    def test_getattr_current(self):
        """Accessing the 'current' property should return the current state."""
        assert transports.State().current == transports.State.pending

    def test_getattr_is_valid_state(self):
        """Accessing a property named is_{a_valid_state_name} should return a boolean."""
        state = transports.State(init=transports.State.failed)
        assert not state.is_pending
        assert not state.is_scheduled
        assert not state.is_running
        assert not state.is_timeout
        assert not state.is_success
        assert state.is_failed

    def test_getattr_invalid_property(self):
        """Accessing a property with an invalid name should raise AttributeError."""
        state = transports.State(init=transports.State.failed)
        with pytest.raises(AttributeError, match='object has no attribute'):
            state.invalid_property  # pylint: disable=pointless-statement

    def test_repr(self):
        """A State repr should return its representation that allows to recreate the same State instance."""
        assert repr(transports.State()) == 'cumin.transports.State(init={state})'.format(state=transports.State.pending)
        state = transports.State.running
        assert repr(transports.State(init=state)) == 'cumin.transports.State(init={state})'.format(state=state)

    def test_str(self):
        """A State string should return its string representation."""
        assert str(transports.State()) == 'pending'
        assert str(transports.State(init=transports.State.running)) == 'running'

    def test_cmp_state(self):
        """Two State instance can be compared between each other."""
        state = transports.State()
        greater_state = transports.State(init=transports.State.failed)
        same_state = transports.State()

        assert greater_state > state
        assert greater_state >= state
        assert same_state >= state
        assert state < greater_state
        assert state <= greater_state
        assert state <= same_state
        assert state == same_state
        assert state != greater_state

    def test_cmp_int(self):
        """A State instance can be compared with integers."""
        state = transports.State()
        greater_state = transports.State.running
        same_state = transports.State.pending

        assert greater_state > state
        assert greater_state >= state
        assert same_state >= state
        assert state < greater_state
        assert state <= greater_state
        assert state <= same_state
        assert state == same_state
        assert state != greater_state

    def test_cmp_invalid(self):
        """Trying to compare a State instance with an invalid object should raise ValueError."""
        state = transports.State()
        invalid_state = 'invalid_state'
        with pytest.raises(ValueError, match='Unable to compare instance'):
            state == invalid_state  # pylint: disable=pointless-statement

    def test_update_invalid_state(self):
        """Trying to update a State with an invalid value should raise ValueError."""
        state = transports.State()
        with pytest.raises(ValueError, match='State must be one of'):
            state.update('invalid_state')

    def test_update_invalid_transition(self):
        """Trying to update a State with an invalid transition should raise StateTransitionError."""
        state = transports.State()
        with pytest.raises(transports.StateTransitionError, match='the allowed states are'):
            state.update(transports.State.failed)

    def test_update_ok(self):
        """Properly updating a State should update it without errors."""
        state = transports.State()
        state.update(transports.State.scheduled)
        assert state.current == transports.State.scheduled
        state.update(transports.State.running)
        assert state.current == transports.State.running
        state.update(transports.State.success)
        assert state.current == transports.State.success
        state.update(transports.State.pending)
        assert state.current == transports.State.pending


class TestTarget(object):
    """Target class tests."""

    def setup_method(self, _):
        """Initialize default properties and instances."""
        # pylint: disable=attribute-defined-outside-init
        self.hosts_list = ['host' + str(i) for i in range(10)]
        self.hosts = cumin.nodeset_fromlist(self.hosts_list)

    def test_init_no_hosts(self):
        """Creating a Target instance with empty hosts should raise WorkerError."""
        with pytest.raises(transports.WorkerError, match="must be a non-empty ClusterShell NodeSet or list"):
            transports.Target([])

    def test_init_nodeset(self):
        """Creating a Target instance with a NodeSet and without optional parameter should return their defaults."""
        target = transports.Target(self.hosts)
        assert target.hosts == self.hosts
        assert target.batch_size == len(self.hosts)
        assert target.batch_sleep == 0.0

    def test_init_list(self):
        """Creating a Target instance with a list and without optional parameter should return their defaults."""
        target = transports.Target(self.hosts_list)
        assert target.hosts == self.hosts
        assert target.batch_size == len(self.hosts)
        assert target.batch_sleep == 0.0

    def test_init_invalid(self):
        """Creating a Target instance with invalid hosts should raise WorkerError."""
        with pytest.raises(transports.WorkerError, match="must be a non-empty ClusterShell NodeSet or list"):
            transports.Target(set(self.hosts_list))

    @mock.patch('cumin.transports.logging.Logger.debug')
    def test_init_batch_size(self, mocked_logger):
        """Creating a Target instance with a batch_size should set it to it's value, if valid."""
        target = transports.Target(self.hosts, batch_size=5)
        assert target.batch_size == 5

        target = transports.Target(self.hosts, batch_size=len(self.hosts) + 1)
        assert target.batch_size == len(self.hosts)
        assert mocked_logger.called

        target = transports.Target(self.hosts, batch_size=None)
        assert target.batch_size == len(self.hosts)

        with pytest.raises(transports.WorkerError, match='must be a positive integer'):
            transports.Target(self.hosts, batch_size=0)

    def test_init_batch_size_perc(self):
        """Creating a Target instance with a batch_size_ratio should set batch_size to the appropriate value."""
        target = transports.Target(self.hosts, batch_size_ratio=0.5)
        assert target.batch_size == 5

        target = transports.Target(self.hosts, batch_size_ratio=1.0)
        assert target.batch_size == len(self.hosts)

        target = transports.Target(self.hosts, batch_size_ratio=None)
        assert target.batch_size == len(self.hosts)

        with pytest.raises(transports.WorkerError, match='parameters are mutually exclusive'):
            transports.Target(self.hosts, batch_size=1, batch_size_ratio=0.5)

        with pytest.raises(transports.WorkerError, match='has generated a batch_size of 0 hosts'):
            transports.Target(self.hosts, batch_size_ratio=0.0)

    @pytest.mark.parametrize('ratio', (1, 2.0, -0.1))
    def test_init_batch_size_perc_range(self, ratio):
        """Creating a Target instance with an invalid batch_size_ratio should raise WorkerError."""
        with pytest.raises(transports.WorkerError, match='must be a float between 0.0 and 1.0'):
            transports.Target(self.hosts, batch_size_ratio=ratio)

    def test_init_batch_sleep(self):
        """Creating a Target instance with a batch_sleep should set it to it's value, if valid."""
        target = transports.Target(self.hosts, batch_sleep=5.0)
        assert target.batch_sleep == pytest.approx(5.0)

        target = transports.Target(self.hosts, batch_sleep=None)
        assert target.batch_sleep == pytest.approx(0.0)

        with pytest.raises(transports.WorkerError):
            transports.Target(self.hosts, batch_sleep=0)

        with pytest.raises(transports.WorkerError):
            transports.Target(self.hosts, batch_sleep=-1.0)

    def test_first_batch(self):
        """The first_batch property should return the first_batch of hosts."""
        size = 5
        target = transports.Target(self.hosts, batch_size=size)
        assert len(target.first_batch) == size
        assert target.first_batch == cumin.nodeset_fromlist(self.hosts[:size])
        assert isinstance(target.first_batch, NodeSet)


class TestBaseWorker(object):
    """Concrete BaseWorker class for tests."""

    def test_instantiation(self):
        """Raise if instantiated directly, should return an instance of BaseWorker if inherited."""
        target = transports.Target(cumin.nodeset('node1'))
        with pytest.raises(TypeError):
            transports.BaseWorker({}, target)  # pylint: disable=abstract-class-instantiated

        assert isinstance(ConcreteBaseWorker({}, transports.Target(cumin.nodeset('node[1-2]'))), transports.BaseWorker)

    @mock.patch.dict(transports.os.environ, {}, clear=True)
    def test_init(self):
        """Constructor should save config and set environment variables."""
        env_dict = {'ENV_VARIABLE': 'env_value'}
        config = {'transport': 'test_transport',
                  'environment': env_dict}

        assert transports.os.environ == {}
        worker = ConcreteBaseWorker(config, transports.Target(cumin.nodeset('node[1-2]')))
        assert transports.os.environ == env_dict
        assert worker.config == config


class TestConcreteBaseWorker(object):
    """BaseWorker test class."""

    def setup_method(self, _):
        """Initialize default properties and instances."""
        # pylint: disable=attribute-defined-outside-init
        self.worker = ConcreteBaseWorker({}, transports.Target(cumin.nodeset('node[1-2]')))
        self.commands = [transports.Command('command1'), transports.Command('command2')]

    def test_commands_getter(self):
        """Access to commands property should return an empty list if not set and the list of commands otherwise."""
        assert self.worker.commands == []
        self.worker._commands = self.commands
        assert self.worker.commands == self.commands
        self.worker._commands = None
        assert self.worker.commands == []

    def test_commands_setter(self):
        """Raise WorkerError if trying to set it not to a list, set it otherwise."""
        with pytest.raises(transports.WorkerError, match='commands must be a list'):
            self.worker.commands = 'invalid_value'

        with pytest.raises(transports.WorkerError, match='commands must be a list of Command objects'):
            self.worker.commands = [1, 'command2']

        self.worker.commands = self.commands
        assert self.worker._commands == self.commands
        self.worker.commands = None
        assert self.worker._commands is None
        self.worker.commands = []
        assert self.worker._commands == []
        self.worker.commands = ['command1', 'command2']
        assert self.worker._commands == self.commands

    def test_timeout_getter(self):
        """Return default value if not set, the value otherwise."""
        assert self.worker.timeout == 0
        self.worker._timeout = 10
        assert self.worker.timeout == 10

    def test_timeout_setter(self):
        """Raise WorkerError if not a positive integer, set it otherwise."""
        message = r'timeout must be a positive integer'
        with pytest.raises(transports.WorkerError, match=message):
            self.worker.timeout = -1

        with pytest.raises(transports.WorkerError, match=message):
            self.worker.timeout = 0

        self.worker.timeout = 10
        assert self.worker._timeout == 10
        self.worker.timeout = None
        assert self.worker._timeout is None

    def test_success_threshold_getter(self):
        """Return default value if not set, the value otherwise."""
        assert self.worker.success_threshold == pytest.approx(1.0)
        for success_threshold in (0.0, 0.0001, 0.5, 0.99):
            self.worker._success_threshold = success_threshold
            assert self.worker.success_threshold == pytest.approx(success_threshold)

    def test_success_threshold_setter(self):
        """Raise WorkerError if not float between 0 and 1, set it otherwise."""
        message = r'success_threshold must be a float beween 0 and 1'
        with pytest.raises(transports.WorkerError, match=message):
            self.worker.success_threshold = 1

        with pytest.raises(transports.WorkerError, match=message):
            self.worker.success_threshold = -0.1

        self.worker.success_threshold = 0.3
        assert self.worker._success_threshold == pytest.approx(0.3)


class TestModuleFunctions(object):
    """Transports module functions test class."""

    def test_validate_list(self):
        """Should raise a WorkerError if the argument is not a list."""
        transports.validate_list('Test', ['value1'])
        transports.validate_list('Test', ['value1', 'value2'])
        transports.validate_list('Test', [], allow_empty=True)

        with pytest.raises(transports.WorkerError, match=r'Test must be a non-empty list'):
            transports.validate_list('Test', [])

        message = r'Test must be a list'
        for invalid_value in (0, None, 'invalid_value', {'invalid': 'value'}):
            with pytest.raises(transports.WorkerError, match=message):
                transports.validate_list('Test', invalid_value)

    def test_validate_positive_integer(self):
        """Should raise a WorkerError if the argument is not a positive integer or None."""
        transports.validate_positive_integer('Test', None)
        transports.validate_positive_integer('Test', 1)
        transports.validate_positive_integer('Test', 100)

        message = r'Test must be a positive integer'
        for invalid_value in (0, -1, 'invalid_value', ['invalid_value']):
            with pytest.raises(transports.WorkerError, match=message):
                transports.validate_positive_integer('Test', invalid_value)

    def test_raise_error(self):
        """Should raise a WorkerError."""
        with pytest.raises(transports.WorkerError, match='Test message'):
            transports.raise_error('Test', 'message', 'value')
