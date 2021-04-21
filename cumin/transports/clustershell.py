"""Transport ClusterShell: worker and event handlers."""
import logging
import sys
import threading

from abc import ABCMeta, abstractmethod
from collections import Counter, defaultdict
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, Union

from ClusterShell import Event, Task
from ClusterShell.MsgTree import MsgTreeElem
from tqdm import tqdm

from cumin import nodeset, nodeset_fromlist
from cumin.color import Colored
from cumin.transports import (BaseExecutionProgress, BaseWorker, Command, NoProgress, raise_error, State,
                              Target, TqdmProgressBars, WorkerError)


class ClusterShellWorker(BaseWorker):
    """It provides a Cumin worker for SSH using the ClusterShell library.

    This transport uses the :py:mod:`ClusterShell` Python library to connect to the selected hosts and execute a
    list of commands. This transport accept the following customizations:

    * ``sync`` execution mode: given a list of commands, the first one will be executed on all the hosts, then, if the
      success ratio is reached, the second one will be executed on all hosts where the first one was successful, and so
      on.
    * ``async`` execution mode: given a list of commands, on each hosts the commands will be executed sequentially,
      interrupting the execution on any single host at the first command that fails. The execution on the hosts is
      independent between each other.
    * custom execution mode: can be achieved creating a custom event handler class that extends the ``BaseEventHandler``
      class defined in ``cumin/transports/clustershell.py``, implementing its abstract methods and setting to this class
      object the handler to the transport.
    """

    def __init__(self, config: dict, target: Target) -> None:
        """Worker ClusterShell constructor.

        :Parameters:
            according to parent :py:meth:`cumin.transports.BaseWorker.__init__`.
        """
        super().__init__(config, target)
        self.task = Task.task_self()  # Initialize a ClusterShell task
        self._handler_instance: Optional[Event.EventHandler] = None
        self._reporter: Type[BaseReporter] = TqdmReporter  # TODO: change this to NullReporter when releasing v5.0.0
        self._progress_bars: bool = True  # TODO: change this to False when releasing v5.0.0

        # Set any ClusterShell task options
        for key, value in config.get('clustershell', {}).items():
            if isinstance(value, list):
                self.task.set_info(key, ' '.join(value))
            else:
                self.task.set_info(key, value)

    def execute(self) -> int:
        """Execute the commands on all the targets using the handler.

        Concrete implementation of parent abstract method.

        :Parameters:
            according to parent :py:meth:`cumin.transports.BaseWorker.execute`.
        """
        if not self.commands:
            raise WorkerError('No commands provided.')

        if self.handler is None:
            raise WorkerError('An EventHandler is mandatory.')

        # Instantiate handler
        # Schedule only the first command for the first batch, the following ones must be handled by the EventHandler
        reporter = self._reporter()  # Instantiate a new Reporter at each execution
        self._handler_instance = self.handler(  # pylint: disable=not-callable
            self.target, self.commands, reporter=reporter, success_threshold=self.success_threshold,
            progress_bars=self._progress_bars)

        self.logger.info(
            "Executing commands %s on '%d' hosts: %s", self.commands, len(self.target.hosts), self.target.hosts)
        self.task.shell(self.commands[0].command, nodes=self.target.first_batch, handler=self._handler_instance,
                        timeout=self.commands[0].timeout, stdin=False)

        # FIXME: return_value should not be optional
        return_value: Optional[int] = 0
        try:
            self.task.run(timeout=self.timeout, stdin=False)
            self.task.join()
        except Task.TimeoutError:
            if self._handler_instance is not None:
                self._handler_instance.on_timeout(self.task)
        finally:
            if self._handler_instance is not None:
                self._handler_instance.close(self.task)
                return_value = self._handler_instance.return_value
                if return_value is None:
                    return_value = 3  # The handler did not set a return value

        return return_value

    def get_results(self):
        """Get the results of the last task execution.

        Concrete implementation of parent abstract method.

        :Parameters:
            according to parent :py:meth:`cumin.transports.BaseWorker.get_results`.
        """
        for output, nodelist in self.task.iter_buffers():
            yield nodeset_fromlist(nodelist), output

    @property
    def handler(self) -> Optional[Type['BaseEventHandler']]:
        """Concrete implementation of parent abstract getter and setter.

        Accepted values for the setter:
        * an instance of a custom handler class derived from :py:class:`BaseEventHandler`.
        * a :py:class:`str` with one of the available default handler listed in :py:data:`DEFAULT_HANDLERS`.

        The event handler is mandatory for this transport.

        :Parameters:
            according to parent :py:attr:`cumin.transports.BaseWorker.handler`.
        """
        return self._handler

    @handler.setter
    def handler(self, value: Union[Type['BaseEventHandler'], str]) -> None:
        """Setter for the `handler` property. The relative documentation is in the getter."""
        if isinstance(value, type) and issubclass(value, BaseEventHandler):
            self._handler = value
        elif value in DEFAULT_HANDLERS:
            self._handler = DEFAULT_HANDLERS[value]
        else:
            raise_error(
                'handler',
                'must be one of ({default}, a class object derived from BaseEventHandler)'.format(
                    default=', '.join(DEFAULT_HANDLERS.keys())),
                value)

    @property
    def reporter(self) -> Type['BaseReporter']:
        """Getter for the reporter property.

        It must be a subclass of :py:class:`cumin.transports.clustershell.BaseReporter`.

        """
        return self._reporter

    @reporter.setter
    def reporter(self, value: Type['BaseReporter']) -> None:
        """Setter for the `reporter` property. The relative documentation is in the getter."""
        if not issubclass(value, BaseReporter):
            raise_error('reporter', 'must be a subclass of cumin.transports.clustershell.BaseReporter', value)

        self._reporter = value

    @property
    def progress_bars(self) -> bool:
        """Getter for the boolean progress_bars property."""
        return self._progress_bars

    @progress_bars.setter
    def progress_bars(self, value: bool) -> None:
        """Setter for the `progress_bars` property. The relative documentation is in the getter."""
        if not isinstance(value, bool):
            raise_error('progress_bars', 'must be a boolean', value)

        self._progress_bars = value


