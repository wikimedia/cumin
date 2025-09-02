"""Abstract transport and state machine for hosts state."""
# pylint: disable=too-many-lines
import logging
import os
import shlex
import sys

from abc import ABCMeta, abstractmethod
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import auto, IntEnum, StrEnum
from itertools import combinations
from types import MappingProxyType
from typing import Callable, Optional

from ClusterShell.MsgTree import MsgTreeElem
from ClusterShell.NodeSet import NodeSet
from tqdm import tqdm

from cumin import CuminError, nodeset, nodeset_fromlist
from cumin.color import Colored


class WorkerError(CuminError):
    """Custom exception class for worker errors."""


class StateTransitionError(CuminError):
    """Exception raised when an invalid transition for a node's State was attempted."""


class InvalidStateError(CuminError):
    """Exception raised when an invalid transition for a node's State was attempted."""


class OutputsMismatchError(CuminError):
    """Exception raised when attempting to get a single output result but there isn't a single unique output."""


class SingleOutputMissingHostsError(CuminError):
    """Exception raised when attempting to get a single output result but the output doesn't cover all hosts."""


class HostNotFoundError(CuminError):
    """Exception raised when attempting to get results for a host that is not part of the execution."""


class SingleCommandOnlyError(CuminError):
    """Exception raised by methods reserved for a single command execution when there are multiple commands."""


class Command:
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

        for field_name in ('_timeout', '_ok_codes'):
            value = getattr(self, field_name)
            if value is not None:
                params.append('{key}={value}'.format(key=field_name[1:], value=value))

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

    def shortened(self, max_len: int = 35) -> str:
        """Return the shortened version of the command up to the given length, omitting the central part.

        Examples:
            ::

                >>> command = Command('long-command --with --many --options and arguments')
                >>> command.shortened()
                'long-command --w...ns and arguments'
                >>> command.shortened(20)
                'long-comm...rguments'
                >>> command.shortened(50)
                'long-command --with --many --options and arguments'
                >>> command.shortened(5)
                'l...s'

        Arguments:
            max_len (int): the maximum length of the returned string, must be at least 5.

        Raises:
            cumin.transports.WorkerError: if the max_len argument is smaller than 5.

        Returns:
            str: the shortened version of the command, if it's longer than max_len.

        """
        if len(self.command) <= max_len:
            return self.command

        if max_len < 5:
            raise WorkerError(f'Commands longer than 5 chars cannot be shortened to {max_len} chars, at least 5.')

        half = max_len // 2
        pref_len = half - 1
        if half * 2 == max_len:
            suff_len = half - 2
        else:
            suff_len = half - 1
        return f'{self.command[:pref_len]}...{self.command[-suff_len:]}'

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


class HostState(StrEnum):
    """StrEnum to describe all the possible states for a host."""

    PENDING = auto()
    """:py:class:`str`: Pending state, not yet scheduled."""
    SCHEDULED = auto()
    """:py:class:`str`: Scheduled for execution state."""
    RUNNING = auto()
    """:py:class:`str`: Running state, during the execution."""
    SUCCESS = auto()
    """:py:class:`str`: Execution completed with success state."""
    FAILED = auto()
    """:py:class:`str`: Exectution failed state."""
    TIMEOUT = auto()
    """:py:class:`str`: Execution timed out state."""


