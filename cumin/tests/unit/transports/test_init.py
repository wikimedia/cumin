"""Transport tests."""
# pylint: disable=protected-access
from dataclasses import FrozenInstanceError
from unittest import mock

import pytest

from ClusterShell.MsgTree import MsgTreeElem
from ClusterShell.NodeSet import NodeSet

import cumin  # noqa: F401 (dynamically used in TestCommand)

from cumin import transports
from cumin.transports import TqdmProgressBars


class ConcreteBaseWorker(transports.BaseWorker):
    """Concrete class for BaseWorker."""

    def run(self):
        """Required by BaseWorker."""

    @property
    def results(self):
        """Required by BaseWorker."""

    def execute(self):
        """Required by BaseWorker."""

    def get_results(self):
        """Required by BaseWorker."""
        yield "node", "output"

    @property
    def handler(self):
        """Required by BaseWorker."""
        return self._handler

    @handler.setter
    def handler(self, value):
        """Required by BaseWorker."""
        self._handler = value


class Commands:
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


def get_single_output(command: transports.Command, command_index: int) -> transports.CommandOutputResult:
    """Get a single output result object to be used in tests."""
    return transports.CommandOutputResult(
        splitted_stderr=False,
        command=command,
        command_index=command_index,
        _stdout=MsgTreeElem(),
    )


@pytest.mark.parametrize('command', Commands().commands)
class TestCommandParametrized:
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
        command_repr = repr(command['obj'])
        if r'\ ' in command_repr:
            return  # Skip tests with bash-escaped spaces are they will trigger DeprecationWarning
        command_instance = eval(command_repr)  # nosec # pylint: disable=eval-used
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


class TestCommand:
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

    @pytest.mark.parametrize('length', range(5, 50, 3))
    def test_shortened(self, length):
        """Calling the shortened() method should return a shortened version of the command."""
        command = transports.Command('X' * 50)
        shortened = command.shortened(length)
        assert len(shortened) == length
        assert shortened.count('.') == 3
        assert shortened.count('X') == length - 3
        parts = shortened.split('...')
        assert len(parts) == 2
        assert (len(parts[0]) - len(parts[1])) in (0, 1)

    @pytest.mark.parametrize('command_length', range(1, 50, 3))
    def test_shortened_default_length(self, command_length):
        """Not passing the length should truncate the command at 35 characters."""
        command = transports.Command('X' * command_length)
        shortened = command.shortened()
        if command_length <= 35:
            assert shortened == command.command
        else:
            assert len(shortened) == 35

    @pytest.mark.parametrize('length', range(5))
    def test_shortened_raise(self, length):
        """Calling the shortened() method with a too short length should raise a WorkerError."""
        command = transports.Command('command1')
        with pytest.raises(transports.WorkerError, match='Commands longer than 5 chars cannot be shortened to'):
            command.shortened(length)