class Node:
    """Node class to represent each target node.

    Additional attributes available are:

    .. attribute:: state

       :py:class:`cumin.transports.State`: the state of the node.

    .. attribute:: running_command_index

       :py:class:`int`: the index of the current running command in the list of commands.

    """

    def __init__(self, name: str, commands: List[Command]):
        """Node class constructor with default values.

        Arguments:
            name (str): the hostname of the node.
            commands (list): a list of :py:class:`cumin.transports.Command` objects to be executed on the node.

        """
        self.name = name
        self.commands = commands
        self.state = State()  # Initialize the state machine for this node.
        self.running_command_index = -1  # Pointer to the current running command in self.commands


class BaseReporter(metaclass=ABCMeta):
    """Reporter base class that does not report anything."""

    def __init__(self) -> None:
        """Initializes a Reporter."""
        self.logger = logging.getLogger('.'.join((self.__module__, self.__class__.__name__)))

    @abstractmethod
    def global_timeout_nodes(self, nodes: Dict[str, Node], num_hosts: int) -> None:
        """Print the nodes that were caught by the global timeout in a colored and tqdm-friendly way."""

    @abstractmethod
    def failed_nodes(self, nodes: Dict[str, Node], num_hosts: int, commands: List[Command],
                     filter_command_index: int = -1) -> None:
        """Print the nodes that failed to execute commands in a colored and tqdm-friendly way.

        Arguments:
            nodes (list): the list of Nodes on which commands were executed
            num_hosts (int): the total number of nodes.
            commands (list): the list of Commands that were executed
            filter_command_index (int, optional): print only the nodes that failed to execute the command specified by
                this command index.

        """

    # FIXME: refactor this to reduce number of arguments and pass a more structured execution context
    @abstractmethod
    def success_nodes(self, command: Optional[Command],  # pylint: disable=too-many-arguments
                      num_successfull_nodes: int, success_ratio: float, tot: int,
                      num_hosts: int, success_threshold: float, nodes: Dict[str, Node]) -> None:
        """Print how many nodes successfully executed all commands in a colored and tqdm-friendly way.

        Arguments:
            command (Command): the command that was executed
            num_successfull_nodes (int): the number of nodes on which the execution was successful
            success_ratio (float): the ratio of successful nodes
            tot (int): total number of successful executions
            num_hosts (int): the total number of nodes.
            success_threshold (float): the threshold of successful nodes above which the command execution is deemed
                successful
            nodes (list): the nodes on which the command was executed

        """

    @abstractmethod
    def command_completed(self) -> None:
        """To be called on completion of processing, when no command specific output is required."""

    # FIXME: buffer_iterator should have a more specific type annotation
    @abstractmethod
    def command_output(self, buffer_iterator: Any, command: Optional[Command] = None) -> None:
        """Print the command output in a colored and tqdm-friendly way.

        Arguments:
            buffer_iterator (mixed): any `ClusterShell` object that implements ``iter_buffers()`` like
                :py:class:`ClusterShell.Task.Task` and all the `Worker` objects.
            command (Command, optional): the command the output is referring to.

        """

    @abstractmethod
    def command_header(self, command: str) -> None:
        """Reports a single command execution.

        Arguments:
            command (str): the command the header belongs to.

        """

    @abstractmethod
    def message_element(self, message: MsgTreeElem) -> None:
        """Report a single message as received from the execution of a command on a node.

        Arguments:
            message (ClusterShell.MsgTree.MsgTreeElem): the message to report.

        """