class State:
    """State machine for the state of a host.

    .. attribute:: current

       :py:class:`cumin.transports.HostState`: the current state.

    .. attribute:: is_pending

       :py:class:`bool`: :py:data:`True` if the current state is :py:attr:`cumin.transports.HostState.PENDING`,
       :py:data:`False` otherwise.

    .. attribute:: is_scheduled

       :py:class:`bool`: :py:data:`True` if the current state is :py:attr:`cumin.transports.HostState.SCHEDULED`,
       :py:data:`False` otherwise.

    .. attribute:: is_running

       :py:class:`bool`: :py:data:`True` if the current state is :py:attr:`cumin.transports.HostState.RUNNING`,
       :py:data:`False` otherwise.

    .. attribute:: is_success

       :py:class:`bool`: :py:data:`True` if the current state is :py:attr:`cumin.transports.HostState.SUCCESS`,
       :py:data:`False` otherwise.

    .. attribute:: is_failed

       :py:class:`bool`: :py:data:`True` if the current state is :py:attr:`cumin.transports.HostState.FAILED`,
       :py:data:`False` otherwise.

    .. attribute:: is_timeout

       :py:class:`bool`: :py:data:`True` if the current state is :py:attr:`cumin.transports.HostState.TIMEOUT`,
       :py:data:`False` otherwise.

    """

    allowed_state_transitions = {
        HostState.PENDING: (HostState.SCHEDULED, ),
        HostState.SCHEDULED: (HostState.RUNNING, ),
        HostState.RUNNING: (HostState.RUNNING, HostState.SUCCESS, HostState.FAILED, HostState.TIMEOUT),
        HostState.SUCCESS: (HostState.PENDING, ),
        HostState.FAILED: (),
        HostState.TIMEOUT: (),
    }
    """:py:class:`dict`: Dictionary with ``{valid state: tuple of valid states}`` mapping of the allowed transitions
    between all the possile states.

    This is the diagram of the allowed transitions:

    .. image:: ../../examples/transports_state_transitions.png
       :alt: State class allowed transitions diagram

    |

    """

    def __init__(self, init=None):
        """State constructor. The initial state is set to `pending` it not provided.

        Arguments:
            init (cumin.transports.HostState, optional): the initial state from where to start. The `pending` state
                will be used if not set.

        Raises:
            cumin.transports.InvalidStateError: if `init` is an invalid state.

        """
        if init is None:
            self._state = HostState.PENDING
        elif isinstance(init, HostState):
            self._state = init
        else:
            raise InvalidStateError("Initial state '{state}' is not valid, must be an instance of HostState".format(
                state=init))

    def __getattr__(self, name):
        """Attribute accessor.

        :Accessible properties:
            * `current` (:py:class:`cumin.transports.HostState`): retuns the current state.
            * `is_{valid_state_name}` (:py:class:`bool`): for each valid state name, returns :py:data:`True` if the
              current state matches the state in the variable name. :py:data:`False` otherwise.

        :Parameters:
            according to Python's Data model :py:meth:`object.__getattr__`.

        Raises:
            exceptions.AttributeError: if the attribute name is not available.

        """
        if name == 'current':
            return self._state

        if name.startswith('is_') and hasattr(HostState, name[3:].upper()):
            return HostState[name[3:].upper()] == self._state

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
        return str(self._state)

    def __eq__(self, other):
        """Equality operator for rich comparison.

        :Parameters:
            according to Python's Data model :py:meth:`object.__eq__`.

        Returns:
            bool: :py:data:`True` if `self` is equal to `other`, :py:data:`False` otherwise.

        Raises:
            exceptions.ValueError: if the comparing object is not an instance of :py:class:`cumin.transports.State`
                or a :py:class:`cumin.transports.HostState`.

        """
        if isinstance(other, HostState):
            return self._state.value == other.value

        if isinstance(other, State):
            return self._state.value == other._state.value  # pylint: disable=protected-access

        raise ValueError("Unable to compare instance of '{other}' with State instance".format(other=type(other)))

    def update(self, new):
        """Transition the state from the current state to the new one, if the transition is allowed.

        Arguments:
            new (cumin.transports.HostState): the new state to set. Only specific state transitions are allowed.

        Raises:
            cumin.transports.StateTransitionError: if the transition is not allowed, see
                :py:attr:`allowed_state_transitions`.

        """
        if not isinstance(new, HostState):
            raise ValueError("State must be an instance of HostState, got '{new}'".format(new=new))

        if new not in self.allowed_state_transitions[self._state]:
            raise StateTransitionError(
                "From the current state '{current}' the allowed states are '{allowed}', got '{new}'".format(
                    current=self._state, allowed=self.allowed_state_transitions[self._state], new=new))

        self._state = new


class Target:
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
            batch_sleep (float, optional): sleep time in seconds between the end of execution of one host in the
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