class TestState:
    """State class tests."""

    def test_instantiation_no_init(self):
        """A new State without an init value should start in the pending state."""
        state = transports.State()
        assert state._state == transports.HostState.PENDING

    def test_instantiation_init_ok(self):
        """A new State with a valid init value should start in this state."""
        state = transports.State(init=transports.HostState.RUNNING)
        assert state._state == transports.HostState.RUNNING

    def test_instantiation_init_ko(self):
        """A new State with an invalid init value should raise InvalidStateError."""
        with pytest.raises(transports.InvalidStateError, match='is not valid, must be an instance of HostState'):
            transports.State(init='invalid_state')

    def test_getattr_current(self):
        """Accessing the 'current' property should return the current state."""
        assert transports.State().current == transports.HostState.PENDING

    def test_getattr_is_valid_state(self):
        """Accessing a property named is_{a_valid_state_name} should return a boolean."""
        state = transports.State(init=transports.HostState.FAILED)
        assert not state.is_pending
        assert not state.is_scheduled
        assert not state.is_running
        assert not state.is_timeout
        assert not state.is_success
        assert state.is_failed

    def test_getattr_invalid_property(self):
        """Accessing a property with an invalid name should raise AttributeError."""
        state = transports.State(init=transports.HostState.FAILED)
        with pytest.raises(AttributeError, match='object has no attribute'):
            state.invalid_property  # pylint: disable=pointless-statement

    def test_repr(self):
        """A State repr should return its representation that allows to recreate the same State instance."""
        assert repr(transports.State()) == 'cumin.transports.State(init={state})'.format(
            state=transports.HostState.PENDING)
        state = transports.HostState.RUNNING
        assert repr(transports.State(init=state)) == 'cumin.transports.State(init={state})'.format(state=state)

    def test_str(self):
        """A State string should return its string representation."""
        assert str(transports.State()) == 'pending'
        assert str(transports.State(init=transports.HostState.RUNNING)) == 'running'

    def test_cmp_state(self):
        """Two State instance can be compared between each other."""
        state = transports.State()
        other_state = transports.State(init=transports.HostState.FAILED)
        same_state = transports.State()

        assert other_state != state
        assert same_state == state

    def test_cmp_host_state(self):
        """A State instance can be compared with HostState instances."""
        state = transports.State()
        other_state = transports.HostState.RUNNING
        same_state = transports.HostState.PENDING

        assert other_state != state
        assert same_state == state

    def test_cmp_invalid(self):
        """Trying to compare a State instance with an invalid object should raise ValueError."""
        state = transports.State()
        invalid_state = 'invalid_state'
        with pytest.raises(ValueError, match='Unable to compare instance'):
            state == invalid_state  # pylint: disable=pointless-statement

    def test_update_invalid_state(self):
        """Trying to update a State with an invalid value should raise ValueError."""
        state = transports.State()
        with pytest.raises(ValueError, match='State must be an instance of HostState'):
            state.update('invalid_state')

    def test_update_invalid_transition(self):
        """Trying to update a State with an invalid transition should raise StateTransitionError."""
        state = transports.State()
        with pytest.raises(transports.StateTransitionError, match='the allowed states are'):
            state.update(transports.HostState.FAILED)

    def test_update_ok(self):
        """Properly updating a State should update it without errors."""
        state = transports.State()
        state.update(transports.HostState.SCHEDULED)
        assert state.current == transports.HostState.SCHEDULED
        state.update(transports.HostState.RUNNING)
        assert state.current == transports.HostState.RUNNING
        state.update(transports.HostState.SUCCESS)
        assert state.current == transports.HostState.SUCCESS
        state.update(transports.HostState.PENDING)
        assert state.current == transports.HostState.PENDING


class TestTarget:
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


class TestBaseWorker:
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


class TestConcreteBaseWorker:
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


class TestModuleFunctions:
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


@mock.patch('cumin.transports.tqdm')
class TestProgressBars:
    """A class that tests ProgressBars."""

    def test_init_intialize_progress_bars_with_correct_size(self, tqdm):
        """Progress bars are initialized at the correct size."""
        progress = TqdmProgressBars()
        progress.init(10)

        assert tqdm.call_count == 2
        _, kwargs = tqdm.call_args
        assert kwargs['total'] == 10

    def test_progress_bars_are_closed(self, tqdm):
        """Progress bars are closed."""
        progress = TqdmProgressBars()
        progress.init(10)

        progress.close()

        assert tqdm.mock_calls[-2] == mock.call().close()
        assert tqdm.mock_calls[-1] == mock.call().close()

    def test_progress_bars_is_updated_on_success(self, tqdm):
        """Progress bar is updated on success."""
        progress = TqdmProgressBars()
        progress.init(10)

        progress.update_success(5)

        assert mock.call().update(5) in tqdm.mock_calls

    def test_progress_bars_is_updated_on_failure(self, tqdm):
        """Progress bar is updated on failure."""
        progress = TqdmProgressBars()
        progress.init(10)

        progress.update_failed(3)

        assert tqdm.mock_calls[-1] == mock.call().update(3)