class NullReporter(BaseReporter):  # pylint: disable=abstract-method are all generated dynamically
    """Reporter class that does not report anything."""

    def _callable(self, *args, **kwargs):
        """Just a callable that does nothing."""

    def __new__(cls, *args, **kwargs):
        """Override class instance creation, see Python's data model."""
        for name in cls.__abstractmethods__:
            setattr(cls, name, cls._callable)

        cls.__abstractmethods__ = frozenset()
        return super().__new__(cls, *args, **kwargs)


class TqdmQuietReporter(NullReporter):  # pylint: disable=abstract-method some are generated dynamically
    """Reports the progress of command execution without the command output."""

    short_command_length = 35
    """:py:class:`int`: the length to which a command should be shortened in various outputs."""

    def _report_line(self, message: str,  # pylint: disable=no-self-use
                     color_func: Callable[[str], str] = Colored.red, nodes_string: str = '') -> None:
        """Print a tqdm-friendly colored status line with success/failure ratio and optional list of nodes.

        Arguments:
            message (str): the message to print.
            color_func (function, optional): the coloring function, one of :py:class`cumin.color.Colored` methods.
            nodes_string (str, optional): the string representation of the affected nodes.

        """
        tqdm.write(color_func(message) + Colored.cyan(nodes_string), file=sys.stderr)

    def _get_log_message(self, num: int, num_hosts: int, message: str,  # pylint: disable=no-self-use
                         nodes: Optional[List[str]] = None) -> Tuple[str, str]:
        """Get a pre-formatted message suitable for logging or printing.

        Arguments:
            num (int): the number of affected nodes.
            num_hosts (int): the total number of nodes.
            message (str): the message to print.
            nodes (list, optional): the list of nodes affected.

        Returns:
            tuple: a tuple of ``(logging message, NodeSet of the affected nodes)``.

        """
        if nodes is None:
            nodes_string = ''
            message_end = ''
        else:
            nodes_string = str(nodeset_fromlist(nodes))
            message_end = ': '

        tot = num_hosts
        log_message = '{perc:.1%} ({num}/{tot}) {message}{message_end}'.format(
            perc=(num / tot), num=num, tot=tot, message=message, message_end=message_end)

        return log_message, nodes_string

    def _get_short_command(self, command: Union[str, Command]) -> str:
        """Return a shortened representation of a command omitting the central part, if it's too long.

        Arguments:
            command (str or Command optional): the command to be shortened.

        Returns:
            str: the short command.

        """
        cmd = str(command)
        sublen = (self.short_command_length - 3) // 2  # The -3 is for the ellipsis
        return (cmd[:sublen] + '...' + cmd[-sublen:]) if len(cmd) > self.short_command_length else cmd

    def global_timeout_nodes(self, nodes: Dict[str, Node], num_hosts: int) -> None:
        """Print the nodes that were caught by the global timeout in a colored and tqdm-friendly way.

        :Parameters:
            according to parent :py:meth:`BaseReporter.global_timeout_nodes`.

        """
        timeout = [node.name for node in nodes.values() if node.state.is_timeout]
        timeout_desc = 'of nodes were executing a command when the global timeout occurred'
        timeout_message, timeout_nodes = self._get_log_message(len(timeout), num_hosts=num_hosts,
                                                               message=timeout_desc, nodes=timeout)
        self.logger.error('%s%s', timeout_message, timeout_nodes)
        self._report_line(timeout_message, nodes_string=timeout_nodes)

        not_run = [node.name for node in nodes.values() if node.state.is_pending or node.state.is_scheduled]
        not_run_desc = 'of nodes were pending execution when the global timeout occurred'
        not_run_message, not_run_nodes = self._get_log_message(len(not_run), num_hosts=num_hosts,
                                                               message=not_run_desc, nodes=not_run)
        self.logger.error('%s%s', not_run_message, not_run_nodes)
        self._report_line(not_run_message, nodes_string=not_run_nodes)

    def failed_nodes(self, nodes: Dict[str, Node], num_hosts: int, commands: List[Command],
                     filter_command_index: int = -1) -> None:  # pylint: disable=no-self-use
        """Print the nodes that failed to execute commands in a colored and tqdm-friendly way.

        :Parameters:
            according to parent :py:meth:`BaseReporter.failed_nodes`.

        """
        for state in (State.failed, State.timeout):
            failed_commands = defaultdict(list)
            for node in [node for node in nodes.values() if node.state == state]:
                failed_commands[node.running_command_index].append(node.name)

            for index, failed_nodes in failed_commands.items():
                command = commands[index]

                if filter_command_index >= 0 and command is not None and index != filter_command_index:
                    continue

                short_command = self._get_short_command(command) if command is not None else ''
                message = "of nodes {state} to execute command '{command}'".format(
                    state=State.states_representation[state], command=short_command)
                log_message, nodes_string = self._get_log_message(len(failed_nodes), num_hosts=num_hosts,
                                                                  message=message, nodes=failed_nodes)
                self.logger.error('%s%s', log_message, nodes_string)
                self._report_line(log_message, nodes_string=nodes_string)

    def success_nodes(self, command: Optional[Command],  # pylint: disable=too-many-arguments,too-many-locals
                      num_successfull_nodes: int, success_ratio: float, tot: int,
                      num_hosts: int, success_threshold: float, nodes: Dict[str, Node]) -> None:
        """Print how many nodes successfully executed all commands in a colored and tqdm-friendly way.

        :Parameters:
            according to parent :py:meth:`BaseReporter.success_nodes`.

        """
        if success_ratio < success_threshold:
            comp = '<'
            post = '. Aborting.'
        else:
            comp = '>='
            post = '.'
        message_string = ' of nodes successfully executed all commands'
        if command is not None:
            message_string = " for command: '{command}'".format(command=self._get_short_command(command))
        nodes_to_log = None
        if num_successfull_nodes not in (0, tot):
            nodes_to_log = [node.name for node in nodes.values() if node.state.is_success]
        message = "success ratio ({comp} {perc:.1%} threshold){message_string}{post}".format(
            comp=comp, perc=success_threshold, message_string=message_string, post=post)
        log_message, nodes_string = self._get_log_message(num_successfull_nodes, num_hosts=num_hosts,
                                                          message=message, nodes=nodes_to_log)
        if num_successfull_nodes == tot:
            color_func = Colored.green
            level = logging.INFO
        elif success_ratio >= success_threshold:
            color_func = Colored.yellow
            level = logging.WARNING
        else:
            color_func = Colored.red
            level = logging.CRITICAL
        self.logger.log(level, '%s%s', log_message, nodes_string)
        self._report_line(log_message, color_func=color_func, nodes_string=nodes_string)