class BaseWorker(metaclass=ABCMeta):
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

    def run_one(self) -> 'CommandResults':
        """Execute a single command on all the targets using the handler.

        This method should be used when there is only one command to execute as it returns directly a
        :py:class:`cumin.transports.CommandResults` that is easier to manage for the single command use case
        than a :py:class:`cumin.transports.ExecutionResults` one as returned by the
        :py:meth:`cumin.transports.BaseWorker.run` method.

        Returns:
            cumin.transports.CommandResults: the results instance for the single command execution.

        Raises:
            cumin.transports.SingleCommandOnlyError: if there is more than one command set for the execution.

        """
        n_commands = len(self.commands)
        if n_commands != 1:
            raise SingleCommandOnlyError(
                f'The run_single() method can execute only a single command, {n_commands} were provided.')

        results = self.run()
        return results.commands_results[0]

    @abstractmethod
    def run(self) -> 'ExecutionResults':
        """Execute all the configured commands on all the targets using the handler.

        When there is only one command to execute, the :py:meth:`cumin.transports.BaseWorker.run_one` method can be
        used instead for an easier access to the results.

        Returns:
            cumin.transports.ExecutionResults: the results instance for all the commands executed.

        """

    @property
    @abstractmethod
    def results(self) -> 'ExecutionResults':
        """Property to access the results instance after having executed the commands.

        Although both :py:meth:`cumin.transports.BaseWorker.run_one` and :py:meth:`cumin.transports.BaseWorker.run`
        methods returns already their results, this property can be convient in some cases when in need to access the
        results at a later point or to get the partial results in case of a catched exception.

        Returns:
            cumin.transports.ExecutionResults: the execution results instance if the execution is completed.

        Raises:
            cumin.transports.WorkerError: if unable to return results, for example because the execution has not
                started yet.

        """

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

    @property
    @abstractmethod
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

    @handler.setter
    @abstractmethod
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
        if value is not None and (not isinstance(value, float)
                                  or not (0.0 <= value <= 1.0)):  # pylint: disable=superfluous-parens
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


class BaseExecutionProgress(metaclass=ABCMeta):
    """Listener interface to consume notification of the status of successful / failed hosts.

    The listener needs to be notified of the total number of hosts when the
    operation starts, and then notified of successes and failures.

    """

    @abstractmethod
    def init(self, num_hosts: int) -> None:
        """Initialize the progress bars.

        Arguments:
            num_hosts (int): the total number of hosts

        """

    @abstractmethod
    def close(self) -> None:
        """Closes the progress bars."""

    @abstractmethod
    def update_success(self, num_hosts: int = 1) -> None:
        """Updates the number of successful hosts.

        Arguments:
            num_hosts (int): increment to the number of hosts that have completed successfully

        """

    @abstractmethod
    def update_failed(self, num_hosts: int = 1) -> None:
        """Updates the number of failed hosts.

        Arguments:
            num_hosts (int): increment to the number of hosts that have completed in error

        """