def test_execution_status():
    """The string representation of the status should add spaces."""
    assert str(transports.ExecutionStatus.COMPLETED_WITH_FAILURES) == 'COMPLETED WITH FAILURES'
    assert str(transports.ExecutionStatus.INTERRUPTED) == 'INTERRUPTED'
    assert str(transports.ExecutionStatus.TIMEDOUT) == 'TIMEDOUT'
    assert str(transports.ExecutionStatus.UNKNOWN) == 'UNKNOWN'


class TestCommandOutputResult:
    """Test class for the CommandOutputResult class."""

    def setup_method(self):
        """Initialize default properties and instances."""
        # pylint: disable=attribute-defined-outside-init
        self.command = transports.Command('command1')
        self.stdout = {True: MsgTreeElem(b'output', parent=MsgTreeElem()),
                       False: MsgTreeElem(b'output\nerror', parent=MsgTreeElem())}
        self.stderr = {True: MsgTreeElem(b'error', parent=MsgTreeElem()), False: MsgTreeElem()}

    def test_init_raise(self):
        """If trying to instantiate with invalid data should raise a WorkerError."""
        with pytest.raises(transports.WorkerError,
                           match='Invalid arguments: "splitted_stderr" is set to False but "stderr" is not empty'):
            transports.CommandOutputResult(splitted_stderr=False, command=self.command, command_index=0,
                                           _stdout=self.stdout[False], _stderr=self.stderr[True])

    @pytest.mark.parametrize('splitted_stderr', (False, True))
    def test_output(self, splitted_stderr):
        """It should instantiate an instance without errors and return its stdout/stderr."""
        ret = transports.CommandOutputResult(
            splitted_stderr=splitted_stderr, command=self.command, command_index=0,
            _stdout=self.stdout[splitted_stderr], _stderr=self.stderr[splitted_stderr])
        assert ret.command_index == 0
        if splitted_stderr:
            assert ret.stdout() == 'output'
            assert ret.stdout(encoding='cp1252') == 'output'
            assert ret.stderr() == 'error'
            assert ret.stderr(encoding='ascii') == 'error'
        else:
            assert ret.stdout() == 'output\nerror'
            assert ret.stdout(encoding='cp1252') == 'output\nerror'
            with pytest.raises(transports.WorkerError, match='The output was not split between stdout and stderr'):
                ret.stderr()

    @pytest.mark.parametrize('splitted_stderr', (False, True))
    def test_format_empty_output(self, splitted_stderr):
        """It should be explicit on the fact that no output was produced."""
        empty = self.stderr[False]
        ret = transports.CommandOutputResult(
            splitted_stderr=splitted_stderr, command=self.command, command_index=0, _stdout=empty, _stderr=empty)
        lines = ret.format().splitlines()
        if splitted_stderr:
            assert len(lines) == 2
            assert lines[0] == "----- NO STDOUT of 'command1' -----"
            assert lines[1] == "----- NO STDERR of 'command1' -----"
        else:
            assert len(lines) == 1
            assert lines[0] == "----- NO OUTPUT of 'command1' -----"

    def test_format_unsplitted(self):
        """It should return the command output (stdout+stderr united) in a formatted way."""
        ret = transports.CommandOutputResult(
            splitted_stderr=False, command=self.command, command_index=0, _stdout=self.stdout[False])
        lines = ret.format().splitlines()
        assert len(lines) == 3
        assert lines[0] == "----- OUTPUT of 'command1' -----"
        assert lines[1] == 'output'
        assert lines[2] == 'error'

    def test_format_splitted(self):
        """It should return the command output (stdout and stderr separately) in a formatted way."""
        ret = transports.CommandOutputResult(splitted_stderr=True, command=self.command, command_index=0,
                                             _stdout=self.stdout[True], _stderr=self.stderr[True])
        lines = ret.format().splitlines()
        assert len(lines) == 4
        assert lines[0] == "----- STDOUT of 'command1' -----"
        assert lines[1] == 'output'
        assert lines[2] == "----- STDERR of 'command1' -----"
        assert lines[3] == 'error'