class TqdmReporter(TqdmQuietReporter):
    """Reports the progress of command execution with full command output."""

    def command_completed(self) -> None:  # pylint: disable=no-self-use
        """To be called on completion of processing, when no command specific output is required.

        :Parameters:
            according to parent :py:meth:`BaseReporter.command_completed`.

        """
        tqdm.write(Colored.blue('================'), file=sys.stdout)

    def command_output(self, buffer_iterator: Any, command: Optional[Command] = None) -> None:
        """Print the command output in a colored and tqdm-friendly way.

        :Parameters:
            according to parent :py:meth:`BaseReporter.command_output`.

        """
        nodelist = None
        if command is not None:
            output_message = "----- OUTPUT of '{command}' -----".format(command=self._get_short_command(command))
        else:
            output_message = '----- OUTPUT -----'

        for output, nodelist in buffer_iterator.iter_buffers():
            tqdm.write(Colored.blue('===== NODE GROUP ====='), file=sys.stdout)
            tqdm.write(Colored.cyan('({num}) {nodes}'.format(num=len(nodelist), nodes=nodeset_fromlist(nodelist))),
                       file=sys.stdout)
            tqdm.write(Colored.blue(output_message), file=sys.stdout)
            tqdm.write(output.message().decode(), file=sys.stdout)

        if nodelist is None:
            message = '===== NO OUTPUT ====='
        else:
            message = '================'

        tqdm.write(Colored.blue(message), file=sys.stdout)

    def command_header(self, command: str) -> None:
        """Reports a single command execution.

        :Parameters:
            according to parent :py:meth:`BaseReporter.command_header`.

        """
        output_message = "----- OUTPUT of '{command}' -----".format(command=self._get_short_command(command))
        tqdm.write(Colored.blue(output_message), file=sys.stdout)

    def message_element(self, message: MsgTreeElem) -> None:  # pylint: disable=no-self-use
        """Report a single message as received from the execution of a command on a node.

        :Parameters:
            according to parent :py:meth:`BaseReporter.message_element`.

        """
        tqdm.write(message.decode(), file=sys.stdout)