class TqdmProgressBars(BaseExecutionProgress):
    """Progress bars based on TQDM."""

    def __init__(self) -> None:
        """Create the progress bars.

        Note:
            the progress bars themselves are not initalized at object creation. ``init()`` needs to be called before
            using the progress bars.

        """
        self._pbar_success: Optional[tqdm] = None
        self._pbar_failed: Optional[tqdm] = None
        self._bar_format = ('{desc} |{bar}| {percentage:3.0f}% ({n_fmt}/{total_fmt}) '
                            '[{elapsed}<{remaining}, {rate_fmt}]')

    def init(self, num_hosts: int) -> None:
        """Initialize the progress bars.

        Arguments:
            num_hosts (int): the total number of hosts

        """
        self._pbar_success = self._tqdm(num_hosts, 'PASS', Colored.green)
        self._pbar_failed = self._tqdm(num_hosts, 'FAIL', Colored.red)

    def _tqdm(self, num_hosts: int, desc: str, color: Callable[[str], str]) -> tqdm:
        pbar = tqdm(desc=desc, total=num_hosts, leave=True, unit='hosts', dynamic_ncols=True,
                    bar_format=color(self._bar_format), file=sys.stderr)
        pbar.refresh()
        return pbar

    def close(self) -> None:
        """Closes the progress bars."""
        self._success.close()
        self._failed.close()

    def update_success(self, num_hosts: int = 1) -> None:
        """Updates the number of successful hosts.

        Arguments:
            num_hosts (int): increment to the number of hosts that have completed successfully

        """
        self._success.update(num_hosts)

    def update_failed(self, num_hosts: int = 1) -> None:
        """Updates the number of failed hosts.

        Arguments:
            num_hosts (int): increment to the number of hosts that have completed in error

        """
        self._failed.update(num_hosts)

    @property
    def _success(self) -> tqdm:
        if self._pbar_success is None:
            raise ValueError('init() should be called before any other operation')
        return self._pbar_success

    @property
    def _failed(self) -> tqdm:
        if self._pbar_failed is None:
            raise ValueError('init() should be called before any other operation')
        return self._pbar_failed


class NoProgress(BaseExecutionProgress):
    """Used as a null object to disable the display of execution progress."""

    def init(self, num_hosts: int) -> None:
        """Does nothing."""

    def close(self) -> None:
        """Does nothing."""

    def update_success(self, num_hosts: int = 1) -> None:
        """Does nothing."""

    def update_failed(self, num_hosts: int = 1) -> None:
        """Does nothing."""


class ExecutionStatus(IntEnum):
    """Enum to define the possible execution statuses."""

    SUCCEEDED = 0
    """The execution completed successfully on all hosts."""
    COMPLETED_WITH_FAILURES = 1
    """The execution completed for some hosts, but there were some failures."""
    FAILED = 2
    """The execution failed, no host executed all commands successfully."""
    UNKNOWN = 3
    """The execution status is unknown, this is the initial status."""
    TIMEDOUT = 4
    """The execution timed out due to the global timeout."""
    INTERRUPTED = 5
    """The execution has been interrupted."""

    def __str__(self):
        """String representation of the value."""
        return self.name.replace('_', ' ')


@dataclass(frozen=True, kw_only=True)
class CommandOutputResult:
    """Dataclass to represent a single result output.

    Notes:
        The instances of this class are read-only.

    Arguments:
        splitted_stderr (bool): whether the capture of ``stdout`` and ``stderr`` was done separately or all the output
            is gathered in the ``output`` property.
        command (cumin.transports.Command): the command that generated this output.
        command_index (int): the index of the command that generated this output in the list of commands.
        _stdout (ClusterShell.MsgTree.MsgTreeElem): the data structure that recorded the output. Client's code should
            call the :py:meth:`cumin.transports.CommandOutputResult.stdout` method to get the command's standard
            output.
        _stderr (ClusterShell.MsgTree.MsgTreeElem, optional): the data structure that recorded the output. Client's
            code should call the :py:meth:`cumin.transports.CommandOutputResult.stderr` method to get the command's
            standard error output.

    """

    splitted_stderr: bool
    command: Command
    command_index: int
    _stdout: MsgTreeElem
    _stderr: MsgTreeElem = field(default_factory=MsgTreeElem)

    def __post_init__(self) -> None:
        """Ensure data consistency at instantiation time.

        Raises:
            cumin.transports.WorkerError: if _stderr is set but splitted_stderr is :py:data:`False`.

        """
        if not self.splitted_stderr and len(self._stderr):
            raise WorkerError('Invalid arguments: "splitted_stderr" is set to False but "stderr" is not empty')

    def stdout(self, *, encoding: str = 'utf-8') -> str:
        """Get the standard output of the executed command.

        It contains both ``stdout`` and ``stderr`` when the
        :py:attr:`cumin.transports.CommandOutputResult.splitted_stderr` property is :py:data:`False` or just
        ``stdout`` when is :py:data:`True`.

        Arguments:
            encoding (str, optional): the encoding to use to convert the output from binary to string.

        Returns:
            str: the caputred output string.

        """
        return self._stdout.message().decode(encoding)

    def stderr(self, *, encoding: str = 'utf-8') -> str:
        """Get the standard error of the executed command.

        Arguments:
            encoding (str, optional): the encoding to use to convert the output from binary to string.

        Returns:
            str: the output string.

        Raises:
            cumin.transports.WorkerError: when the :py:attr:`cumin.transports.CommandOutputResult.splitted_stderr`
                property is set to :py:data:`False`.

        """
        if not self.splitted_stderr:
            raise WorkerError('The output was not split between stdout and stderr, call `stdout()` instead.')
        return self._stderr.message().decode(encoding)

    def format(self, *, encoding: str = 'utf-8', colored: bool = False) -> str:
        """String representation of the command outputs.

        Arguments:
            encoding (str, optional): the encoding to use to convert the output from binary to string.
            colored (bool, optional): whether to return a color-encoded output with the same colors of the CLI.

        Returns:
            str: a pre-formatted output with all the command captured output, splitting standard output and error
            if they where recorded separately.

        """
        command = self.command.shortened()
        parts = []
        negation = 'NO '
        prefix = '' if len(self._stdout) else negation
        name = 'STDOUT' if self.splitted_stderr else 'OUTPUT'
        output_line = f"----- {prefix}{name} of '{command}' -----"
        if colored:
            output_line = Colored.blue(output_line)

        parts.append(output_line)

        if len(self._stdout):
            parts.append(self._stdout.message().decode(encoding))

        if self.splitted_stderr:
            stderr_prefix = '' if len(self._stderr) else negation
            error_line = f"----- {stderr_prefix}STDERR of '{command}' -----"
            if colored:
                error_line = Colored.blue(error_line)

            parts.append(error_line)

            if len(self._stderr):
                parts.append(self._stderr.message().decode(encoding))

        return '\n'.join(parts)


