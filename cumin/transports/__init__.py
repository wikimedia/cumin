"""Abstract transport and state machine for hosts state."""
import logging
import os
import shlex

from abc import ABCMeta, abstractmethod, abstractproperty

from ClusterShell.NodeSet import NodeSet

from cumin import CuminError


class WorkerError(CuminError):
    """Custom exception class for worker errors."""


class StateTransitionError(CuminError):
    """Exception raised when an invalid transition for a node's State was attempted."""


class InvalidStateError(CuminError):
    """Exception raised when an invalid transition for a node's State was attempted."""


class Command(object):
    """Class to represent a command."""

    def __init__(self, command, timeout=None, ok_codes=None):
        """Command constructor.

        Arguments:
        command  -- the command to execute.
        timeout  -- the command's timeout in seconds. [optional, default: None]
        ok_codes -- a list of exit codes to be considered successful for the command. The exit code 0 is considered
                    successful by default, if this option is set it override it. If set to an empty list it means
                    that any code is considered successful. [optional, default: None]
        """
        self.command = command
        self._timeout = None
        self._ok_codes = None

        if timeout is not None:
            self.timeout = timeout

        if ok_codes is not None:
            self.ok_codes = ok_codes

    def __repr__(self):
        """Repr of the command, allow to instantiate a Command with the same properties."""
        params = ["'{command}'".format(command=self.command.replace("'", r'\''))]

        for field in ('_timeout', '_ok_codes'):
            value = getattr(self, field)
            if value is not None:
                params.append('{key}={value}'.format(key=field[1:], value=value))

        return 'cumin.transports.Command({params})'.format(params=', '.join(params))

    def __str__(self):
        """String representation of the command."""
        return self.command

    def __eq__(self, other):
        """Equality operation. Allow to directly compare a Command object to another or a string.

        Raises ValueError if the comparing object is not an instance of Command or a string.

        Arguments: according to Python's datamodel documentation
        """
        if isinstance(other, str):
            other_command = other
            same_params = (self._timeout is None and self._ok_codes is None)
        elif isinstance(other, Command):
            other_command = other.command
            same_params = (self.timeout == other.timeout and self.ok_codes == other.ok_codes)
        else:
            raise ValueError("Unable to compare instance of '{other}' with Command instance".format(other=type(other)))

        return shlex.split(self.command) == shlex.split(other_command) and same_params

    def __ne__(self, other):
        """Inequality operation. Allow to directly compare a Command object to another or a string.

        Raises ValueError if the comparing object is not an instance of Command or a string.

        Arguments: according to Python's datamodel documentation
        """
        return not self == other

    @property
    def timeout(self):
        """Getter for the command's timeout property, return None if not set."""
        return self._timeout

    @timeout.setter
    def timeout(self, value):
        """Setter for the command's timeout property with validation, raise WorkerError if not valid.

        Arguments:
        value -- the command's timeout in seconds for it's execution on each host. Must be a positive float or a
                 positive integer, or None to unset it.
        """
        if isinstance(value, int):
            value = float(value)

        validate_positive_float('timeout', value)
        self._timeout = value

    @property
    def ok_codes(self):
        """Getter for the command's ok_codes property, return a list with only the element 0 if not set."""
        ok_codes = self._ok_codes
        if ok_codes is None:
            ok_codes = [0]

        return ok_codes

    @ok_codes.setter
    def ok_codes(self, value):
        """Setter for the command's ok_codes property with validation, raise WorkerError if not valid.

        Arguments:
        value -- the command's list of exit codes to be considered successful for the execution. Must be a list of
                 integers in the range 0-255 or None to unset it. The exit code 0 is considered successful by default,
                 but it can be overriden setting this property. An empty list is also accepted.
        """
        if value is None:
            self._ok_codes = value
            return

        validate_list('ok_codes', value, allow_empty=True)
        for code in value:
            if not isinstance(code, int) or code < 0 or code > 255:
                raise_error('ok_codes', 'must be a list of integers in the range 0-255 or None', value)

        self._ok_codes = value