class TestHostResults:
    """Test class for the HostResults class."""

    @pytest.mark.parametrize('last_executed_command_index, return_codes', (
        (0, (0,)),
        (1, (0, 0)),
        (2, (0, 0, 0)),
    ))
    def test_completed_true(self, last_executed_command_index, return_codes):
        """It should return true if the execution was completed."""
        command = transports.Command('command1')
        commands = tuple([command] * len(return_codes))
        outputs = []
        for command_index in range(len(return_codes)):
            outputs.append(get_single_output(command, command_index))
        ret = transports.HostResults(
            name='node1', state=transports.HostState.SUCCESS, commands=commands,
            last_executed_command_index=last_executed_command_index, return_codes=return_codes, outputs=tuple(outputs))
        assert ret.completed

    @pytest.mark.parametrize('last_executed_command_index, return_codes', (
        (0, ()),
        (1, (1,)),
        (2, (0, 1)),
    ))
    def test_completed_false(self, last_executed_command_index, return_codes):
        """It should return false if the execution was not completed."""
        command = transports.Command('command1')
        commands = tuple([command] * (last_executed_command_index + len(return_codes) + 1))
        outputs = []
        for command_index in range(len(return_codes)):
            outputs.append(get_single_output(command, command_index))
        ret = transports.HostResults(
            name='node1', state=transports.HostState.FAILED, commands=commands,
            last_executed_command_index=last_executed_command_index, return_codes=return_codes, outputs=tuple(outputs))
        assert not ret.completed


def test_targeted_hosts_members():
    """The provided mapping should be RO and the dataclass frozen."""
    by_state = {transports.HostState.SUCCESS: cumin.nodeset('node[1-3]'),
                transports.HostState.FAILED: cumin.nodeset('node[4-5]')}
    by_return_code = {0: cumin.nodeset('node[1-3]'), 2: cumin.nodeset('node[4-5]')}
    targets = transports.TargetedHostsMembers(
        all=cumin.nodeset('node[1-5]'), by_state=by_state, by_return_code=by_return_code)

    # Ensure the instance is frozen
    with pytest.raises(FrozenInstanceError):
        targets.all = cumin.nodeset()

    # Ensure the mappings are read-only
    with pytest.raises(TypeError, match='mappingproxy'):
        targets.by_return_code[9] = cumin.nodeset('node9')
    with pytest.raises(TypeError, match='mappingproxy'):
        targets.by_return_code[0] |= cumin.nodeset('node9')


def test_targeted_hosts_counters():
    """The provided mapping should be RO and the dataclass frozen."""
    by_state = {transports.HostState.SUCCESS: 3, transports.HostState.FAILED: 2}
    by_return_code = {0: 3, 2: 2}
    targets = transports.TargetedHostsCounters(total=5, by_state=by_state, by_return_code=by_return_code)

    # Ensure the instance is frozen
    with pytest.raises(FrozenInstanceError):
        targets.total = 0

    # Ensure the mappings are read-only
    with pytest.raises(TypeError, match='mappingproxy'):
        targets.by_return_code[9] = 5
    with pytest.raises(TypeError, match='mappingproxy'):
        targets.by_return_code[0] += 5


def test_get_targeted_hosts():
    """It should return a TargetedHosts instance with copies of the nodesets."""
    all_hosts = cumin.nodeset('node[1-5]')
    by_state = {transports.HostState.SUCCESS: cumin.nodeset('node[1-3]'),
                transports.HostState.FAILED: cumin.nodeset('node[4-5]')}
    by_return_code = {0: cumin.nodeset('node[1-3]'), 2: cumin.nodeset('node[4-5]')}
    targets = transports.get_targeted_hosts(all_hosts=all_hosts, by_state=by_state, by_return_code=by_return_code)

    # Ensure the instance is frozen
    with pytest.raises(FrozenInstanceError):
        targets.hosts = targets.hosts

    # Ensure the mappings are read-only
    with pytest.raises(TypeError, match='mappingproxy'):
        targets.hosts.by_return_code[9] = cumin.nodeset('node9')
    with pytest.raises(TypeError, match='mappingproxy'):
        targets.hosts.by_return_code[0] |= cumin.nodeset('node9')

    # Alter the mappings nodesets and check that they are copies
    targets.hosts.by_return_code[0].add('node9')
    new_targets = transports.get_targeted_hosts(all_hosts=all_hosts, by_state=by_state, by_return_code=by_return_code)
    assert new_targets.hosts.by_return_code[0] == cumin.nodeset('node[1-3]')
    assert new_targets.counters.by_return_code[0] == 3