class BaseEventHandler(Event.EventHandler):
    """ClusterShell event handler base class.

    Inherit from :py:class:`ClusterShell.Event.EventHandler` class and define a base `EventHandler` class to be used
    in Cumin. It can be subclassed to generate custom `EventHandler` classes while taking advantage of some common
    functionalities.
    """

    # FIXME: not sure what the type of **kwargs should be
    def __init__(self, target: Target, commands: List[Command], reporter: BaseReporter,
                 success_threshold: float = 1.0, progress_bars: bool = True, **kwargs: Any) -> None:
        """Event handler ClusterShell extension constructor.

        Arguments:
            target (cumin.transports.Target): a Target instance.
            commands (list): the list of Command objects that has to be executed on the nodes.
            reporter (cumin.transports.clustershell.BaseReporter): reporter used to output progress.
            success_threshold (float, optional): the success threshold, a :py:class:`float` between ``0`` and ``1``,
                to consider the execution successful.
            progress_bars (bool): should progress bars be displayed
            **kwargs (optional): additional keyword arguments that might be used by derived classes.

        """
        super().__init__()
        self.success_threshold = success_threshold
        self.logger = logging.getLogger('.'.join((self.__module__, self.__class__.__name__)))
        self.target = target
        self.lock = threading.Lock()  # Used to update instance variables coherently from within callbacks

        # Execution management variables
        self.return_value: Optional[int] = None
        self.commands = commands
        self.kwargs = kwargs  # Allow to store custom parameters from subclasses without changing the signature
        self.counters: Dict[str, int] = Counter()
        self.counters['total'] = len(target.hosts)
        self.deduplicate_output = self.counters['total'] > 1
        self.global_timedout = False
        # Instantiate all the node instances, slicing the commands list to get a copy
        self.nodes = {node: Node(node, commands[:]) for node in target.hosts}
        # Move already all the nodes in the first_batch to the scheduled state, it means that ClusterShell was
        # already instructed to execute a command on those nodes
        for node_name in target.first_batch:
            self.nodes[node_name].state.update(State.scheduled)

        self.progress: BaseExecutionProgress = TqdmProgressBars() if progress_bars else NoProgress()
        self.reporter = reporter

    def close(self, task):
        """Additional method called at the end of the whole execution, useful for reporting and final actions.

        Arguments:
            task (ClusterShell.Task.Task): a ClusterShell Task instance.

        """
        raise NotImplementedError

    def on_timeout(self, task):
        """Update the state of the nodes and the timeout counter.

        Callback called by the :py:class:`ClusterShellWorker` when a :py:exc:`ClusterShell.Task.TimeoutError` is
        raised. It means that the whole execution timed out.

        Arguments:
            task (ClusterShell.Task.Task): a ClusterShell Task instance.

        """
        num_timeout = task.num_timeout()
        self.logger.error('Global timeout was triggered while %d nodes were executing a command', num_timeout)

        with self.lock:  # Avoid modifications of the same data from other callbacks triggered by ClusterShell
            self.global_timedout = True
            # Considering timed out also the nodes that were pending the execution (for example when executing in
            # batches) and those that were already scheduled (for example when the # of nodes is greater than
            # ClusterShell fanout)
            pending_or_scheduled = sum(
                (node.state.is_pending or node.state.is_scheduled
                 or (node.state.is_success and node.running_command_index < (len(node.commands) - 1))
                 ) for node in self.nodes.values())
            if pending_or_scheduled > 0:
                self.progress.update_failed(num_timeout + pending_or_scheduled)

        if self.global_timedout:
            self.reporter.global_timeout_nodes(self.nodes, self.counters['total'])

    def ev_pickup(self, worker, node):
        """Command execution started on a node, remove the command from the node's queue.

        This callback is triggered by the `ClusterShell` library for each node when it starts executing a command.

        :Parameters:
            according to parent :py:meth:`ClusterShell.Event.EventHandler.ev_pickup`.
        """
        self.logger.debug("node=%s, command='%s'", node, worker.command)

        with self.lock:  # Avoid modifications of the same data from other callbacks triggered by ClusterShell
            curr_node = self.nodes[node]
            curr_node.state.update(State.running)  # Update the node's state to running

            command = curr_node.commands[curr_node.running_command_index + 1].command
            # Security check, it should never be triggered
            if command != worker.command:
                raise WorkerError("ev_pickup: got unexpected command '{command}', expected '{expected}'".format(
                    command=command, expected=worker.command))
            curr_node.running_command_index += 1  # Move the pointer of the current command

        if not self.deduplicate_output:
            self.reporter.command_header(worker.command)

    def ev_read(self, worker, node, _, msg):
        """Worker has data to read from a specific node. Print it if running on a single host.

        This callback is triggered by ClusterShell for each node when output is available.

        :Parameters:
            according to parent :py:meth:`ClusterShell.Event.EventHandler.ev_read`.
        """
        if self.deduplicate_output:
            return

        with self.lock:
            self.reporter.message_element(msg)

    def ev_close(self, worker, timedout):
        """Worker has finished or timed out.

        This callback is triggered by ClusterShell when the execution has completed or timed out.

        :Parameters:
            according to parent :py:meth:`ClusterShell.Event.EventHandler.ev_close`.
        """
        if not timedout:
            return

        delta_timeout = worker.task.num_timeout() - self.counters['timeout']
        self.logger.debug("command='%s', delta_timeout=%d", worker.command, delta_timeout)

        with self.lock:  # Avoid modifications of the same data from other callbacks triggered by ClusterShell
            self.progress.update_failed(delta_timeout)
            self.counters['timeout'] = worker.task.num_timeout()
            for node in worker.task.iter_keys_timeout():
                if not self.nodes[node].state.is_timeout:
                    self.nodes[node].state.update(State.timeout)

        # Schedule a timer to run the current command on the next node or start the next command
        worker.task.timer(self.target.batch_sleep, worker.eh)

    def _success_nodes_report(self, command: Optional[Command] = None) -> None:
        """Print how many nodes successfully executed all commands in a colored and tqdm-friendly way.

        Arguments:
            command (Command, optional): the command the report is referring to.

        """
        if self.global_timedout and command is None:
            num = sum(1 for node in self.nodes.values() if node.state.is_success
                      and node.running_command_index == (len(self.commands) - 1))
        else:
            num = self.counters['success']

        tot = self.counters['total']
        success_ratio = num / tot

        self.reporter.success_nodes(command, num, success_ratio, tot, self.counters['total'],
                                    self.success_threshold, self.nodes)