@dataclass(frozen=True, kw_only=True)
class HostsOutputResult:
    """Dataclass to represent a single result output for a group of hosts.

    Notes:
        The instances of this class are read-only.

    Arguments:
        hosts (ClusterShell.NodeSet.NodeSet): the hosts that generated the output.
        output (cumin.transports.CommandOutputResult): the command result.

    """

    hosts: NodeSet
    output: CommandOutputResult


@dataclass(frozen=True, kw_only=True)
class HostResults:
    """Dataclass to represent all the output of all the executed commands for a given host.

    Notes:
        The instances of this class are read-only.

    Arguments:
        name (str): the hostname used to connect to it, usually the FQDN.
        state (cumin.transports.HostState): the final execution state of the host.
        commands (tuple): the list of :py:class:`cumin.transports.Command` instances, one for each executed command.
        last_executed_command_index (int): the index of the last executed command from the ``commands`` tuple on this
            host. Has the value of ``-1`` if no commands were executed on this host.
        return_codes (tuple): a tuple of :py:class:`int` objects with the return code of each executed commands. It can
            be shorter than the ``commands`` tuple if some commands were not executed.
        outputs (tuple): a tuple of :py:class:`cumin.transports.CommandOutputResult` instances with the results of the
            commands execution. Each position in this tuple represent the output of the command with the same index
            in the commands tuple. It can be shorter than the ``commands`` tuple if some commands were not executed.

    """

    name: str
    state: HostState
    commands: tuple[Command, ...]
    last_executed_command_index: int
    return_codes: tuple[int, ...]
    outputs: tuple[CommandOutputResult, ...]

    def __post_init__(self) -> None:
        """Ensure data consistency at instantiation time.

        Raises:
            cumin.transports.WorkerError: if there is any inconsistency in the arguments.

        """
        num_commands = len(self.commands)
        if self.last_executed_command_index < 0 and (self.return_codes or self.outputs):
            raise WorkerError(f'Invalid negative last_executed_command_index ({self.last_executed_command_index}) '
                              f'with return codes or outputs set.')
        if self.last_executed_command_index > (num_commands - 1):
            raise WorkerError(
                f'Invalid last_executed_command_index {self.last_executed_command_index} greater than the available '
                f'commands {num_commands - 1}')
        if len(self.return_codes) > num_commands:
            raise WorkerError(f'Expected at most {num_commands} return_codes, got {len(self.return_codes)} instead')
        if len(self.outputs) > num_commands:
            raise WorkerError(f'Expected at most {num_commands} outputs, got {len(self.outputs)} instead')

    @property
    def completed(self) -> bool:
        """Whether all commands were executed and completed execution.

        Returns:
            bool: if the host has completed the execution of all commands.

        """
        return (self.last_executed_command_index == len(self.commands) - 1
                and len(self.return_codes) == len(self.commands))