class TestCommandResults:
    """Test class for the CommandResults class."""

    def setup_method(self):
        """Initialize default properties and instances."""
        # pylint: disable=attribute-defined-outside-init
        all_hosts = cumin.nodeset('node[1-5]')
        by_state = {transports.HostState.SUCCESS: cumin.nodeset('node[1-3]'),
                    transports.HostState.FAILED: cumin.nodeset('node[4-5]')}
        by_return_code = {0: cumin.nodeset('node[1-3]'), 2: cumin.nodeset('node[4-5]')}
        self.targets = transports.get_targeted_hosts(
            all_hosts=all_hosts, by_state=by_state, by_return_code=by_return_code)
        self.command = transports.Command('command1')
        self.empty_command_results = transports.CommandResults(
            command=self.command, command_index=0, targets=self.targets, outputs=())

        self.stdout = {True: MsgTreeElem(b'output', parent=MsgTreeElem()),
                       False: MsgTreeElem(b'output\nerror', parent=MsgTreeElem())}
        self.stderr = {True: MsgTreeElem(b'error', parent=MsgTreeElem()), False: MsgTreeElem()}
        self.command_outputs = transports.CommandOutputResult(
            splitted_stderr=False, command=self.command, command_index=0,
            _stdout=MsgTreeElem(b'output', parent=MsgTreeElem()))
        hosts_outputs = transports.HostsOutputResult(hosts=all_hosts, output=self.command_outputs)
        partial1_outputs = transports.HostsOutputResult(
            hosts=cumin.nodeset('node[1-3]'), output=self.command_outputs)
        partial2_outputs = transports.HostsOutputResult(
            hosts=cumin.nodeset('node4'), output=self.command_outputs)
        self.command_results = transports.CommandResults(
            command=self.command, command_index=0, targets=self.targets, outputs=(hosts_outputs,))
        self.multi_command_results = transports.CommandResults(
            command=self.command, command_index=0, targets=self.targets, outputs=(partial1_outputs, partial2_outputs))
        self.single_missing_command_results = transports.CommandResults(
            command=self.command, command_index=0, targets=self.targets, outputs=(partial1_outputs,))

    def test_init_overlapping_outputs(self):
        """It should raise WorkerError when multiple outputs match the same host."""
        output1 = transports.HostsOutputResult(hosts=cumin.nodeset('node[1-3]'), output=self.command_outputs)
        output2 = transports.HostsOutputResult(hosts=cumin.nodeset('node[3-5]'), output=self.command_outputs)
        with pytest.raises(transports.WorkerError, match='Some hosts are present in more than one output: node3'):
            transports.CommandResults(
                command=self.command, command_index=0, targets=self.targets, outputs=(output1, output2))

    def test_init_unknown_host(self):
        """It should raise WorkerError when an output matches hosts not targeted."""
        output = transports.HostsOutputResult(hosts=cumin.nodeset('node[1-6]'), output=self.command_outputs)
        with pytest.raises(transports.WorkerError,
                           match='Some hosts referenced by outputs are not part of the targeted hosts: node6'):
            transports.CommandResults(
                command=self.command, command_index=0, targets=self.targets, outputs=(output,))

    def test_command_index(self):
        """It should return the command index of the command execution."""
        assert self.command_results.command_index == 0

    def test_has_no_outputs(self):
        """It should return True if there is any output."""
        assert self.empty_command_results.has_no_outputs
        assert not self.command_results.has_no_outputs

    def test_has_single_output(self):
        """If should return True if all the hosts have the same output."""
        assert not self.empty_command_results.has_single_output
        assert self.command_results.has_single_output

    def test_get_single_output_ok(self):
        """It should return the single output."""
        assert self.command_results.get_single_output() is self.command_outputs

    def test_get_single_output_no_outputs(self):
        """It should raise OutputsMismatchError if there are no outputs."""
        with pytest.raises(transports.OutputsMismatchError,
                           match="Command 'command1' has 0 distinct outputs, expected 1"):
            self.empty_command_results.get_single_output()

    def test_get_single_output_too_many_outputs(self):
        """It should raise OutputsMismatchError if there are too many outputs."""
        with pytest.raises(transports.OutputsMismatchError,
                           match="Command 'command1' has 2 distinct outputs, expected 1"):
            self.multi_command_results.get_single_output()

    def test_get_single_output_missing_hosts(self):
        """It should raise SingleOutputMissingHostsError if the single output doesn't cover all hosts."""
        with pytest.raises(transports.SingleOutputMissingHostsError,
                           match="Command 'command1' single output matches only 3 hosts of the 5 targeted"):
            self.single_missing_command_results.get_single_output()

    def test_get_host_output_ok(self):
        """It should return the output instance for the given host or None if didn't had any output."""
        host_output = self.command_results.get_host_output('node1')
        assert isinstance(host_output, transports.CommandOutputResult)
        host_output = self.multi_command_results.get_host_output('node4')
        assert isinstance(host_output, transports.CommandOutputResult)
        assert self.multi_command_results.get_host_output('node5') is None

    def test_get_host_output_not_found(self):
        """It should raise HostNotFoundError if the host is not part of the targets."""
        with pytest.raises(transports.HostNotFoundError, match="Host 'unknown' was not targeted"):
            self.command_results.get_host_output('unknown')