class SyncEventHandler(BaseEventHandler):
    """Custom ClusterShell event handler class that execute commands synchronously.

    The implemented logic is:

    * execute command `#N` on all nodes where command #`N-1` was successful according to `batch_size`.
    * the success ratio is checked at each command completion on every node, and will abort if not met, however
      nodes already scheduled for execution with `ClusterShell` will execute the command anyway. The use of the
      `batch_size` allow to control this aspect.
    * if the execution of command `#N` is completed and the success ratio is greater than the success threshold,
      re-start from the top with `N=N+1`.

    The typical use case is to orchestrate some operation across a fleet, ensuring that each command is completed by
    enough nodes before proceeding with the next one.
    """

    def __init__(self, target: Target, commands: List[Command], reporter: BaseReporter,
                 success_threshold: float = 1.0, progress_bars: bool = True, **kwargs: Any) -> None:
        """Define a custom ClusterShell event handler to execute commands synchronously.

        :Parameters:
            according to parent :py:meth:`BaseEventHandler.__init__`.

        """
        super().__init__(target, commands, reporter, success_threshold=success_threshold,
                         progress_bars=progress_bars, **kwargs)
        self.current_command_index = 0  # Global pointer for the current command in execution across all nodes
        self.start_command()
        self.aborted = False

    def start_command(self, schedule: bool = False) -> None:
        """Initialize progress bars and variables for this command execution.

        Executed at the start of each command.

        Arguments:
            schedule (bool, optional): whether the next command should be sent to ClusterShell for execution or not.

        """
        self.counters['success'] = 0

        self.progress.init(self.counters['total'])

        # Schedule the next command, the first was already scheduled by ClusterShellWorker.execute()
        if schedule:
            with self.lock:  # Avoid modifications of the same data from other callbacks triggered by ClusterShell
                # Available nodes for the next command execution were already update back to the pending state
                remaining_nodes = [node.name for node in self.nodes.values() if node.state.is_pending]
                first_batch = remaining_nodes[:self.target.batch_size]
                first_batch_set = nodeset_fromlist(first_batch)
                for node_name in first_batch:
                    self.nodes[node_name].state.update(State.scheduled)

            command = self.commands[self.current_command_index]
            self.logger.debug(
                "command='%s', timeout=%s, first_batch=%s", command.command, command.timeout, first_batch_set)

            # Schedule the command for execution in ClusterShell
            Task.task_self().flush_buffers()
            Task.task_self().shell(command.command, nodes=first_batch_set, handler=self, timeout=command.timeout)

    def end_command(self) -> bool:
        """Command terminated, print the result and schedule the next command if criteria are met.

        Executed at the end of each command inside a lock.

        Returns:
            bool: :py:data:`True` if the next command should be scheduled, :py:data:`False` otherwise.

        """
        if self.deduplicate_output:
            self.reporter.command_output(Task.task_self(), command=self.commands[self.current_command_index])
        else:
            self.reporter.command_completed()

        self.progress.close()

        self.reporter.failed_nodes(nodes=self.nodes, num_hosts=self.counters['total'], commands=self.commands,
                                   filter_command_index=self.current_command_index)
        self._success_nodes_report(command=self.commands[self.current_command_index])

        success_ratio = self.counters['success'] / self.counters['total']

        # Abort on failure
        if success_ratio < self.success_threshold:
            self.return_value = 2
            self.aborted = True  # Tells other timers that might trigger after that the abort is already in progress
            return False

        if success_ratio == 1:
            self.return_value = 0
        else:
            self.return_value = 1

        if self.current_command_index == (len(self.commands) - 1):
            self.logger.debug('This was the last command')
            return False  # This was the last command

        return True

    def on_timeout(self, task: Task) -> None:
        """Override parent class `on_timeout` method to run `end_command`.

        :Parameters:
            according to parent :py:meth:`BaseEventHandler.on_timeout`.
        """
        super().on_timeout(task)
        self.end_command()

    def ev_hup(self, worker, node, rc):
        """Command execution completed on a node.

        This callback is triggered by ClusterShell for each node when it completes the execution of a command.
        Update the progress bars and keep track of nodes based on the success/failure of the command's execution.
        Schedule a timer for further decisions.

        :Parameters:
            according to parent :py:meth:`ClusterShell.Event.EventHandler.ev_hup`.
        """
        self.logger.debug("node=%s, rc=%d, command='%s'", node, rc, worker.command)

        with self.lock:  # Avoid modifications of the same data from other callbacks triggered by ClusterShell
            curr_node = self.nodes[node]

            ok_codes = curr_node.commands[curr_node.running_command_index].ok_codes
            if rc in ok_codes or not ok_codes:
                self.progress.update_success()
                self.counters['success'] += 1
                new_state = State.success
            else:
                self.progress.update_failed()
                self.counters['failed'] += 1
                new_state = State.failed

            curr_node.state.update(new_state)

        # Schedule a timer to run the current command on the next node or start the next command
        worker.task.timer(self.target.batch_sleep, worker.eh)

    def ev_timer(self, timer):  # noqa, mccabe: MC0001 too complex (15) FIXME
        """Schedule the current command on the next node or the next command on the first batch of nodes.

        This callback is triggered by `ClusterShell` when a scheduled `Task.timer()` goes off.

        :Parameters:
            according to parent :py:meth:`ClusterShell.Event.EventHandler.ev_timer`.
        """
        success_ratio = 1 - ((self.counters['failed'] + self.counters['timeout']) / self.counters['total'])

        node = None
        if success_ratio >= self.success_threshold:
            # Success ratio is still good, looking for the next node
            with self.lock:  # Avoid modifications of the same data from other callbacks triggered by ClusterShell
                for new_node in self.nodes.values():
                    if new_node.state.is_pending:
                        # Found the next node where to execute the command
                        node = new_node
                        node.state.update(State.scheduled)
                        break

        if node is not None:
            # Schedule the execution with ClusterShell of the current command to the next node found above
            command = self.nodes[node.name].commands[self.nodes[node.name].running_command_index + 1]
            self.logger.debug("next_node=%s, timeout=%s, command='%s'", node.name, command.command, command.timeout)
            Task.task_self().shell(command.command, handler=timer.eh, timeout=command.timeout, nodes=nodeset(node.name))
            return

        # No more nodes were left for the execution of the current command
        with self.lock:  # Avoid modifications of the same data from other callbacks triggered by ClusterShell
            try:
                command: Optional[str] = self.commands[self.current_command_index].command
            except IndexError:
                command: Optional[str] = None  # Last command reached

            # Get a list of the nodes still in pending state
            pending = [pending_node.name for pending_node in self.nodes.values() if pending_node.state.is_pending]
            # Nodes in running are still running the command and nodes in scheduled state will execute the command
            # anyway, they were already offloaded to ClusterShell
            accounted = len(pending) + self.counters['failed'] + self.counters['success'] + self.counters['timeout']

            # Avoid race conditions
            if self.aborted or accounted != self.counters['total'] or command is None or self.global_timedout:
                self.logger.debug("Skipped timer")
                return

            if pending:
                # This usually happens when executing in batches
                self.logger.warning("Command '%s' was not executed on: %s", command, nodeset_fromlist(pending))

            self.logger.info("Completed command '%s'", command)
            restart = self.end_command()
            self.current_command_index += 1  # Move the global pointer of the command in execution

            if restart:
                for node in self.nodes.values():
                    if node.state.is_success:
                        # Only nodes in pending state will be scheduled for the next command
                        node.state.update(State.pending)

        if restart:
            self.start_command(schedule=True)

    def close(self, task: Task) -> None:
        """Concrete implementation of parent abstract method to print the success nodes report.

        :Parameters:
            according to parent :py:meth:`cumin.transports.BaseEventHandler.close`.
        """
        self._success_nodes_report()