@dataclass(frozen=True, kw_only=True)
class TargetedHostsMembers:
    """Class to represent the targeted hosts based on their state and return code after the execution.

    Each instance of this class is meant to be directly related to a specific command executed.

    Notes:
        The instances of this class are read-only.

    Arguments:
        all (ClusterShell.NodeSet.NodeSet): the set of all targeted hosts.
        by_state (Mapping): a mapping that for each :py:class:`cumin.transports.HostState` member returns the set of
            targeted hosts that ended up in that state after the execution of the command.
        by_return_code (Mapping): a mapping that for each return code returns the set of targeted hosts that returned
            that return code after the execution of the command.

    """

    all: NodeSet
    by_state: Mapping[HostState, NodeSet]
    by_return_code: Mapping[int, NodeSet]

    def __post_init__(self) -> None:
        """Ensure data consistency at instantiation time and make the mapping properties read-only.

        Raises:
            cumin.transports.WorkerError: if there is any inconsistency in the arguments.

        """
        object.__setattr__(self, 'by_state', MappingProxyType(self.by_state))
        object.__setattr__(self, 'by_return_code', MappingProxyType(self.by_return_code))

        for group_name in ('by_state', 'by_return_code'):
            group_nodeset = nodeset()
            for hosts in getattr(self, group_name).values():
                group_nodeset |= hosts

            if (
                (group_name == 'by_state' and group_nodeset != self.all)
                or (group_name == 'by_return_code' and not self.all.issuperset(group_nodeset))
            ):
                missing = self.all - group_nodeset
                unknown = group_nodeset - self.all
                raise WorkerError(
                    f'Invalid {group_name}, is missing {len(missing)} nodes and has {len(unknown)} unknown nodes:'
                    f'\nmissing: {missing}\nunknown: {unknown}'
                )


@dataclass(frozen=True, kw_only=True)
class TargetedHostsCounters:
    """Class to represent the targeted hosts count based on their state and return code after the execution.

    Each instance of this class is meant to be directly related to a specific command executed.

    Notes:
        The instances of this class are read-only.

    Arguments:
        total (int): the total number of hosts that were scheduled to execute this command.
        by_state (Mapping): a mapping that for each :py:class:`cumin.transports.HostState` member returns the number
            of targeted hosts that ended up in that state after the execution of the command.
        by_return_code (Mapping): a mapping that for each return code returns the number of targeted hosts that
            returned that return code after the execution of the command.

    """

    total: int
    by_state: Mapping[HostState, int]
    by_return_code: Mapping[int, int]

    def __post_init__(self) -> None:
        """Ensure data consistency at instantiation time and make the mapping properties read-only.

        Raises:
            cumin.transports.WorkerError: if there is any inconsistency in the arguments.

        """
        object.__setattr__(self, 'by_state', MappingProxyType(self.by_state))
        object.__setattr__(self, 'by_return_code', MappingProxyType(self.by_return_code))

        total_by_state = sum(num_hosts for num_hosts in self.by_state.values())
        if total_by_state != self.total:
            raise WorkerError(
                f'Expected sum of all by_state hosts ({total_by_state}) to match the total ({self.total})')

        total_by_return_code = sum(num_hosts for num_hosts in self.by_return_code.values())
        if total_by_return_code > self.total:
            raise WorkerError(
                f'Expected sum of all by_return_code hosts ({total_by_return_code}) to not exceed the total '
                f'({self.total})')


