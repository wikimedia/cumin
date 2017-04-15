"""Abstract transport and state machine for hosts state."""
import logging
import os
import shlex

from abc import ABCMeta, abstractmethod, abstractproperty

from cumin import CuminError


class WorkerError(CuminError):
    """Custom exception class for worker errors."""


class StateTransitionError(CuminError):
    """Exception raised when an invalid transition for a node's State was attempted."""


class InvalidStateError(CuminError):
    """Exception raised when an invalid transition for a node's State was attempted."""


class Command(object):
    """Class to represent a command."""

    def __init__(self, command):
        """Command constructor.

        Arguments:
        command -- the command to execute.
        """
        self.command = command

    def __repr__(self):
        """Repr of the command, allow to instantiate a Command with the same properties."""
        return "cumin.transports.Command('{command}')".format(command=self.command)

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
        elif isinstance(other, Command):
            other_command = other.command
        else:
            raise ValueError("Unable to compare instance of '{other}' with Command instance".format(other=type(other)))

        return shlex.split(self.command) == shlex.split(other_command)

    def __ne__(self, other):
        """Inequality operation. Allow to directly compare a Command object to another or a string.

        Raises ValueError if the comparing object is not an instance of Command or a string.

        Arguments: according to Python's datamodel documentation
        """
        return not self == other


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
            return self._state - other._state
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


class BaseWorker(object):
    """Worker interface to be extended by concrete workers."""

    __metaclass__ = ABCMeta

    def __init__(self, config, logger=None):
        """Worker constructor. Setup environment variables and initialize properties.

        Arguments:
        config -- a dictionary with the parsed configuration file
        logger -- an optional logger instance [optional, default: None]
        """
        self.config = config
        self.logger = logger or logging.getLogger(__name__)

        # Initialize setters values
        self._hosts = None
        self._commands = None
        self._handler = None
        self._timeout = None
        self._success_threshold = None
        self._batch_size = None
        self._batch_sleep = None

        for key, value in config.get('environment', {}).iteritems():
            os.environ[key] = value

    @abstractmethod
    def execute(self):
        """Execute the task as configured. Return 0 on success, an int > 0 on failure."""

    @abstractmethod
    def get_results(self):
        """Generator that yields tuples '(node_name, result)' with the results of the current execution."""

    @property
    def hosts(self):
        """Getter for the hosts property with a default value."""
        return self._hosts or []

    @hosts.setter
    def hosts(self, value):
        """Setter for the hosts property with validation, raise WorkerError if not valid.

        Arguments:
        value -- a list of hosts to target for the execution of the commands
        """
        validate_list('hosts', value)
        self._hosts = value

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
        return self._success_threshold or 1.0

    @success_threshold.setter
    def success_threshold(self, value):
        """Setter for the success_threshold property with validation, raise WorkerError if not valid.

        Arguments:
        value -- The success ratio threshold that must be reached to consider the run successful. A float between 0
                 and 1 or None. The specific meaning might change based on the chosen transport. [default: 1]
        """
        if value is not None and (not isinstance(value, float) or not (0.0 <= value <= 1.0)):
            raise WorkerError("success_threshold must be a float beween 0 and 1, got '{value_type}': {value}".format(
                value_type=type(value), value=value))

        self._success_threshold = value

    @property
    def batch_size(self):
        """Getter for the batch_size property, default to the number of hosts if not set."""
        return self._batch_size or len(self.hosts)

    @batch_size.setter
    def batch_size(self, value):
        """Setter for the batch_size property with validation, raise WorkerError if not valid.

        Arguments:
        value -- the value to set the batch_size to, if greater than the number of hosts it will be auto-resized to the
                 number of hosts. Must be a positive integer or None to unset it.
        """
        validate_positive_integer('batch_size', value)
        hosts_size = len(self.hosts)
        if value is not None and value > hosts_size:
            self.logger.debug(("Provided batch_size '{batch_size}' is greater than the number of hosts '{hosts_size}'"
                               ", using '{hosts_size}' as value").format(batch_size=value, hosts_size=hosts_size))
            value = hosts_size

        self._batch_size = value

    @property
    def batch_sleep(self):
        """Getter for the batch_sleep property, default to 0.0 if not set."""
        return self._batch_sleep or 0.0

    @batch_sleep.setter
    def batch_sleep(self, value):
        """Setter for the batch_sleep property with validation, raise WorkerError if value is not valid.

        Arguments:
        value -- the value to set the batch_sleep to. Must be a positive float or None to unset it.
        """
        if value is not None and (not isinstance(value, float) or value < 0.0):
            raise_error('batch_sleep', 'must be a positive float', value)
        self._batch_sleep = value


def validate_list(property_name, value):
    """Helper to validate a list or None, raise WorkerError otherwise.

    Arguments:
    property_name -- the name of the property to validate
    value         -- the value to validate
    """
    if value is not None and not isinstance(value, list):
        raise_error(property_name, 'must be a list', value)


def validate_positive_integer(property_name, value):
    """Helper to validate a positive integer or None, raise WorkerError otherwise.

    Arguments:
    property_name -- the name of the property to validate
    value         -- the value to validate
    """
    if value is not None and (not isinstance(value, int) or value <= 0):
        raise_error(property_name, 'must be a positive integer', value)


def raise_error(property_name, message, value):
    """Helper to raise a WorkerError exception.

    Arguments:
    property_name -- the name of the property that raised the exception
    message       -- the message to use for the exception
    value         -- the value that raised the exception
    """
    raise WorkerError("{property_name} {message}, got '{value_type}': {value}".format(
        property_name=property_name, message=message, value_type=type(value), value=value))