class AsyncEventHandler(BaseEventHandler):
    """Custom ClusterShell event handler class that execute commands asynchronously.

    The implemented logic is:

    * execute on all nodes independently every command in a sequence, aborting the execution on that node if any
      command fails.
    * The success ratio is checked at each node completion (either because it completed all commands or aborted
      earlier), however nodes already scheduled for execution with ClusterShell will execute the commands anyway. The
      use of the batch_size allows to control this aspect.
    * if the success ratio is met, schedule the execution of all commands to the next node.

    The typical use case is to execute read-only commands to gather the status of a fleet without any special need of
    orchestration between the nodes.
    """

    def __init__(self, target: Target, commands: List[Command], reporter: BaseReporter,
                 success_threshold: float = 1.0, progress_bars: bool = True, **kwargs: Any) -> None:
        """Define a custom ClusterShell event handler to execute commands asynchronously between nodes.

        :Parameters:
            according to parent :py:meth:`BaseEventHandler.__init__`.
        """
        super().__init__(target, commands, reporter, success_threshold=success_threshold,
                         progress_bars=progress_bars, **kwargs)

        self.progress.init(self.counters['total'])

    def ev_hup(self, worker, node, rc):
        """Command execution completed on a node.

        This callback is triggered by ClusterShell for each node when it completes the execution of a command.
        Enqueue the next command if the success criteria are met, track the failure otherwise. Update the progress
        bars accordingly.

        :Parameters:
            according to parent :py:meth:`ClusterShell.Event.EventHandler.ev_hup`.
        """
        self.logger.debug("node=%s, rc=%d, command='%s'", node, rc, worker.command)

        schedule_next = False
        schedule_timer = False
        with self.lock:  # Avoid modifications of the same data from other callbacks triggered by ClusterShell
            curr_node = self.nodes[node]

            ok_codes = curr_node.commands[curr_node.running_command_index].ok_codes
            if rc in ok_codes or not ok_codes:
                if curr_node.running_command_index == (len(curr_node.commands) - 1):
                    self.progress.update_success()
                    self.counters['success'] += 1
                    curr_node.state.update(State.success)
                    schedule_timer = True  # Continue the execution on other nodes if criteria are met
                else:
                    schedule_next = True  # Continue the execution in the current node with the next command
            else:
                self.progress.update_failed()
                self.counters['failed'] += 1
                curr_node.state.update(State.failed)
                schedule_timer = True  # Continue the execution on other nodes if criteria are met

        if schedule_next:
            # Schedule the execution of the next command on this node with ClusterShell
            command = curr_node.commands[curr_node.running_command_index + 1]
            worker.task.shell(
                command.command, nodes=nodeset(node), handler=worker.eh, timeout=command.timeout, stdin=False)
        elif schedule_timer:
            # Schedule a timer to allow to run all the commands in the next available node
            worker.task.timer(self.target.batch_sleep, worker.eh)

    def ev_timer(self, timer):
        """Schedule the current command on the next node or the next command on the first batch of nodes.

        This callback is triggered by `ClusterShell` when a scheduled `Task.timer()` goes off.

        :Parameters:
            according to parent :py:meth:`ClusterShell.Event.EventHandler.ev_timer`.
        """
        success_ratio = 1 - ((self.counters['failed'] + self.counters['timeout']) / self.counters['total'])

        node = None
        if success_ratio >= self.success_threshold:
            # Success ratio is still good, looking for the next node
            with self.lock:  # Avoid modifications of the same data from other callbacks triggered by ClusterShell
                for new_node in self.nodes.values():
                    if new_node.state.is_pending:
                        # Found the next node where to execute all the commands
                        node = new_node
                        node.state.update(State.scheduled)
                        break

        if node is not None:
            # Schedule the execution of the first command to the next node with ClusterShell
            command = node.commands[0]
            self.logger.debug("next_node=%s, timeout=%s, command='%s'", node.name, command.command, command.timeout)
            Task.task_self().shell(
                command.command, handler=timer.eh, timeout=command.timeout, nodes=nodeset(node.name))
        else:
            self.logger.debug('No more nodes left')

    def close(self, task: Task) -> None:
        """Concrete implementation of parent abstract method to print the nodes reports and close progress bars.

        :Parameters:
            according to parent :py:meth:`cumin.transports.BaseEventHandler.close`.
        """
        if self.deduplicate_output:
            self.reporter.command_output(task)
        else:
            self.reporter.command_completed()

        self.progress.close()

        self.reporter.failed_nodes(nodes=self.nodes, num_hosts=self.counters['total'], commands=self.commands)
        self._success_nodes_report()

        num = self.counters['success']
        tot = self.counters['total']
        success_ratio = num / tot

        if success_ratio == 1:
            self.return_value = 0
        elif success_ratio < self.success_threshold:
            self.return_value = 2
        else:
            self.return_value = 1


worker_class: Type[BaseWorker] = ClusterShellWorker  # pylint: disable=invalid-name
"""Required by the transport auto-loader in :py:meth:`cumin.transport.Transport.new`."""

DEFAULT_HANDLERS: Dict[str, Type[Event.EventHandler]] = {'sync': SyncEventHandler, 'async': AsyncEventHandler}
"""dict: mapping of available default event handlers for :py:class:`ClusterShellWorker`."""
