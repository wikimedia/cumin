"""Abstract transport and state machine for hosts state."""
import logging
import os
import shlex

from abc import ABCMeta, abstractmethod, abstractproperty

from ClusterShell.NodeSet import NodeSet

from cumin import CuminError, nodeset_fromlist


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
            command (str): the command to execute.
            timeout (int, optional): the command's timeout in seconds.
            ok_codes (list, optional): a list of exit codes to be considered successful for the command.
                The exit code zero is considered successful by default, if this option is set it override it. If set
                to an empty list ``[]``, it means that any code is considered successful.
        """
        self.command = command
        self._timeout = None
        self._ok_codes = None

        if timeout is not None:
            self.timeout = timeout

        if ok_codes is not None:
            self.ok_codes = ok_codes

    def __repr__(self):
        """Return the representation of the :py:class:`Command`.

        The representation allow to instantiate a new :py:class:`Command` instance with the same properties.

        Returns:
            str: the representation of the object.

        """
        params = ["'{command}'".format(command=self.command.replace("'", r'\''))]

        for field in ('_timeout', '_ok_codes'):
            value = getattr(self, field)
            if value is not None:
                params.append('{key}={value}'.format(key=field[1:], value=value))

        return 'cumin.transports.Command({params})'.format(params=', '.join(params))

    def __str__(self):
        """Return the string representation of the command.

        Returns:
            str: the string representation of the object.

        """
        return self.command

    def __eq__(self, other):
        """Equality operation. Allow to directly compare a :py:class:`Command` object to another or a string.

        :Parameters:
            according to Python's Data model :py:meth:`object.__eq__`.

        Returns:
            bool: :py:data:`True` if the `other` object is equal to this one, :py:data:`False` otherwise.

        Raises:
            exceptions.ValueError: if the comparing object is not an instance of :py:class:`Command` or a
                :py:class:`str`.

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

        :Parameters:
            according to Python's Data model :py:meth:`object.__ne__`.

        Returns:
            bool: :py:data:`True` if the `other` object is different to this one, :py:data:`False` otherwise.

        Raises:
            exceptions.ValueError: if the comparing object is not an instance of :py:class:`Command` or a
                :py:class:`str`.

        """
        return not self == other

    @property
    def timeout(self):
        """Timeout of the :py:class:`Command`.

        :Getter:
            Returns the current `timeout` or :py:data:`None` if not set.

        :Setter:
            :py:class:`float`, :py:class:`int`, :py:data:`None`: the `timeout` in seconds for the execution of the
            `command` on each host. Both :py:class:`float` and :py:class:`int` are accepted and converted internally to
            :py:class:`float`. If :py:data:`None` the `timeout` is reset to its default value.

        Raises:
            cumin.transports.WorkerError: if trying to set it to an invalid value.

        """
        return self._timeout

    @timeout.setter
    def timeout(self, value):
        """Setter for the timeout property. The relative documentation is in the getter."""
        if isinstance(value, int):
            value = float(value)

        validate_positive_float('timeout', value)
        self._timeout = value

    @property
    def ok_codes(self):
        """List of exit codes to be considered successful for the execution of the :py:class:`Command`.

        :Getter:
            Returns the current `ok_codes` or a :py:class:`list` with the element ``0`` if not set.

        :Setter:
            :py:class:`list[int]`, :py:data:`None`: list of exit codes to be considered successful for the execution of
            the `command` on each host. Must be a :py:class:`list` of :py:class:`int` in the range ``0-255`` included,
            or :py:data:`None` to unset it. The exit code ``0`` is considered successful by default, but it can be
            overriden setting this property. Set it to an empty :py:class:`list` to consider any
            exit code successful.

        Raises:
            cumin.transports.WorkerError: if trying to set it to an invalid value.

        """
        ok_codes = self._ok_codes
        if ok_codes is None:
            ok_codes = [0]

        return ok_codes

    @ok_codes.setter
    def ok_codes(self, value):
        """Setter for the ok_codes property. The relative documentation is in the getter."""
        if value is None:
            self._ok_codes = value
            return

        validate_list('ok_codes', value, allow_empty=True)
        for code in value:
            if not isinstance(code, int) or code < 0 or code > 255:
                raise_error('ok_codes', 'must be a list of integers in the range 0-255 or None', value)

        self._ok_codes = value


class State(object):
    """State machine for the state of a host.

    .. attribute:: current

       :py:class:`int`: the current `state`.

    .. attribute:: pending, scheduled, running, success, failed, timeout

        :py:class:`int`: the available valid states, according to :py:attr:`valid_states`.

    .. attribute:: is_pending, is_scheduled, is_running, is_success, is_failed, is_timeout

       :py:class:`bool`: :py:data:`True` if this is the current `state`, :py:data:`False` otherwise.

    """

    valid_states = range(6)
    """:py:class:`list`: valid states indexes."""

    pending, scheduled, running, success, failed, timeout = valid_states
    """Valid states."""

    states_representation = ('pending', 'scheduled', 'running', 'success', 'failed', 'timeout')
    """:py:func:`tuple`: tuple with the string representations of the valid states."""

    allowed_state_transitions = {
        pending: (scheduled, ),
        scheduled: (running, ),
        running: (running, success, failed, timeout),
        success: (pending, ),
        failed: (),
        timeout: (),
    }
    """:py:class:`dict`: dictionary with ``{valid state: tuple of valid states}`` mapping of allowed transitions for
    any valid state."""

    def __init__(self, init=None):
        """State constructor. The initial state is set to `pending` it not provided.

        Arguments:
            init (int, optional): the initial state from where to start. The `pending` state will be used if not set.

        Raises:
            cumin.transports.InvalidStateError: if `init` is an invalid state.

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

        :Accessible properties:
            * `current` (:py:class:`int`): retuns the current state.
            * `is_{valid_state_name}` (:py:class:`bool`): for each valid state name, returns :py:data:`True` if the
              current state matches the state in the variable name. :py:data:`False` otherwise.

        :Parameters:
            according to Python's Data model :py:meth:`object.__getattr__`.

        Raises:
            exceptions.AttributeError: if the attribute name is not available.

        """
        if name == 'current':
            return self._state
        elif name.startswith('is_') and name[3:] in self.states_representation:
            return getattr(self, name[3:]) == self._state
        else:
            raise AttributeError("'State' object has no attribute '{name}'".format(name=name))

    def __repr__(self):
        """Return the representation of the :py:class:`State`.

        The representation allow to instantiate a new :py:class:`State` instance with the same properties.

        Returns:
            str: the representation of the object.

        """
        return 'cumin.transports.State(init={state})'.format(state=self._state)

    def __str__(self):
        """Return the string representation of the state.

        Returns:
            str: the string representation of the object.

        """
        return self.states_representation[self._state]

    def __eq__(self, other):
        """Equality operator for rich comparison.

        :Parameters:
            according to Python's Data model :py:meth:`object.__eq__`.

        Returns:
            bool: :py:data:`True` if `self` is equal to `other`, :py:data:`False` otherwise.

        Raises:
            exceptions.ValueError: if the comparing object is not an instance of :py:class:`State` or a
                :py:class:`int`.

        """
        return self._cmp(other) == 0

    def __lt__(self, other):
        """Less than operator for rich comparison.

        :Parameters:
            according to Python's Data model :py:meth:`object.__lt__`.

        Returns:
            bool: :py:data:`True` if `self` is lower than `other`, :py:data:`False` otherwise.

        Raises:
            exceptions.ValueError: if the comparing object is not an instance of :py:class:`State` or a
                :py:class:`int`.

        """
        return self._cmp(other) < 0

    def __le__(self, other):
        """Less than or equal operator for rich comparison.

        :Parameters:
            according to Python's Data model :py:meth:`object.__le__`.

        Returns:
            bool: :py:data:`True` if `self` is lower or equal than `other`, :py:data:`False` otherwise.

        Raises:
            exceptions.ValueError: if the comparing object is not an instance of :py:class:`State` or a
                :py:class:`int`.

        """
        return self._cmp(other) <= 0

    def __gt__(self, other):
        """Greater than operator for rich comparison.

        :Parameters:
            according to Python's Data model :py:meth:`object.__gt__`.

        Returns:
            bool: :py:data:`True` if `self` is greater than `other`, :py:data:`False` otherwise.

        Raises:
            exceptions.ValueError: if the comparing object is not an instance of :py:class:`State` or a
                :py:class:`int`.

        """
        return self._cmp(other) > 0

    def __ge__(self, other):
        """Greater than or equal operator for rich comparison.

        :Parameters:
            according to Python's Data model :py:meth:`object.__ge__`.

        Returns:
            bool: :py:data:`True` if `self` is greater or equal than `other`, :py:data:`False` otherwise.

        Raises:
            exceptions.ValueError: if the comparing object is not an instance of :py:class:`State` or a
                :py:class:`int`.

        """
        return self._cmp(other) >= 0

    def update(self, new):
        """Transition the state from the current state to the new one, if the transition is allowed.

        Arguments:
            new (int): the new state to set. Only specific state transitions are allowed.

        Raises:
            cumin.transports.StateTransitionError: if the transition is not allowed, see
                :py:attr:`allowed_state_transitions`.

        """
        if new not in self.valid_states:
            raise ValueError("State must be one of {valid}, got '{new}'".format(valid=self.valid_states, new=new))

        if new not in self.allowed_state_transitions[self._state]:
            raise StateTransitionError(
                "From the current state '{current}' the allowed states are '{allowed}', got '{new}'".format(
                    current=self._state, allowed=self.allowed_state_transitions[self._state], new=new))

        self._state = new

    def _cmp(self, other):
        """Comparison operation. Allow to directly compare a state object to another or to an integer.

        Raises ValueError if the comparing object is not an instance of State or an integer.

        Arguments:
        other -- the object to compare the current instance to
        """
        if isinstance(other, int):
            return self._state - other
        elif isinstance(other, State):
            return self._state - other._state  # pylint: disable=protected-access
        else:
            raise ValueError("Unable to compare instance of '{other}' with State instance".format(other=type(other)))


class Target(object):
    """Targets management class."""

    def __init__(self, hosts, batch_size=None, batch_size_ratio=None, batch_sleep=None):
        """Constructor, inizialize the Target with the list of hosts and additional parameters.

        Arguments:
            hosts (ClusterShell.NodeSet.NodeSet, list): hosts that will be targeted, both
                :py:class:`ClusterShell.NodeSet.NodeSet` and :py:class:`list` are accepted and converted automatically
                to :py:class:`ClusterShell.NodeSet.NodeSet` internally.
            batch_size (int, optional): set the batch size so that no more that this number of hosts are targeted
                at any given time. It must be a positive integer. If greater than the number of hosts it will be
                auto-resized to the number of hosts.
            batch_size_ratio (float, optional): set the batch size with a ratio so that no more that this fraction
                of hosts are targeted at any given time. It must be a float between 0 and 1 and will raise exception
                if after rounding it there are 0 hosts selected.
            batch_sleep (int, optional): sleep time in seconds between the end of execution of one host in the
                batch and the start in the next host. It must be a positive float.

        Raises:
            cumin.transports.WorkerError: if the `hosts` parameter is empty or invalid, if both the `batch_size` and
                `batch_size_ratio` parameters are set or if the `batch_size_ratio` selects no hosts.

        """
        self.logger = logging.getLogger('.'.join((self.__module__, self.__class__.__name__)))

        message = "must be a non-empty ClusterShell NodeSet or list"
        if not hosts:
            raise_error('hosts', message, hosts)
        elif isinstance(hosts, NodeSet):
            self.hosts = hosts
        elif isinstance(hosts, list):
            self.hosts = nodeset_fromlist(hosts)
        else:
            raise_error('hosts', message, hosts)

        if batch_size is not None and batch_size_ratio is not None:
            raise WorkerError(("The 'batch_size' and 'batch_size_ratio' parameters are mutually exclusive but they're "
                               "both set."))

        if batch_size_ratio is not None:
            if not isinstance(batch_size_ratio, float) or not 0.0 <= batch_size_ratio <= 1.0:
                raise_error('batch_size_ratio', 'must be a float between 0.0 and 1.0', batch_size_ratio)

            batch_size = round(len(self.hosts) * batch_size_ratio)
            if batch_size == 0:
                raise_error('batch_size_ratio', 'has generated a batch_size of 0 hosts', batch_size_ratio)

        self.batch_size = self._compute_batch_size(batch_size, self.hosts)
        self.batch_sleep = Target._compute_batch_sleep(batch_sleep)

    @property
    def first_batch(self):
        """First batch of the hosts to target.

        :Getter:
            Returns a :py:class:`ClusterShell.NodeSet.NodeSet` of the first batch of hosts, according to the
            `batch_size`.
        """
        return self.hosts[:self.batch_size]

    def _compute_batch_size(self, batch_size, hosts):
        """Compute the batch_size based on the hosts size and return the value to be used.

        Arguments:
            batch_size (int, None): a positive integer to indicate the batch_size to apply when executing the worker or
                :py:data:`None` to get its default value of all the hosts. If greater than the number of hosts, the
                number of hosts will be used as value instead.
            hosts (ClusterShell.NodeSet.NodeSet): the list of hosts to use to calculate the batch size.

        Returns:
            int: the effective `batch_size` to use.

        """
        validate_positive_integer('batch_size', batch_size)
        hosts_size = len(hosts)

        if batch_size is None:
            batch_size = hosts_size
        elif batch_size > hosts_size:
            self.logger.debug(("Provided batch_size '%d' is greater than the number of hosts '%d'"
                               ", using '%d' as value"), batch_size, hosts_size, hosts_size)
            batch_size = hosts_size

        return batch_size

    @staticmethod
    def _compute_batch_sleep(batch_sleep):
        """Validate batch_sleep and return its value or a default value.

        Arguments:
            batch_sleep(float, None): a positive float indicating the sleep in seconds to apply between one batched
                host and the next, or :py:data:`None` to get its default value.

        Returns:
            float: the effective `batch_sleep` to use.

        """
        validate_positive_float('batch_sleep', batch_sleep)
        return batch_sleep or 0.0


class BaseWorker(object, metaclass=ABCMeta):
    """Worker interface to be extended by concrete workers."""

    def __init__(self, config, target):
        """Worker constructor. Setup environment variables and initialize properties.

        Arguments:
            config (dict): a dictionary with the parsed configuration file.
            target (Target): a Target instance.
        """
        self.config = config
        self.target = target
        self.logger = logging.getLogger('.'.join((self.__module__, self.__class__.__name__)))
        self.logger.trace('Transport %s created with config: %s', type(self).__name__, config)

        # Initialize setters values
        self._commands = None
        self._handler = None
        self._timeout = None
        self._success_threshold = None

        for key, value in config.get('environment', {}).items():
            os.environ[key] = value

    @abstractmethod
    def execute(self):
        """Execute the task as configured.

        Returns:
            int: ``0`` on success, a positive integer on failure.

        Raises:
            cumin.transports.WorkerError: if misconfigured.

        """

    @abstractmethod
    def get_results(self):
        """Iterate over the results (`generator`).

        Yields:
            tuple: with ``(hosts, result)`` for each host(s) of the current execution.

        """

    @property
    def commands(self):
        """Commands for the current execution.

        :Getter:
            Returns the current `command` :py:class:`list` or an empty :py:class:`list` if not set.

        :Setter:
            :py:class:`list[Command]`, :py:class:`list[str]`: a :py:class:`list` of :py:class:`Command` objects or
            :py:class:`str` to be executed in the hosts. The elements are converted to :py:class:`Command`
            automatically.

        Raises:
            cumin.transports.WorkerError: if trying to set it with invalid data.

        """
        return self._commands or []

    @commands.setter
    def commands(self, value):
        """Setter for the `commands` property. The relative documentation is in the getter."""
        if value is None:
            self._commands = value
            return

        validate_list('commands', value, allow_empty=True)
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
        """Get and set the `handler` for the current execution.

        :Getter:
            Returns the current `handler` or :py:data:`None` if not set.

        :Setter:
            :py:class:`str`, :py:class:`EventHandler`, :py:data:`None`: an event handler to be notified of the progress
            during execution. Its interface depends on the actual transport chosen. Accepted values are:
            * None => don't use an event handler (default)
            * str => a string label to choose one of the available default EventHandler classes in that transport,
            * an event handler class object (not instance)
        """

    @abstractproperty
    @handler.setter
    def handler(self, value):
        """Setter for the `handler` property. The relative documentation is in the getter."""

    @property
    def timeout(self):
        """Global timeout for the current execution.

        :Getter:
            int: returns the current `timeout` or ``0`` (no timeout) if not set.

        :Setter:
            :py:class:`int`, :py:data:`None`: timeout for the current execution in seconds. Must be a positive integer
            or :py:data:`None` to reset it.

        Raises:
            cumin.transports.WorkerError: if trying to set it to an invalid value.

        """
        return self._timeout or 0

    @timeout.setter
    def timeout(self, value):
        """Setter for the global `timeout` property. The relative documentation is in the getter."""
        validate_positive_integer('timeout', value)
        self._timeout = value

    @property
    def success_threshold(self):
        """Success threshold for the current execution.

        :Getter:
            float: returns the current `success_threshold` or ``1.0`` (`100%`) if not set.

        :Setter:
            :py:class:`float`, :py:data:`None`: The success ratio threshold that must be reached to consider the run
            successful. A :py:class:`float` between ``0`` and ``1`` or :py:data:`None` to reset it. The specific
            meaning might change based on the chosen transport.

        Raises:
            cumin.transports.WorkerError: if trying to set it to an invalid value.

        """
        success_threshold = self._success_threshold
        if success_threshold is None:
            success_threshold = 1.0

        return success_threshold

    @success_threshold.setter
    def success_threshold(self, value):
        """Setter for the `success_threshold` property. The relative documentation is in the getter."""
        if value is not None and (not isinstance(value, float) or
                                  not (0.0 <= value <= 1.0)):  # pylint: disable=superfluous-parens
            raise WorkerError("success_threshold must be a float beween 0 and 1, got '{value_type}': {value}".format(
                value_type=type(value), value=value))

        self._success_threshold = value


def validate_list(property_name, value, allow_empty=False):
    """Validate a list.

    Arguments:
        property_name (str): the name of the property to validate.
        value (list): the value to validate.
        allow_empty (bool, optional): whether to consider an empty list valid.

    Raises:
        cumin.transports.WorkerError: if trying to set it to an invalid value.

    """
    if not isinstance(value, list):
        raise_error(property_name, 'must be a list', value)

    if not allow_empty and not value:
        raise_error(property_name, 'must be a non-empty list', value)


def validate_positive_integer(property_name, value):
    """Validate a positive integer or :py:data:`None`.

    Arguments:
        property_name (str): the name of the property to validate.
        value (int, None): the value to validate.

    Raises:
        cumin.transports.WorkerError: if trying to set it to an invalid value.

    """
    if value is not None and (not isinstance(value, int) or value <= 0):
        raise_error(property_name, 'must be a positive integer or None', value)


def validate_positive_float(property_name, value):
    """Validate a positive float or :py:data:`None`.

    Arguments:
        property_name (str): the name of the property to validate.
        value (float, None): the value to validate.

    Raises:
        cumin.transports.WorkerError: if trying to set it to an invalid value.

    """
    if value is not None and (not isinstance(value, float) or value <= 0):
        raise_error(property_name, 'must be a positive float or None', value)


def raise_error(property_name, message, value):
    """Raise a :py:class:`WorkerError` exception.

    Arguments:
        property_name (str): the name of the property that raised the exception.
        message (str): the message to use for the exception.
        value (mixed): the value that raised the exception.
    """
    raise WorkerError("{property_name} {message}, got '{value_type}': {value}".format(
        property_name=property_name, message=message, value_type=type(value), value=value))