@dataclass(frozen=True, kw_only=True)
class TargetedHosts:
    """Class to represent the targeted hosts based on their state and return code after the execution.

    Each instance of this class is meant to be directly related to a specific command executed.

    Notes:
        The instances of this class are read-only.

    Arguments:
        hosts (cumin.transports.TargetedHostsMembers): the targeted hosts with their name.
        counter (cumin.transports.TargetedHostsCounters): the targeted hosts counters.

    """

    hosts: TargetedHostsMembers
    counters: TargetedHostsCounters


def get_targeted_hosts(
    *,
    all_hosts: NodeSet,
    by_state: Mapping[HostState, NodeSet],
    by_return_code: Mapping[int, NodeSet]
) -> TargetedHosts:
    """Helper function to get a :py:class:`cumin.transports.TargetedHosts` instance.

    Arguments:
        all_hosts (ClusterShell.NodeSet.NodeSet): the set of all targeted hosts.
        by_state (Mapping): a mapping that for each :py:class:`cumin.transports.HostState` member returns the set of
            targeted hosts that ended up in that state after the execution of the command.
        by_return_code (Mapping): a mapping that for each return code returns the set of targeted hosts that returned
            that return code after the execution of the command.

    Returns:
        cumin.transports.TargetedHosts: the targeted hosts instance with members and counters.

    """
    return TargetedHosts(
        hosts=TargetedHostsMembers(
            all=all_hosts.copy(),
            by_state={key: value.copy() for key, value in by_state.items()},
            by_return_code={key: value.copy() for key, value in by_return_code.items()},
        ),
        counters=TargetedHostsCounters(
            total=len(all_hosts),
            by_state=Counter({state: len(hosts) for state, hosts in by_state.items()}),
            by_return_code=Counter({return_code: len(hosts) for return_code, hosts in by_return_code.items()}),
        ),
    )


@dataclass(frozen=True, kw_only=True)
class CommandResults:
    """Class to expose the results of the execution of a single command.

    Notes:
        The instances of this class are read-only.

    Arguments:
        command (cumin.transports.Command): the command executed.
        command_index (int): the index of this command in the list of commands executed.
        targets (cumin.transports.TargetedHosts): the targeted hosts instance with members and counters.
        outputs (tuple): a tuple of :py:class:`cumin.transports.HostsOutputResult` instances with the recorded outputs.
            If all hosts had no output for this command the tuple will be empty.

    """

    command: Command
    command_index: int
    targets: TargetedHosts
    outputs: tuple[HostsOutputResult, ...]

    def __post_init__(self) -> None:
        """Ensure data consistency."""
        # Ensure that each host is included in only one output
        for output_a, output_b in combinations(self.outputs, 2):
            duplicated = output_a.hosts & output_b.hosts
            if duplicated:
                raise WorkerError(f'Some hosts are present in more than one output: {duplicated}')

        matched = nodeset()
        for output in self.outputs:
            matched |= output.hosts

        # Ensure that the outputs match only hosts targeted
        if not self.targets.hosts.all.issuperset(matched):
            unknowns = matched - self.targets.hosts.all
            raise WorkerError(f'Some hosts referenced by outputs are not part of the targeted hosts: {unknowns}')

    @property
    def has_no_outputs(self) -> bool:
        """Property that tells if the execution has produced no outputs.

        Returns:
            bool: :py:data:`True` if the execution has produced no outputs, :py:data:`False` otherwise.

        """
        return not self.outputs

    @property
    def has_single_output(self) -> bool:
        """Property that tells if the execution has produced the same output across all targeted hosts.

        Returns:
            bool: :py:data:`True` if the execution has produced a single output that is the same for all targeted
            hosts.

        """
        return len(self.outputs) == 1 and self.outputs[0].hosts == self.targets.hosts.all

    def get_single_output(self) -> CommandOutputResult:
        """Quicker access to get the output instance in case all hosts have produced the same output.

        Returns:
            cumin.transports.CommandOutputResult: the output instance.

        Raises:
            cumin.transports.OutputsMismatchError: when there are multiple outputs.
            cumin.transports.SingleOutputMissingHostsError: when there is a single output but some hosts had no output.

        """
        n_outputs = len(self.outputs)
        if n_outputs != 1:
            raise OutputsMismatchError(f"Command '{self.command}' has {n_outputs} distinct outputs, expected 1")

        n_matches = len(self.outputs[0].hosts)
        if self.outputs[0].hosts != self.targets.hosts.all:
            raise SingleOutputMissingHostsError(
                f"Command '{self.command}' single output matches only {n_matches} hosts of the "
                f"{self.targets.counters.total} targeted."
            )

        return self.outputs[0].output

    def get_host_output(self, name: str) -> Optional[CommandOutputResult]:
        """Get the output instance for a given host or :py:data:`None` if it had no output.

        Arguments:
            name (str): the hostname used to connect to it, usually the FQDN.

        Returns:
            None: when the host had no output.
            cumin.transports.CommandOutputResult: the host output instance when there is any output.

        """
        if name not in self.targets.hosts.all:
            raise HostNotFoundError(f"Host '{name}' was not targeted")

        for output in self.outputs:
            if name in output.hosts:
                return output.output

        return None  # Host has no output