class TestExecutionResults:
    """Test class for the ExecutionResults class."""

    def setup_method(self):
        """Initialize default properties and instances."""
        # pylint: disable=attribute-defined-outside-init
        all_hosts = cumin.nodeset('node[1-5]')
        by_state = {transports.HostState.SUCCESS: cumin.nodeset('node[1-3]'),
                    transports.HostState.FAILED: cumin.nodeset('node[4-5]')}
        by_return_code = {0: cumin.nodeset('node[1-3]'), 2: cumin.nodeset('node[4-5]')}
        self.targets = transports.get_targeted_hosts(
            all_hosts=all_hosts, by_state=by_state, by_return_code=by_return_code)
        self.command = transports.Command('command1')
        self.empty_command_results = transports.CommandResults(
            command=self.command, command_index=0, targets=self.targets, outputs=())
        self.hosts_results = {}
        for i in range(1, 6):
            output = get_single_output(self.command, 0)
            self.hosts_results[f'node{i}'] = transports.HostResults(
                name=f'node{i}', state=transports.HostState.SUCCESS, commands=(self.command,),
                last_executed_command_index=0, return_codes=(0,), outputs=(output,))

        self.execution_results = transports.ExecutionResults(
            status=transports.ExecutionStatus.SUCCEEDED, last_executed_command_index=0,
            commands_results=(self.empty_command_results,), hosts_results=self.hosts_results)

        command_outputs = transports.CommandOutputResult(
            splitted_stderr=False, command=self.command, command_index=0,
            _stdout=MsgTreeElem(b'output', parent=MsgTreeElem()))
        hosts_outputs = transports.HostsOutputResult(hosts=all_hosts, output=command_outputs)
        command_results = transports.CommandResults(
            command=self.command, command_index=0, targets=self.targets, outputs=(hosts_outputs,))

        self.execution_results_with_output = transports.ExecutionResults(
            status=transports.ExecutionStatus.SUCCEEDED, last_executed_command_index=0,
            commands_results=(command_results,), hosts_results=self.hosts_results)

    def test_read_only(self):
        """Ensure that the instance is frozen and the mapping read only."""
        # Ensure the instance is frozen
        with pytest.raises(FrozenInstanceError):
            self.execution_results.status = transports.ExecutionStatus.FAILED

        # Ensure the mappings are read-only
        with pytest.raises(TypeError, match='mappingproxy'):
            del self.execution_results.hosts_results['node1']

    def test_has_no_outputs(self):
        """It should return True if the execution produced no outputs."""
        assert self.execution_results.has_no_outputs
        assert not self.execution_results_with_output.has_no_outputs