class State(object):
    """State machine for the state of a host."""

    # Valid states indexes
    valid_states = range(6)
    # Valid states
    pending, scheduled, running, success, failed, timeout = valid_states

    # String representation of the valid states
    states_representation = ('pending', 'scheduled', 'running', 'success', 'failed', 'timeout')

    # Dictionary of tuples of valid states to which the transition is allowed from the current state
    allowed_state_transitions = {
        pending: (scheduled, ),
        scheduled: (running, ),
        running: (running, success, failed, timeout),
        success: (pending, ),
        failed: (),
        timeout: (),
    }

    def __init__(self, init=None):
        """State constructor. The initial state is set to pending it not provided.

        Raises InvalidStateError if init is an invalid state.

        Arguments:
        init -- the initial state from where to start. If not specified, the State will start in the pending state.
                [optional, default: None]
        """
        if init is None:
            self._state = self.pending
        elif init in self.valid_states:
            self._state = init
        else:
            raise InvalidStateError("Initial state '{state}' is not a valid state. Expected one of {states}".format(
                state=init, states=self.valid_states))

    def __getattr__(self, name):
        """Attribute accessor.

        Returns the current state and dynamically a bool for variables named 'is_{valid_state_name}'.
        Raises AttributeError otherwise.

        Arguments: according to Python's datamodel documentation
        """
        if name == 'current':
            return self._state
        elif name.startswith('is_') and name[3:] in self.states_representation:
            return getattr(self, name[3:]) == self._state
        else:
            raise AttributeError("'State' object has no attribute '{name}'".format(name=name))

    def __repr__(self):
        """Repr of the state, allow to instantiate a State in the same state."""
        return 'cumin.transports.State(init={state})'.format(state=self._state)

    def __str__(self):
        """String representation of the state."""
        return self.states_representation[self._state]

    def __cmp__(self, other):
        """Comparison operation. Allow to directly compare a state object to another or to an integer.

        Raises ValueError if the comparing object is not an instance of State or an integer.

        Arguments: according to Python's datamodel documentation
        """
        if isinstance(other, int):
            return self._state - other
        elif isinstance(other, State):
            return self._state - other._state  # pylint: disable=protected-access
        else:
            raise ValueError("Unable to compare instance of '{other}' with State instance".format(other=type(other)))

    def update(self, new):
        """Transition the state from the current state to the new one, if the transition is allowed.

        Raises StateTransitionError if the transition is not allowed, see allowed_state_transitions.

        Arguments:
        new -- the new state to set. Only specific state transitions are allowed.
        """
        if new not in self.valid_states:
            raise ValueError("State must be one of {valid}, got '{new}'".format(valid=self.valid_states, new=new))

        if new not in self.allowed_state_transitions[self._state]:
            raise StateTransitionError(
                "From the current state '{current}' the allowed states are '{allowed}', got '{new}'".format(
                    current=self._state, allowed=self.allowed_state_transitions[self._state], new=new))

        self._state = new


class Target(object):
    """Targets management class."""

    def __init__(self, hosts, batch_size=None, batch_sleep=None, logger=None):
        """Constructor, inizialize the Target with the list of hosts and additional parameters.

        Arguments:
        hosts       -- a ClusterShell's NodeSet or a list of hosts that will be targeted
        batch_size  -- set the batch size so that no more that this number of hosts are targeted at any given time.
                       If greater than the number of hosts it will be auto-resized to the number of hosts. It must be
                       a positive integer or None to unset it. [optional, default: None]
        batch_sleep -- sleep time in seconds between the end of execution of one host in the batch and the start in
                       the next host. It must be a positive float or None to unset it. [optional, default: None]
        logger      -- a logging.Logger instance [optional, default: None]
        """
        self.logger = logger or logging.getLogger(__name__)

        if isinstance(hosts, NodeSet):
            self.hosts = hosts
        elif isinstance(hosts, list):
            self.hosts = NodeSet.fromlist(hosts)
        else:
            raise_error('hosts', "must be a ClusterShell's NodeSet or a list", hosts)

        self.batch_size = self._compute_batch_size(batch_size, self.hosts)
        self.batch_sleep = Target._compute_batch_sleep(batch_sleep)

    @property
    def first_batch(self):
        """Extract the first batch of hosts to execute."""
        return self.hosts[:self.batch_size]

    def _compute_batch_size(self, batch_size, hosts):
        """Compute the batch_size based on the hosts size and return the value to be used.

        Arguments:
        batch_size -- a positive integer to indicate the batch_size to apply when executing the worker or None to get
                      its default value. If greater than the number of hosts, the number of hosts will be used as value.
        hosts      -- the list of hosts to use to calculate the batch size.
        """
        validate_positive_integer('batch_size', batch_size)
        hosts_size = len(hosts)

        if batch_size is None:
            batch_size = hosts_size
        elif batch_size > hosts_size:
            self.logger.debug(("Provided batch_size '{batch_size}' is greater than the number of hosts '{hosts_size}'"
                               ", using '{hosts_size}' as value").format(batch_size=batch_size, hosts_size=hosts_size))
            batch_size = hosts_size

        return batch_size

    @staticmethod
    def _compute_batch_sleep(batch_sleep):
        """Validate batch_sleep and return its value or a default value.

        Arguments:
        batch_sleep -- a positive float indicating the sleep in seconds to apply between one batched host and the next,
                       or None to get its default value.
        """
        validate_positive_float('batch_sleep', batch_sleep)
        return batch_sleep or 0.0