@dataclass(frozen=True, kw_only=True)
class ExecutionResults:
    """Class to expose to the final results of an execution run.

    Notes:
        The instances of this class are read-only.

    Arguments:
        status (cumin.transports.ExecutionStatus): the final status of the execution run.
        last_executed_command_index (int): the index of the last executed command in the list of commands to be
            executed.
        commands_results(tuple): the tuple of :py:class:`cumin.transports.CommandResults` instances for each
            command to be executed.
        hosts_results (mapping): the mapping of hosts results with string keys (hostnames or FQDN) and instances
            of :py:class:`cumin.transports.HostResults` as values.

    """

    status: ExecutionStatus
    last_executed_command_index: int
    commands_results: tuple[CommandResults, ...]
    hosts_results: Mapping[str, HostResults]

    def __post_init__(self):
        """Sanity checks and make the mapping properties read-only."""
        object.__setattr__(self, 'hosts_results', MappingProxyType(self.hosts_results))

        grouped_num_commands = defaultdict(nodeset)
        for hostname, host_results in self.hosts_results.items():
            grouped_num_commands[len(host_results.commands)].add(hostname)

        if len(grouped_num_commands) != 1:
            grouped_num_commands_string = '\n'.join(
                f'{group_num_commands} commands: {group_hosts}'
                for group_num_commands, group_hosts
                in grouped_num_commands.items()
            )
            raise WorkerError(
                f'All hosts should have the same number of commands got {len(grouped_num_commands)} groups '
                f'instead:\n{grouped_num_commands_string}')

        num_commands = list(grouped_num_commands.keys())[0]

        if self.last_executed_command_index < 0:
            raise WorkerError('Invalid negative last_executed_command_index: {self.last_executed_command_index}')
        if self.last_executed_command_index > (num_commands - 1):
            raise WorkerError(
                'Invalid last_executed_command_index greater than the commands index '
                f'({self.last_executed_command_index} > {num_commands - 1})')
        if len(self.commands_results) != num_commands:
            raise WorkerError(
                f'Invalid commands_results, expected to have {num_commands} results, got '
                f'{len(self.commands_results)} instead')

        for index, command_result in enumerate(self.commands_results):
            if index != command_result.command_index:
                raise WorkerError(
                    f'Invalid commands_results[{index}], should have command_index {index}, has '
                    f'{command_result.command_index} instead')

    @property
    def return_code(self):
        """Property to easily access the return code of the whole execution run.

        Returns:
            int: the return code of the execution.

        """
        return self.status.value

    @property
    def has_no_outputs(self) -> bool:
        """Property that tells if the execution has produced no outputs.

        Returns:
            bool: :py:data:`True` if the execution has produced no outputs, :py:data:`False` otherwise.

        """
        return all(command_results.has_no_outputs for command_results in self.commands_results)
