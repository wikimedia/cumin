"""Transport ClusterShell: worker and event handlers."""
import logging
import sys
import threading

from abc import ABCMeta, abstractmethod
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Callable, Optional, Type, Union

from ClusterShell import Event, Task
from ClusterShell.Engine.Engine import EngineTimer
from ClusterShell.MsgTree import MsgTree, MsgTreeElem
from ClusterShell.NodeSet import NodeSet
from tqdm import tqdm

from cumin import nodeset, nodeset_fromlist, transports
from cumin.color import Colored
from cumin.transports import HostState  # Direct import to be DRY as it's used many times


class ClusterShellWorker(transports.BaseWorker):
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

    def __init__(self, config: dict, target: transports.Target) -> None:
        """Worker ClusterShell constructor.

        :Parameters:
            according to parent :py:meth:`cumin.transports.BaseWorker.__init__`.
        """
        super().__init__(config, target)
        self.task = Task.task_self()  # Initialize a ClusterShell task
        self._handler_instance: Optional['BaseEventHandler'] = None
        self._reporter: Type[BaseReporter] = TqdmReporter  # TODO: change this to NullReporter when releasing v5.0.0
        self._progress_bars: bool = True  # TODO: change this to False when releasing v5.0.0

        # Set any ClusterShell task options
        for key, value in config.get('clustershell', {}).items():
            if isinstance(value, list):
                self.task.set_info(key, ' '.join(value))
            else:
                self.task.set_info(key, value)

        # Disable ClusterShell's default MsgTree instances. Those are managed by the custom EventHandlers.
        self.task.set_default('stdout_msgtree', False)
        self.task.set_default('stderr_msgtree', False)

    @property
    def results(self) -> transports.ExecutionResults:
        """Property to access the results instance after having executed the commands.

        Concrete implementation of parent abstract property.

        """
        if self._handler_instance is None:
            raise transports.WorkerError('Execution has not started yet, no results available')

        return self._handler_instance.run_report.get_results()

    def execute(self) -> int:
        """Execute the commands on all the targets using the handler.

        Concrete implementation of parent abstract method.

        :Parameters:
            according to parent :py:meth:`cumin.transports.BaseWorker.execute`.

        """
        results = self.run()
        return results.return_code

    def run(self) -> transports.ExecutionResults:
        """Execute the commands on all the targets using the handler.

        Concrete implementation of parent abstract method.

        :Parameters:
            according to parent :py:meth:`cumin.transports.BaseWorker.execute`.
        """
        if not self.commands:
            raise transports.WorkerError('No commands provided.')

        if self.handler is None:
            raise transports.WorkerError('An EventHandler is mandatory.')

        # Instantiate handler
        # Schedule only the first command for the first batch, the following ones must be handled by the EventHandler
        reporter = self._reporter()  # Instantiate a new Reporter at each execution
        progress_bars_instance = transports.TqdmProgressBars() if self._progress_bars else transports.NoProgress()
        self._handler_instance = self.handler(  # pylint: disable=not-callable
            self.target, self.commands, reporter=reporter, success_threshold=self.success_threshold,
            progress_bars=progress_bars_instance)

        self.logger.info(
            "Executing commands %s on '%d' hosts: %s", self.commands, len(self.target.hosts), self.target.hosts)
        self.task.shell(self.commands[0].command, nodes=self.target.first_batch, handler=self._handler_instance,
                        timeout=self.commands[0].timeout, stdin=False)

        try:
            self.task.run(timeout=self.timeout, stdin=False)
            self.task.join()
        except Task.TimeoutError:
            if self._handler_instance is not None:
                self._handler_instance.run_report.status = transports.ExecutionStatus.TIMEDOUT
                self._handler_instance.on_timeout(self.task)
        except KeyboardInterrupt:
            if self._handler_instance is not None:
                self._handler_instance.run_report.status = transports.ExecutionStatus.INTERRUPTED
            raise
        finally:
            if self._handler_instance is not None:
                self._handler_instance.close(self.task)

        return self.results

    def get_results(self):
        """Get the results of the last task execution.

        Concrete implementation of parent abstract method.

        :Parameters:
            according to parent :py:meth:`cumin.transports.BaseWorker.get_results`.
        """
        for command_results in self._handler_instance.run_report.commands_results:
            for output, nodelist in command_results.outputs['stdout'].walk():
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
            transports.raise_error(
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
            transports.raise_error(
                'reporter', 'must be a subclass of cumin.transports.clustershell.BaseReporter', value)

        self._reporter = value

    @property
    def progress_bars(self) -> bool:
        """Getter for the boolean progress_bars property."""
        return self._progress_bars

    @progress_bars.setter
    def progress_bars(self, value: bool) -> None:
        """Setter for the `progress_bars` property. The relative documentation is in the getter."""
        if not isinstance(value, bool):
            transports.raise_error('progress_bars', 'must be a boolean', value)
        self._progress_bars = value


@dataclass(kw_only=True)
class HostRun:
    """Class to keep track of the execution run for a single host.

    Arguments:
        name (str): the hostname used to connect to it, usually the FQDN.
        commands (list): the list of commands instances to execute.
        return_codes (list): the list of return codes for each executed command.
        last_executed_command_index (int): the index of the last executed command from the ``commands`` list on this
            host.
        state (cumin.transports.State): the current state of the host.

    """
    name: str
    commands: list[transports.Command]
    return_codes: list[int] = field(default_factory=list)
    last_executed_command_index: int = -1
    state: transports.State = field(default_factory=transports.State)

    @property
    def has_completed(self) -> bool:
        """Whether the host has executed all commands.

        Returns:
            bool: :py:data:`True` if the host has executed all commands, :py:data:`False` otherwise.

        """
        return self.last_executed_command_index == (len(self.commands) - 1)


class ExecutionRun:
    """Class to keep track of the whole execution progress."""

    def __init__(self, *, commands: list[transports.Command], hosts: NodeSet):
        """Initialize the instance.

        Arguments:
            commands (list): the list of commands instances to execute.
            hosts (ClusterShell.NodeSet.NodeSet): the set of hosts to target.

        """
        self.last_executed_command_index: int = -1
        self.commands = list(commands)  # Make a copy
        self.initial_hosts = nodeset(hosts)  # Make a copy
        self.total = len(hosts)

        self.status = transports.ExecutionStatus.UNKNOWN
        self.commands_results: list[SimpleNamespace] = [self.init_command_results(i) for i in range(len(self.commands))]
        self.hosts = {name: HostRun(name=name, commands=self.commands) for name in self.initial_hosts}

    def next_host(self, state: HostState) -> Optional[HostRun]:
        """Get the next available host in a given state.

        Arguments:
            state (cumin.transports.HostState): the state a host must be to be selected.

        Returns:
            None: if no host was found with the given state.
            cumin.transports.clustershell.HostRun: the host instance if one is found.

        """
        for host in self.hosts.values():
            if host.state.current is state:
                return host

        return None

    def get_counter(self) -> Counter:
        """Helper method to get a Counter instance with all the hosts by state.

        Returns:
            Counter: the counter instance with keys that are :py:class:`cumin.transports.HostState` instances.

        """
        counter: Counter[HostState] = Counter()
        for host in self.hosts.values():
            counter[host.state.current] += 1

        return counter

    def init_command_results(self, index: int) -> SimpleNamespace:
        """Initialize a simple object to keep track of the execution of a given command.

        Arguments:
            index (int): the index of the command from the ``commands`` list on this host to track.

        Returns:
            types.SimpleNamespace: the simple object.

        """
        command = SimpleNamespace()
        command.command = self.commands[index]
        command.command_index = index
        command.outputs = {'stdout': MsgTree(), 'stderr': MsgTree()}
        return command

    def get_targets(self) -> list[transports.TargetedHosts]:
        """Helper method to get the TargetedHosts instances when returning the final results.

        Returns:
            list: a list of :py:class:`cumin.transports.TargetedHosts` instances, one for each executed command.

        """
        targets: list[SimpleNamespace] = []
        for index in range(len(self.commands)):
            target = SimpleNamespace()
            target.all = nodeset()
            target.by_state = defaultdict(nodeset)
            target.by_return_code = defaultdict(nodeset)
            targets.append(target)

        for host in self.hosts.values():
            for ok_index in range(host.last_executed_command_index):
                target = targets[ok_index]
                target.all.add(host.name)
                target.by_state[HostState.SUCCESS].add(host.name)
                target.by_return_code[host.return_codes[ok_index]].add(host.name)

            index = host.last_executed_command_index if host.last_executed_command_index > -1 else 0
            target = targets[index]
            target.all.add(host.name)
            target.by_state[host.state.current].add(host.name)
            if len(host.return_codes) >= index + 1:
                target.by_return_code[host.return_codes[host.last_executed_command_index]].add(host.name)

        return [
            transports.get_targeted_hosts(
                all_hosts=target.all,
                by_state=dict(target.by_state),
                by_return_code=dict(target.by_return_code),
            ) for target in targets
        ]

    def get_command_outputs(self, index: int) -> tuple[transports.HostsOutputResult, ...]:
        """Get the command outputs for a given command index.

        Arguments:
            index (int): the index of the command from the ``commands`` list on this host to track.

        Returns:
            list: the list of command outputs.

        """
        command_outputs = []
        command_results = self.commands_results[index]
        for stdout, nodelist in command_results.outputs['stdout'].walk():
            command_outputs.append(
                transports.HostsOutputResult(
                    hosts=nodeset_fromlist(nodelist),
                    output=transports.CommandOutputResult(
                        splitted_stderr=False,
                        command=command_results.command,
                        command_index=command_results.command_index,
                        _stdout=stdout,
                    ),
                )
            )

        return tuple(command_outputs)

    def get_results(self) -> transports.ExecutionResults:
        """Get the final results in the cumin's API representation.

        Returns:
            cumin.transports.ExecutionResults: the results instance.

        """
        targets = self.get_targets()
        commands_results = []
        for index, command_results in enumerate(self.commands_results):
            commands_results.append(
                transports.CommandResults(
                    command=command_results.command,
                    command_index=command_results.command_index,
                    targets=targets[index],
                    outputs=self.get_command_outputs(index),
                )
            )

        hosts_results = {}
        for name, host in self.hosts.items():
            host_outputs = []
            for index in range(host.last_executed_command_index + 1):
                host_outputs.append(
                    transports.CommandOutputResult(
                        splitted_stderr=False,
                        command=host.commands[index],
                        command_index=index,
                        _stdout=self.commands_results[index].outputs['stdout'].get(name, MsgTreeElem()),
                    )
                )

            hosts_results[name] = transports.HostResults(
                name=name,
                state=host.state.current,
                commands=tuple(host.commands),
                last_executed_command_index=host.last_executed_command_index,
                return_codes=tuple(host.return_codes),
                outputs=tuple(host_outputs),
            )

        return transports.ExecutionResults(
            status=self.status,
            last_executed_command_index=self.last_executed_command_index,
            commands_results=tuple(commands_results),
            hosts_results=hosts_results,
        )


class BaseReporter(metaclass=ABCMeta):
    """Reporter base class that does not report anything."""

    def __init__(self) -> None:
        """Initializes a Reporter."""
        self.logger = logging.getLogger('.'.join((self.__module__, self.__class__.__name__)))

    @abstractmethod
    def global_timeout_nodes(self, nodes: dict[str, HostRun]) -> None:
        """Print the nodes that were caught by the global timeout in a colored and tqdm-friendly way.

        Arguments:
            nodes (dict): the mapping of the nodes processed.

        """

    @abstractmethod
    def failed_nodes(self, nodes: dict[str, HostRun], num_hosts: int,
                     commands: list[transports.Command], filter_command_index: int = -1) -> None:
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
    def success_nodes(self, command: Optional[transports.Command],  # pylint: disable=too-many-arguments
                      num_successfull_nodes: int, success_ratio: float, num_hosts: int, success_threshold: float,
                      nodes: dict[str, HostRun]) -> None:
        """Print how many nodes successfully executed all commands in a colored and tqdm-friendly way.

        Arguments:
            command (cumin.transports.Command): the command that was executed
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

    @abstractmethod
    def command_output(self, command_outputs: tuple[transports.HostsOutputResult, ...]) -> None:
        """Print the command output in a colored and tqdm-friendly way.

        Arguments:
            command_outputs (list): the list of command outputs instances.

        """

    @abstractmethod
    def command_header(self, command: transports.Command) -> None:
        """Reports a single command execution.

        Arguments:
            command (cumin.transports.Command): the command the header belongs to.

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
                         nodes: Optional[list[str]] = None) -> tuple[str, str]:
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

    def global_timeout_nodes(self, nodes: dict[str, HostRun]) -> None:
        """Print the nodes that were caught by the global timeout in a colored and tqdm-friendly way.

        :Parameters:
            according to parent :py:meth:`BaseReporter.global_timeout_nodes`.

        """
        num_hosts = len(nodes)
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

    def failed_nodes(
        self, nodes: dict[str, HostRun], num_hosts: int,
        commands: list[transports.Command], filter_command_index: int = -1,
    ) -> None:  # pylint: disable=no-self-use
        """Print the nodes that failed to execute commands in a colored and tqdm-friendly way.

        :Parameters:
            according to parent :py:meth:`BaseReporter.failed_nodes`.

        """
        for state in (HostState.FAILED, HostState.TIMEOUT):
            failed_commands = defaultdict(list)
            for node in [node for node in nodes.values() if node.state.current is state]:
                failed_commands[node.last_executed_command_index].append(node.name)

            for index, failed_nodes in failed_commands.items():
                command = commands[index]

                if filter_command_index >= 0 and command is not None and index != filter_command_index:
                    continue

                short_command = command.shortened() if command is not None else ''
                message = "of nodes {state} to execute command '{command}'".format(
                    state=state, command=short_command)
                log_message, nodes_string = self._get_log_message(len(failed_nodes), num_hosts=num_hosts,
                                                                  message=message, nodes=failed_nodes)
                self.logger.error('%s%s', log_message, nodes_string)
                self._report_line(log_message, nodes_string=nodes_string)

    def success_nodes(self, command: Optional[transports.Command],  # pylint: disable=too-many-arguments,too-many-locals
                      num_successfull_nodes: int, success_ratio: float, num_hosts: int, success_threshold: float,
                      nodes: dict[str, HostRun]) -> None:
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
            message_string = " for command: '{command}'".format(command=command.shortened())
        nodes_to_log = None
        if num_successfull_nodes not in (0, num_hosts):
            nodes_to_log = [node.name for node in nodes.values() if node.state.is_success]
        message = "success ratio ({comp} {perc:.1%} threshold){message_string}{post}".format(
            comp=comp, perc=success_threshold, message_string=message_string, post=post)
        log_message, nodes_string = self._get_log_message(num_successfull_nodes, num_hosts=num_hosts,
                                                          message=message, nodes=nodes_to_log)
        if num_successfull_nodes == num_hosts:
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

    def command_output(self, command_outputs: tuple[transports.HostsOutputResult, ...]) -> None:
        """Print the command output in a colored and tqdm-friendly way.

        :Parameters:
            according to parent :py:meth:`BaseReporter.command_output`.

        """
        for command_output in command_outputs:
            tqdm.write(Colored.blue('===== NODE GROUP ====='), file=sys.stdout)
            tqdm.write(
                Colored.cyan('({num}) {nodes}'.format(num=len(command_output.hosts), nodes=command_output.hosts)),
                file=sys.stdout)
            tqdm.write(command_output.output.format(colored=True), file=sys.stdout)

        if command_outputs:
            message = '================'
        else:
            message = '===== NO OUTPUT ====='

        tqdm.write(Colored.blue(message), file=sys.stdout)

    def command_header(self, command: transports.Command) -> None:
        """Reports a single command execution.

        :Parameters:
            according to parent :py:meth:`BaseReporter.command_header`.

        """
        output_message = "----- OUTPUT of '{command}' -----".format(command=command.shortened())
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

    def __init__(
        self, target: transports.Target, commands: list[transports.Command], reporter: BaseReporter,
        progress_bars: transports.BaseExecutionProgress, success_threshold: float = 1.0, **kwargs: Any,
    ) -> None:
        """Event handler ClusterShell extension constructor.

        Arguments:
            target (cumin.transports.Target): a Target instance.
            commands (list): the list of Command objects that has to be executed on the nodes.
            reporter (cumin.transports.clustershell.BaseReporter): reporter used to output progress.
            progress_bars (cumin.transports.BaseExecutionProgress): the progress bars instance.
            success_threshold (float, optional): the success threshold, a :py:class:`float` between ``0`` and ``1``,
                to consider the execution successful.
            **kwargs (optional): additional keyword arguments that might be used by derived classes.

        """
        super().__init__()
        self.success_threshold = success_threshold
        self.logger = logging.getLogger('.'.join((self.__module__, self.__class__.__name__)))
        self.target = target
        self.lock = threading.Lock()  # Used to update instance variables coherently from within callbacks

        # Execution management variables
        self.commands = commands
        self.kwargs = kwargs  # Allow to store custom parameters from subclasses without changing the signature
        self.deduplicate_output = len(target.hosts) > 1
        self.global_timedout = False

        self.progress = progress_bars
        self.reporter = reporter
        self.run_report = ExecutionRun(commands=self.commands, hosts=self.target.hosts)
        # Move already all the nodes in the first_batch to the scheduled state, it means that ClusterShell was
        # already instructed to execute a command on those nodes
        for node_name in target.first_batch:
            self.run_report.hosts[node_name].state.update(HostState.SCHEDULED)

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
            self.run_report.status = transports.ExecutionStatus.TIMEDOUT
            # Considering timed out also the nodes that were pending the execution (for example when executing in
            # batches) and those that were already scheduled (for example when the # of nodes is greater than
            # ClusterShell fanout)
            pending_or_scheduled = sum(
                host.state.is_pending or host.state.is_scheduled or (host.state.is_success and not host.has_completed)
                for host in self.run_report.hosts.values())
            if pending_or_scheduled > 0:
                self.progress.update_failed(num_timeout + pending_or_scheduled)

        self.reporter.global_timeout_nodes(self.run_report.hosts)

    def ev_hup(self, worker, node, rc):
        """Command execution completed on a node.

        This callback is triggered by ClusterShell for each node when it completes the execution of a command.

        :Parameters:
            according to parent :py:meth:`ClusterShell.Event.EventHandler.ev_hup`.
        """
        self.logger.debug("node=%s, rc=%d, command='%s'", node, rc, worker.command)

    def ev_pickup(self, worker, node):
        """Command execution started on a node, remove the command from the node's queue.

        This callback is triggered by the `ClusterShell` library for each node when it starts executing a command.

        :Parameters:
            according to parent :py:meth:`ClusterShell.Event.EventHandler.ev_pickup`.
        """
        self.logger.debug("node=%s, command='%s'", node, worker.command)

        with self.lock:  # Avoid modifications of the same data from other callbacks triggered by ClusterShell
            host = self.run_report.hosts[node]

            command = host.commands[host.last_executed_command_index + 1]
            # Security check, it should never be triggered
            if command.command != worker.command:
                raise transports.WorkerError(
                    "ev_pickup: got unexpected command '{command}', expected '{expected}'".format(
                        command=command.command, expected=worker.command))

            host.state.update(HostState.RUNNING)  # Update the node's state to running
            host.last_executed_command_index += 1  # Move the pointer of the current command
            if self.run_report.last_executed_command_index < host.last_executed_command_index:
                self.run_report.last_executed_command_index = host.last_executed_command_index

        if not self.deduplicate_output:
            self.reporter.command_header(command)

    def ev_read(self, worker, node, sname, msg):
        """Worker has data to read from a specific node. Print it if running on a single host.

        This callback is triggered by ClusterShell for each node when output is available.

        :Parameters:
            according to parent :py:meth:`ClusterShell.Event.EventHandler.ev_read`.
        """
        host = self.run_report.hosts[node]
        self.run_report.commands_results[host.last_executed_command_index].outputs[sname].add(node, msg)
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

        self.logger.debug("command='%s', total_timedout=%d", worker.command, worker.task.num_timeout())

        with self.lock:  # Avoid modifications of the same data from other callbacks triggered by ClusterShell
            new_timedout = 0
            for name in worker.task.iter_keys_timeout():
                host = self.run_report.hosts[name]
                if host.state.is_timeout:
                    continue

                new_timedout += 1
                host.state.update(HostState.TIMEOUT)

            self.progress.update_failed(new_timedout)

        # Schedule a timer to run the current command on the next node or start the next command
        worker.task.timer(self.target.batch_sleep, worker.eh)

    def _success_nodes_report(self, current_command_index: int = -1) -> None:
        """Print how many nodes successfully executed all commands in a colored and tqdm-friendly way.

        Arguments:
            current_command_index (int, optional): the command index the success is referring to, if any.

        """
        if current_command_index == -1:  # called at the end of all executions
            command = None
            num = sum(host.state.is_success and host.has_completed for host in self.run_report.hosts.values())
        else:
            command = self.commands[current_command_index]
            num = sum(host.state.is_success and host.last_executed_command_index == current_command_index
                      for host in self.run_report.hosts.values())

        tot = self.run_report.total
        success_ratio = num / tot
        self.reporter.success_nodes(command, num, success_ratio, tot, self.success_threshold, self.run_report.hosts)

    @property
    def is_above_threshold(self) -> bool:
        """Whether the success threshold is still met.

        Returns:
            bool: :py:data:`True` if the success ratio is still above or equal the success threshold.

        """
        counter = self.run_report.get_counter()
        failed = counter[HostState.FAILED]
        timeout = counter[HostState.TIMEOUT]
        success_ratio = 1 - ((failed + timeout) / self.run_report.total)
        return success_ratio >= self.success_threshold


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

    def __init__(
        self, target: transports.Target, commands: list[transports.Command], reporter: BaseReporter,
        progress_bars: transports.BaseExecutionProgress, success_threshold: float = 1.0, **kwargs: Any,
    ) -> None:
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
        self.progress.init(self.run_report.total)

        # Schedule the next command, the first was already scheduled by ClusterShellWorker.execute()
        if not schedule:
            return

        with self.lock:  # Avoid modifications of the same data from other callbacks triggered by ClusterShell
            # Available nodes for the next command execution were already update back to the pending state
            remaining_nodes = [
                host.name for host in self.run_report.hosts.values() if host.state.is_pending]
            first_batch = remaining_nodes[:self.target.batch_size]
            first_batch_set = nodeset_fromlist(first_batch)
            for node_name in first_batch:
                self.run_report.hosts[node_name].state.update(HostState.SCHEDULED)

        command = self.commands[self.current_command_index]
        self.logger.debug(
            "command='%s', timeout=%s, first_batch=%s", command.command, command.timeout, first_batch_set)

        # Schedule the command for execution in ClusterShell
        Task.task_self().shell(command.command, nodes=first_batch_set, handler=self, timeout=command.timeout)

    def end_command(self) -> bool:
        """Command terminated, print the result and schedule the next command if criteria are met.

        Executed at the end of each command inside a lock.

        Returns:
            bool: :py:data:`True` if the next command should be scheduled, :py:data:`False` otherwise.

        """
        if self.deduplicate_output:
            self.reporter.command_output(self.run_report.get_command_outputs(self.current_command_index))
        else:
            self.reporter.command_completed()

        self.progress.close()

        self.reporter.failed_nodes(
            nodes=self.run_report.hosts, num_hosts=self.run_report.total,
            commands=self.commands, filter_command_index=self.current_command_index)
        self._success_nodes_report(current_command_index=self.current_command_index)

        success_ratio = self.run_report.get_counter()[HostState.SUCCESS] / self.run_report.total

        # Abort on failure
        if success_ratio < self.success_threshold:
            self.run_report.status = transports.ExecutionStatus.FAILED
            self.aborted = True  # Tells other timers that might trigger after that the abort is already in progress
            return False

        if success_ratio == 1:
            self.run_report.status = transports.ExecutionStatus.SUCCEEDED
        else:
            self.run_report.status = transports.ExecutionStatus.COMPLETED_WITH_FAILURES

        if self.current_command_index == (len(self.commands) - 1):
            self.logger.debug('This was the last command')
            return False

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
        super().ev_hup(worker, node, rc)

        with self.lock:  # Avoid modifications of the same data from other callbacks triggered by ClusterShell
            host = self.run_report.hosts[node]
            host.return_codes.append(rc)

            ok_codes = host.commands[host.last_executed_command_index].ok_codes
            if rc in ok_codes or not ok_codes:
                self.progress.update_success()
                new_state = HostState.SUCCESS
            else:
                self.progress.update_failed()
                new_state = HostState.FAILED

            host.state.update(new_state)

        # Schedule a timer to run the current command on the next node or start the next command
        worker.task.timer(self.target.batch_sleep, worker.eh)

    def ev_timer(self, timer: EngineTimer) -> None:  # noqa, mccabe: MC0001 too complex (15) FIXME
        """Schedule the current command on the next node or the next command on the first batch of nodes.

        This callback is triggered by `ClusterShell` when a scheduled `Task.timer()` goes off.

        :Parameters:
            according to parent :py:meth:`ClusterShell.Event.EventHandler.ev_timer`.
        """
        next_host = None
        if self.is_above_threshold:
            # Success ratio is still good, looking for the next node
            with self.lock:  # Avoid modifications of the same data from other callbacks triggered by ClusterShell
                next_host = self.run_report.next_host(HostState.PENDING)
                if next_host is not None:  # Found the next node where to execute the command
                    next_host.state.update(HostState.SCHEDULED)

        if next_host is not None:
            # Schedule the execution with ClusterShell of the current command to the next node found above
            next_command = next_host.commands[next_host.last_executed_command_index + 1]
            self.logger.debug(
                "next_node=%s, timeout=%s, command='%s'", next_host.name, next_command.command, next_command.timeout)
            Task.task_self().shell(
                next_command.command, handler=timer.eh, timeout=next_command.timeout, nodes=nodeset(next_host.name))
            return

        # No more nodes were left for the execution of the current command
        with self.lock:  # Avoid modifications of the same data from other callbacks triggered by ClusterShell
            try:
                command: Optional[str] = self.commands[self.current_command_index].command
            except IndexError:
                command = None  # Last command reached

            # Get a list of the nodes still in pending state
            pending = [host.name for host in self.run_report.hosts.values() if host.state.is_pending]
            # Nodes in running are still running the command and nodes in scheduled state will execute the command
            # anyway, they were already offloaded to ClusterShell
            counter = self.run_report.get_counter()
            accounted = (len(pending) + counter[HostState.FAILED] + counter[HostState.SUCCESS]
                         + counter[HostState.TIMEOUT])

            # Avoid race conditions
            if self.aborted or accounted != self.run_report.total or command is None or self.global_timedout:
                self.logger.debug("Skipped timer")
                return

            if pending:
                # This usually happens when executing in batches
                self.logger.warning("Command '%s' was not executed on: %s", command, nodeset_fromlist(pending))

            self.logger.info("Completed command '%s'", command)
            restart = self.end_command()
            self.current_command_index += 1  # Move the global pointer of the command in execution

            if restart:
                for host in self.run_report.hosts.values():
                    if host.state.is_success:
                        # Only nodes in pending state will be scheduled for the next command
                        host.state.update(HostState.PENDING)

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

    def __init__(
        self, target: transports.Target, commands: list[transports.Command], reporter: BaseReporter,
        progress_bars: transports.BaseExecutionProgress, success_threshold: float = 1.0, **kwargs: Any,
    ) -> None:
        """Define a custom ClusterShell event handler to execute commands asynchronously between nodes.

        :Parameters:
            according to parent :py:meth:`BaseEventHandler.__init__`.
        """
        super().__init__(target, commands, reporter, success_threshold=success_threshold,
                         progress_bars=progress_bars, **kwargs)

        self.progress.init(self.run_report.total)

    def ev_hup(self, worker, node, rc):
        """Command execution completed on a node.

        This callback is triggered by ClusterShell for each node when it completes the execution of a command.
        Enqueue the next command if the success criteria are met, track the failure otherwise. Update the progress
        bars accordingly.

        :Parameters:
            according to parent :py:meth:`ClusterShell.Event.EventHandler.ev_hup`.
        """
        super().ev_hup(worker, node, rc)

        schedule_next = False
        schedule_timer = False
        with self.lock:  # Avoid modifications of the same data from other callbacks triggered by ClusterShell
            host = self.run_report.hosts[node]
            host.return_codes.append(rc)

            ok_codes = host.commands[host.last_executed_command_index].ok_codes
            if rc in ok_codes or not ok_codes:
                if host.has_completed:
                    self.progress.update_success()
                    host.state.update(HostState.SUCCESS)
                    schedule_timer = True  # Continue the execution on other nodes if criteria are met
                else:
                    schedule_next = True  # Continue the execution in the current node with the next command
            else:
                self.progress.update_failed()
                host.state.update(HostState.FAILED)
                schedule_timer = True  # Continue the execution on other nodes if criteria are met

        if schedule_next:
            # Schedule the execution of the next command on this node with ClusterShell
            command = host.commands[host.last_executed_command_index + 1]
            worker.task.shell(
                command.command, nodes=nodeset(node), handler=worker.eh, timeout=command.timeout, stdin=False)
        elif schedule_timer:
            # Schedule a timer to allow to run all the commands in the next available node
            worker.task.timer(self.target.batch_sleep, worker.eh)

    def ev_timer(self, timer: EngineTimer) -> None:
        """Schedule the current command on the next node or the next command on the first batch of nodes.

        This callback is triggered by `ClusterShell` when a scheduled `Task.timer()` goes off.

        :Parameters:
            according to parent :py:meth:`ClusterShell.Event.EventHandler.ev_timer`.
        """
        next_host = None
        if self.is_above_threshold:
            # Success ratio is still good, looking for the next node
            with self.lock:  # Avoid modifications of the same data from other callbacks triggered by ClusterShell
                next_host = self.run_report.next_host(HostState.PENDING)
                if next_host is not None:  # Found the next node where to execute all the commands
                    next_host.state.update(HostState.SCHEDULED)

        if next_host is not None:
            # Schedule the execution of the first command to the next node with ClusterShell
            command = next_host.commands[0]
            self.logger.debug(
                "next_node=%s, timeout=%s, command='%s'", next_host.name, command.command, command.timeout)
            Task.task_self().shell(
                command.command, handler=timer.eh, timeout=command.timeout, nodes=nodeset(next_host.name))
        else:
            self.logger.debug('No more nodes left')

    def close(self, task: Task) -> None:
        """Concrete implementation of parent abstract method to print the nodes reports and close progress bars.

        :Parameters:
            according to parent :py:meth:`cumin.transports.BaseEventHandler.close`.
        """
        if self.deduplicate_output:
            for index in range(len(self.run_report.commands)):
                outputs = self.run_report.get_command_outputs(index)
                if outputs:
                    self.reporter.command_output(self.run_report.get_command_outputs(index))
        else:
            self.reporter.command_completed()

        self.progress.close()

        self.reporter.failed_nodes(
            nodes=self.run_report.hosts, num_hosts=self.run_report.total, commands=self.commands)
        self._success_nodes_report()

        counter = self.run_report.get_counter()
        success_ratio = counter[HostState.SUCCESS] / self.run_report.total

        if success_ratio == 1:
            self.run_report.status = transports.ExecutionStatus.SUCCEEDED
        elif success_ratio < self.success_threshold:
            self.run_report.status = transports.ExecutionStatus.FAILED
        else:
            self.run_report.status = transports.ExecutionStatus.COMPLETED_WITH_FAILURES


worker_class: Type[transports.BaseWorker] = ClusterShellWorker  # pylint: disable=invalid-name
"""Required by the transport auto-loader in :py:meth:`cumin.transport.Transport.new`."""

DEFAULT_HANDLERS: dict[str, Type[Event.EventHandler]] = {'sync': SyncEventHandler, 'async': AsyncEventHandler}
"""dict: mapping of available default event handlers for :py:class:`ClusterShellWorker`."""