class BaseWorker(object):
    """Worker interface to be extended by concrete workers."""

    __metaclass__ = ABCMeta

    def __init__(self, config, target, logger=None):
        """Worker constructor. Setup environment variables and initialize properties.

        Arguments:
        config -- a dictionary with the parsed configuration file
        target -- a Target instance
        logger -- an optional logger instance [optional, default: None]
        """
        self.config = config
        self.target = target
        self.logger = logger or logging.getLogger(__name__)
        self.logger.trace('Transport {name} created with config: {config}'.format(
            name=type(self).__name__, config=config))

        # Initialize setters values
        self._commands = None
        self._handler = None
        self._timeout = None
        self._success_threshold = None

        for key, value in config.get('environment', {}).iteritems():
            os.environ[key] = value

    @abstractmethod
    def execute(self):
        """Execute the task as configured. Return 0 on success, an int > 0 on failure."""

    @abstractmethod
    def get_results(self):
        """Generator that yields tuples '(node_name, result)' with the results of the current execution."""

    @property
    def commands(self):
        """Getter for the commands property with a default value."""
        return self._commands or []

    @commands.setter
    def commands(self, value):
        """Setter for the commands property with validation, raise WorkerError if not valid.

        Arguments:
        value -- a list of Command objects or strings with the commands to be executed on the hosts. If a list of
                 strings is passed, it will be automatically converted to a list of Command objects.
        """
        if value is None:
            self._commands = value
            return

        validate_list('commands', value)
        commands = []
        for command in value:
            if isinstance(command, Command):
                commands.append(command)
            elif isinstance(command, str):
                commands.append(Command(command))
            else:
                raise_error('commands', 'must be a list of Command objects or strings', value)

        self._commands = commands

    @abstractproperty
    @property
    def handler(self):
        """Getter for the handler property."""

    @abstractproperty
    @handler.setter
    def handler(self, value):
        """Setter for the handler property with validation, can raise WorkerError if not valid.

        Arguments:
        value -- an event handler to be notified of the progress during execution. It's interface depends on the
                 actual transport chosen. Accepted values are:
                 - None => don't use an event handler (default)
                 - str => a string label to choose one of the available default EventHandler classes in that transport,
                 - an event handler class object (not instance)
                [optional, default: None]
        """

    @property
    def timeout(self):
        """Getter for the global timeout property, default to 0 (unlimited) if not set."""
        return self._timeout or 0

    @timeout.setter
    def timeout(self, value):
        """Setter for the global timeout property with validation, raise WorkerError if not valid.

        Arguments:
        value -- the global timeout in seconds for the whole execution. Must be a positive integer or None to unset it.
        """
        validate_positive_integer('timeout', value)
        self._timeout = value

    @property
    def success_threshold(self):
        """Getter for the success_threshold property with a default value."""
        success_threshold = self._success_threshold
        if success_threshold is None:
            success_threshold = 1.0

        return success_threshold

    @success_threshold.setter
    def success_threshold(self, value):
        """Setter for the success_threshold property with validation, raise WorkerError if not valid.

        Arguments:
        value -- The success ratio threshold that must be reached to consider the run successful. A float between 0
                 and 1 or None. The specific meaning might change based on the chosen transport. [default: 1]
        """
        if value is not None and (not isinstance(value, float) or
                                  not (0.0 <= value <= 1.0)):  # pylint: disable=superfluous-parens
            raise WorkerError("success_threshold must be a float beween 0 and 1, got '{value_type}': {value}".format(
                value_type=type(value), value=value))

        self._success_threshold = value


def validate_list(property_name, value, allow_empty=False):
    """Helper to validate a list, raise WorkerError otherwise.

    Arguments:
    property_name -- the name of the property to validate
    value         -- the value to validate
    """
    if not isinstance(value, list):
        raise_error(property_name, 'must be a list', value)

    if not allow_empty and not value:
        raise_error(property_name, 'must be a non-empty list', value)


def validate_positive_integer(property_name, value):
    """Helper to validate a positive integer or None, raise WorkerError otherwise.

    Arguments:
    property_name -- the name of the property to validate
    value         -- the value to validate
    """
    if value is not None and (not isinstance(value, int) or value <= 0):
        raise_error(property_name, 'must be a positive integer or None', value)


def validate_positive_float(property_name, value):
    """Helper to validate a positive float or None, raise WorkerError otherwise.

    Arguments:
    property_name -- the name of the property to validate
    value         -- the value to validate
    """
    if value is not None and (not isinstance(value, float) or value <= 0):
        raise_error(property_name, 'must be a positive float or None', value)


def raise_error(property_name, message, value):
    """Helper to raise a WorkerError exception.

    Arguments:
    property_name -- the name of the property that raised the exception
    message       -- the message to use for the exception
    value         -- the value that raised the exception
    """
    raise WorkerError("{property_name} {message}, got '{value_type}': {value}".format(
        property_name=property_name, message=message, value_type=type(value), value=value))
