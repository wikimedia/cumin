"""Transport ClusterShell: worker and event handlers."""
import logging
import sys
import threading

from collections import Counter, defaultdict

import colorama

from ClusterShell import Event, NodeSet, Task
from tqdm import tqdm

from cumin.transports import BaseWorker, raise_error, State


class ClusterShellWorker(BaseWorker):
    """It provides a Cumin worker for SSH using the ClusterShell library."""

    def __init__(self, config, logger=None):
        """Worker ClusterShell constructor.

        Arguments: according to BaseQuery interface
        """
        super(ClusterShellWorker, self).__init__(config, logger)
        self.task = Task.task_self()  # Initialize a ClusterShell task
        self._handler_instance = None

        # Set any ClusterShell task options
        for key, value in config.get('clustershell', {}).items():
            if isinstance(value, list):
                self.task.set_info(key, ' '.join(value))
            else:
                self.task.set_info(key, value)

    def execute(self):
        """Required by BaseWorker."""
        if not self.commands:
            self.logger.warning('No commands provided')
            return

        if self.handler is None:
            raise RuntimeError('An EventHandler is mandatory.')

        # Schedule only the first command for the first batch, the following ones must be handled by the EventHandler
        first_batch = self.hosts[:self.batch_size]

        # Instantiate handler
        self._handler_instance = self.handler(  # pylint: disable=not-callable
            self.hosts, self.commands, success_threshold=self.success_threshold, batch_size=self.batch_size,
            batch_sleep=self.batch_sleep, logger=self.logger, first_batch=first_batch)

        self.logger.info("Executing commands {commands} on '{num}' hosts: {hosts}".format(
            commands=self.commands, num=len(self.hosts), hosts=self.hosts))
        self.task.shell(self.commands[0].command, nodes=first_batch, handler=self._handler_instance,
                        timeout=self.commands[0].timeout)

        return_value = 0
        try:
            self.task.run(timeout=self.timeout)
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
        """Required by BaseWorker."""
        for output, nodelist in self.task.iter_buffers():
            yield NodeSet.NodeSet.fromlist(nodelist), output

    @property
    def handler(self):
        """Getter for the handler property."""
        return self._handler

    @handler.setter
    def handler(self, value):
        """Required by BaseTask.

        The available default handlers are defined in DEFAULT_HANDLERS.
        """
        if isinstance(value, type) and issubclass(value, BaseEventHandler):
            self._handler = value
        elif value in DEFAULT_HANDLERS.keys():
            self._handler = DEFAULT_HANDLERS[value]
        else:
            raise_error(
                'handler',
                'must be one of ({default}, a class object derived from BaseEventHandler)'.format(
                    default=', '.join(DEFAULT_HANDLERS.keys())),
                value)


class Node(object):
    """Node class to represent each target node."""

    def __init__(self, name, commands):
        """Node class constructor with default values.

        Arguments:
        name     -- the hostname of the node.
        commands -- a list of Command objects to be executed on the node.
        """
        self.name = name
        self.commands = commands
        self.state = State()  # Initialize the state machine for this node.
        self.running_command_index = -1  # Pointer to the current running command in self.commands


class BaseEventHandler(Event.EventHandler):
    """ClusterShell event handler extension base class.

    Inherit from ClusterShell's EventHandler class and define a base EventHandler class to be used in Cumin.
    It can be subclassed to generate custom EventHandler classes while taking advantage of some common
    functionalities.
    """

    short_command_length = 35  # For logging and printing the commands are shortened to reach at most this length

    def __init__(self, nodes, commands, **kwargs):
        """Event handler ClusterShell extension constructor.

        If subclasses defines a self.pbar_ko tqdm progress bar, it will be updated on timeout.

        Arguments:
        nodes    -- the ClusterShell's NodeSet with which this worker was initiliazed.
        commands -- the list of Command objects that has to be executed on the nodes.
        **kwargs -- optional additional keyword arguments that might be used by classes that extend this base class.
        """
        super(BaseEventHandler, self).__init__()
        self.logger = kwargs.get('logger', None) or logging.getLogger(__name__)
        self.lock = threading.Lock()  # Used to update instance variables coherently from within callbacks

        # Execution management variables
        self.return_value = None
        self.commands = commands
        self.kwargs = kwargs  # Allow to store custom parameters from subclasses without changing the signature
        self.counters = Counter()
        self.counters['total'] = len(nodes)
        self.deduplicate_output = self.counters['total'] > 1
        self.global_timedout = False
        # Instantiate all the node instances, slicing the commands list to get a copy
        self.nodes = {node: Node(node, commands[:]) for node in nodes}
        # Move already all the nodes in the first_batch to the scheduled state, it means that ClusterShell was
        # already instructed to execute a command on those nodes
        for node_name in kwargs.get('first_batch', []):
            self.nodes[node_name].state.update(State.scheduled)

        # Initialize color and progress bar formats
        # TODO: decouple the output handling from the event handling
        self.pbar_ok = None
        self.pbar_ko = None
        colorama.init()
        self.bar_format = ('{desc} |{bar}| {percentage:3.0f}% ({n_fmt}/{total_fmt}) '
                           '[{elapsed}<{remaining}, {rate_fmt}]') + colorama.Style.RESET_ALL

    def close(self, task):
        """Additional method called at the end of the whole execution, useful for reporting and final actions.

        Arguments:
        task -- a ClusterShell Task instance
        """
        raise NotImplementedError

    def on_timeout(self, task):
        """Callback called by the ClusterShellWorker when a Task.TimeoutError is raised.

        The whole execution timed out, update the state of the nodes and the timeout counter accordingly.

        Arguments:
        task -- a ClusterShell Task instance
        """
        num_timeout = task.num_timeout()
        self.logger.error('global timeout was triggered while {num} nodes were executing a command'.format(
            num=num_timeout))

        self.lock.acquire()  # Avoid modifications of the same data from other callbacks triggered by ClusterShell
        try:
            self.global_timedout = True
            # Considering timed out also the nodes that were pending the execution (for example when executing in
            # batches) and those that were already scheduled (for example when the # of nodes is greater than
            # ClusterShell fanout)
            pending_or_scheduled = sum(
                (node.state.is_pending or node.state.is_scheduled or
                 (node.state.is_success and node.running_command_index < (len(node.commands) - 1))
                 ) for node in self.nodes.itervalues())
            if self.pbar_ko is not None:
                self.pbar_ko.update(num_timeout + pending_or_scheduled)
        finally:
            self.lock.release()

        self._global_timeout_nodes_report()

    def ev_pickup(self, worker):
        """Command execution started on a node, remove the command from the node's queue.

        This callback is triggered by ClusterShell for each node when it starts executing a command.

        Arguments: according to EventHandler interface
        """
        self.logger.debug("node={node}, command='{command}'".format(
            node=worker.current_node, command=worker.command))

        self.lock.acquire()  # Avoid modifications of the same data from other callbacks triggered by ClusterShell
        try:
            node = self.nodes[worker.current_node]
            node.state.update(State.running)  # Update the node's state to running

            command = node.commands[node.running_command_index + 1].command
            # Security check, it should never be triggered
            if command != worker.command:
                raise RuntimeError("ev_pickup: got unexpected command '{command}', expected '{expected}'".format(
                    command=command, expected=worker.command))
            node.running_command_index += 1  # Move the pointer of the current command
        finally:
            self.lock.release()

        if not self.deduplicate_output:
            output_message = "----- OUTPUT of '{command}' -----".format(command=self._get_short_command(worker.command))
            tqdm.write(colorama.Fore.BLUE + output_message + colorama.Style.RESET_ALL, file=sys.stdout)

    def ev_read(self, worker):
        """Worker has data to read from a specific node. Print it if running on a single host.

        This callback is triggered by ClusterShell for each node when output is available.

        Arguments: according to EventHandler interface
        """
        if self.deduplicate_output:
            return

        tqdm.write(worker.current_msg)

    def ev_timeout(self, worker):
        """Worker has timed out.

        This callback is triggered by ClusterShell when the execution has timed out.

        Arguments: according to EventHandler interface
        """
        delta_timeout = worker.task.num_timeout() - self.counters['timeout']
        self.logger.debug("command='{command}', delta_timeout={num}".format(
            command=worker.command, num=delta_timeout))

        self.lock.acquire()  # Avoid modifications of the same data from other callbacks triggered by ClusterShell
        try:
            self.pbar_ko.update(delta_timeout)
            self.counters['timeout'] = worker.task.num_timeout()
            for node in worker.task.iter_keys_timeout():
                if not self.nodes[node].state.is_timeout:
                    self.nodes[node].state.update(State.timeout)
        finally:
            self.lock.release()

        # Schedule a timer to run the current command on the next node or start the next command
        worker.task.timer(self.kwargs.get('batch_sleep', 0.0), worker.eh)

    def _get_log_message(self, num, message, nodes=None):
        """Helper to get a pre-formatted message suitable for logging or printing.

        Returns a tuple of two strings: a logging message, the affected nodes in NodeSet format

        Arguments:
        num     - the number of affecte nodes
        message - the message to print
        nodes   - the list of nodes affected [optional, default: None]
        """
        if nodes is None:
            nodes_string = ''
            message_end = ''
        else:
            nodes_string = NodeSet.NodeSet.fromlist(nodes)
            message_end = ': '

        tot = self.counters['total']
        log_message = '{perc:.1%} ({num}/{tot}) {message}{message_end}'.format(
            perc=(float(num) / tot), num=num, tot=tot, message=message, message_end=message_end)

        return (log_message, str(nodes_string))

    def _print_report_line(self, message, color=colorama.Fore.RED, nodes_string=''):  # pylint: disable=no-self-use
        """Helper to print a tqdm-friendly colored status line with success/failure ratio and optional list of nodes.

        Arguments:
        message      -- the message to print
        color        -- the message color [optional, default: colorama.Fore.RED]
        nodes_string -- the string representation of the affected nodes [optional, default: '']
        """
        tqdm.write('{color}{message}{nodes_color}{nodes_string}{reset}'.format(
            color=color, message=message, nodes_color=colorama.Fore.CYAN,
            nodes_string=nodes_string, reset=colorama.Style.RESET_ALL), file=sys.stderr)

    def _get_short_command(self, command):
        """Return a shortened representation of a command omitting the central part.

        Arguments:
        command - the command to be shortened
        """
        sublen = (self.short_command_length - 3) // 2  # The -3 is for the ellipsis
        return (command[:sublen] + '...' + command[-sublen:]) if len(command) > self.short_command_length else command

    def _commands_output_report(self, buffer_iterator, command=None):
        """Helper to print the commands output in a colored and tqdm-friendly way.

        Arguments:
        buffer_iterator - any ClusterShell object that implements iter_buffers() like Task and Worker objects.
        command         - command the output is referring to [optional, default: None]
        """
        if not self.deduplicate_output:
            tqdm.write(colorama.Fore.BLUE + '================' + colorama.Style.RESET_ALL, file=sys.stdout)
            return

        nodelist = None
        if command is not None:
            output_message = "----- OUTPUT of '{command}' -----".format(command=self._get_short_command(command))
        else:
            output_message = '----- OUTPUT -----'

        for output, nodelist in buffer_iterator.iter_buffers():
            tqdm.write(colorama.Fore.BLUE + '===== NODE GROUP =====' + colorama.Style.RESET_ALL, file=sys.stdout)
            tqdm.write('{color}({num}) {nodes}{reset}'.format(
                color=colorama.Fore.CYAN, num=len(nodelist), nodes=NodeSet.NodeSet.fromlist(nodelist),
                reset=colorama.Style.RESET_ALL), file=sys.stdout)
            tqdm.write(colorama.Fore.BLUE + output_message + colorama.Style.RESET_ALL, file=sys.stdout)
            tqdm.write('{output}'.format(output=output), file=sys.stdout)

        if nodelist is None:
            message = '===== NO OUTPUT ====='
        else:
            message = '================'

        tqdm.write(colorama.Fore.BLUE + message + colorama.Style.RESET_ALL, file=sys.stdout)

    def _global_timeout_nodes_report(self):
        """Helper to print the nodes that were caught by the global timeout in a colored and tqdm-friendly way."""
        if not self.global_timedout:
            return

        timeout = [node.name for node in self.nodes.itervalues() if node.state.is_timeout]
        timeout_desc = 'of nodes were executing a command when the global timeout occurred'
        timeout_message, timeout_nodes = self._get_log_message(len(timeout), timeout_desc, nodes=timeout)
        self.logger.error('{message}{nodes}'.format(message=timeout_message, nodes=timeout_nodes))
        self._print_report_line(timeout_message, nodes_string=timeout_nodes)

        not_run = [node.name for node in self.nodes.itervalues() if node.state.is_pending or node.state.is_scheduled]
        not_run_desc = 'of nodes were pending execution when the global timeout occurred'
        not_run_message, not_run_nodes = self._get_log_message(len(not_run), not_run_desc, nodes=not_run)
        self.logger.error('{message}{nodes}'.format(message=not_run_message, nodes=not_run_nodes))
        self._print_report_line(not_run_message, nodes_string=not_run_nodes)

    def _failed_commands_report(self, filter_command_index=-1):
        """Helper to print the nodes that failed to execute commands in a colored and tqdm-friendly way.

        Arguments:
        filter_command - print only the nodes that failed to execute this specific command [optional, default: None]
        """
        for state in (State.failed, State.timeout):
            failed_commands = defaultdict(list)
            for node in [node for node in self.nodes.itervalues() if node.state == state]:
                failed_commands[node.running_command_index].append(node.name)

            for index, nodes in failed_commands.iteritems():
                command = self.commands[index].command

                if filter_command_index >= 0 and command is not None and index != filter_command_index:
                    continue

                message = "of nodes {state} to execute command '{command}'".format(
                    state=State.states_representation[state], command=self._get_short_command(command))
                log_message, nodes_string = self._get_log_message(len(nodes), message, nodes=nodes)
                self.logger.error('{message}{nodes}'.format(message=log_message, nodes=nodes_string))
                self._print_report_line(log_message, nodes_string=nodes_string)

    def _success_nodes_report(self, command=None):
        """Helper to print how many nodes succesfully executed all commands in a colored and tqdm-friendly way."""
        if self.global_timedout and command is None:
            num = sum(1 for node in self.nodes.itervalues() if node.state.is_success and
                      node.running_command_index == (len(self.commands) - 1))
        else:
            num = self.counters['success']

        tot = self.counters['total']
        success_threshold = self.kwargs.get('success_threshold', 1)
        success_ratio = float(num) / tot

        if success_ratio < success_threshold:
            comp = '<'
            post = '. Aborting.'
        else:
            comp = '>='
            post = '.'

        message_string = ' of nodes successfully executed all commands'
        if command is not None:
            message_string = " for command: '{command}'".format(command=self._get_short_command(command))

        nodes = None
        if num not in (0, tot):
            nodes = [node.name for node in self.nodes.itervalues() if node.state.is_success]

        message = "success ratio ({comp} {perc:.1%} threshold){message_string}{post}".format(
            comp=comp, perc=success_threshold, message_string=message_string, post=post)
        log_message, nodes_string = self._get_log_message(num, message, nodes=nodes)
        final_message = '{message}{nodes}'.format(message=log_message, nodes=nodes_string)

        if num == tot:
            color = colorama.Fore.GREEN
            self.logger.info(final_message)
        elif success_ratio >= success_threshold:
            color = colorama.Fore.YELLOW
            self.logger.warning(final_message)
        else:
            color = colorama.Fore.RED
            self.logger.error(final_message)

        self._print_report_line(log_message, color=color, nodes_string=nodes_string)


class SyncEventHandler(BaseEventHandler):
    """Custom ClusterShell event handler class that execute commands synchronously.

    The implemented logic is:
    - execute command #N on all nodes where command #N-1 was successful according to batch_size
    - the success ratio is checked at each command completion on every node, and will abort if not met, however
      nodes already scheduled for execution with ClusterShell will execute the command anyway. The use of the
      batch_size allow to control this aspect.
    - if the execution of command #N is completed and the success ratio is greater than the success threshold,
      re-start from the top with N=N+1

    The typical use case is to orchestrate some operation across a fleet, ensuring that each command is completed by
    enough nodes before proceeding with the next one.
    """

    def __init__(self, nodes, commands, **kwargs):
        """Custom ClusterShell synchronous event handler constructor.

        Arguments: according to BaseEventHandler interface
        """
        super(SyncEventHandler, self).__init__(nodes, commands, **kwargs)
        self.current_command_index = 0  # Global pointer for the current command in execution across all nodes
        self.start_command()
        self.aborted = False

    def start_command(self, schedule=False):
        """Initialize progress bars and variables for this command execution.

        Executed at the start of each command.

        Arguments:
        schedule -- boolean to decide if the next command should be sent to ClusterShell for execution or not.
                    [optional, default: False]
        """
        self.counters['success'] = 0

        self.pbar_ok = tqdm(desc='PASS', total=self.counters['total'], leave=True, unit='hosts', dynamic_ncols=True,
                            bar_format=colorama.Fore.GREEN + self.bar_format, file=sys.stderr)
        self.pbar_ok.refresh()
        self.pbar_ko = tqdm(desc='FAIL', total=self.counters['total'], leave=True, unit='hosts', dynamic_ncols=True,
                            bar_format=colorama.Fore.RED + self.bar_format, file=sys.stderr)
        self.pbar_ko.refresh()

        # Schedule the next command, the first was already scheduled by ClusterShellWorker.execute()
        if schedule:
            batch_size = self.kwargs.get('batch_size', self.counters['total'])

            self.lock.acquire()  # Avoid modifications of the same data from other callbacks triggered by ClusterShell
            try:
                # Available nodes for the next command execution were already update back to the pending state
                remaining_nodes = [node.name for node in self.nodes.itervalues() if node.state.is_pending]
                first_batch = remaining_nodes[:batch_size]
                first_batch_set = NodeSet.NodeSet.fromlist(first_batch)
                for node_name in first_batch:
                    self.nodes[node_name].state.update(State.scheduled)
            finally:
                self.lock.release()

            command = self.commands[self.current_command_index]
            self.logger.debug("command='{command}', timeout={timeout}, first_batch={first_batch}".format(
                command=command.command, timeout=command.timeout, first_batch=first_batch_set))

            # Schedule the command for execution in ClusterShell
            Task.task_self().flush_buffers()
            Task.task_self().shell(command.command, nodes=first_batch_set, handler=self, timeout=command.timeout)

    def end_command(self):
        """Command terminated, print the result and schedule the next command if criteria are met.

        Executed at the end of each command inside a lock.
        """
        self._commands_output_report(Task.task_self(), command=self.commands[self.current_command_index].command)

        self.pbar_ok.close()
        self.pbar_ko.close()

        self._failed_commands_report(filter_command_index=self.current_command_index)
        self._success_nodes_report(command=self.commands[self.current_command_index].command)

        success_threshold = self.kwargs.get('success_threshold', 1)
        success_ratio = float(self.counters['success']) / self.counters['total']

        # Abort on failure
        if success_ratio < success_threshold:
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

    def on_timeout(self, task):
        """Callback called by the ClusterShellWorker when a Task.TimeoutError is raised.

        Arguments: according to BaseEventHandler interface
        """
        super(SyncEventHandler, self).on_timeout(task)
        self.end_command()

    def ev_hup(self, worker):
        """Command execution completed.

        This callback is triggered by ClusterShell for each node when it completes the execution of a command.

        Update the progress bars and keep track of nodes based on the success/failure of the command's execution.
        Schedule a timer for further decisions.

        Arguments: according to EventHandler interface
        """
        self.logger.debug("node={node}, rc={rc}, command='{command}'".format(
            node=worker.current_node, rc=worker.current_rc, command=worker.command))

        self.lock.acquire()  # Avoid modifications of the same data from other callbacks triggered by ClusterShell
        try:
            node = self.nodes[worker.current_node]

            if worker.current_rc in node.commands[node.running_command_index].ok_codes:
                self.pbar_ok.update()
                self.counters['success'] += 1
                new_state = State.success
            else:
                self.pbar_ko.update()
                self.counters['failed'] += 1
                new_state = State.failed

            node.state.update(new_state)
        finally:
            self.lock.release()

        # Schedule a timer to run the current command on the next node or start the next command
        worker.task.timer(self.kwargs.get('batch_sleep', 0.0), worker.eh)

    def ev_timer(self, timer):
        """Schedule the current command on the next node or the next command on the first batch of nodes.

        This callback is triggered by ClusterShell when a scheduled Task.timer() goes off.

        Arguments: according to EventHandler interface
        """
        success_threshold = self.kwargs.get('success_threshold', 1)
        success_ratio = 1 - (float(self.counters['failed'] + self.counters['timeout']) / self.counters['total'])

        node = None
        if success_ratio >= success_threshold:
            # Success ratio is still good, looking for the next node
            self.lock.acquire()  # Avoid modifications of the same data from other callbacks triggered by ClusterShell
            try:
                for new_node in self.nodes.itervalues():
                    if new_node.state.is_pending:
                        # Found the next node where to execute the command
                        node = new_node
                        node.state.update(State.scheduled)
                        break
            finally:
                self.lock.release()

        if node is not None:
            # Schedule the execution with ClusterShell of the current command to the next node found above
            command = self.nodes[node.name].commands[self.nodes[node.name].running_command_index + 1]
            self.logger.debug("next_node={node}, timeout={timeout}, command='{command}'".format(
                node=node.name, command=command.command, timeout=command.timeout))
            Task.task_self().shell(
                command.command, nodes=NodeSet.NodeSet(node.name), handler=timer.eh, timeout=command.timeout)
            return

        # No more nodes were left for the execution of the current command
        self.lock.acquire()  # Avoid modifications of the same data from other callbacks triggered by ClusterShell
        try:
            try:
                command = self.commands[self.current_command_index].command
            except IndexError:
                command = None  # Last command reached

            # Get a list of the nodes still in pending state
            pending = [pending_node.name for pending_node in self.nodes.itervalues() if pending_node.state.is_pending]
            # Nodes in running are still running the command and nodes in scheduled state will execute the command
            # anyway, they were already offloaded to ClusterShell
            accounted = len(pending) + self.counters['failed'] + self.counters['success'] + self.counters['timeout']

            # Avoid race conditions
            if self.aborted or accounted != self.counters['total'] or command is None or self.global_timedout:
                self.logger.debug("skipped timer")
                return

            if pending:
                # This usually happens when executing in batches
                self.logger.warning("command '{command}' was not executed on: {nodes}".format(
                    command=command, nodes=NodeSet.NodeSet.fromlist(pending)))

            self.logger.info("completed command '{command}'".format(command=command))
            restart = self.end_command()
            self.current_command_index += 1  # Move the global pointer of the command in execution

            if restart:
                for node in self.nodes.itervalues():
                    if node.state.is_success:
                        # Only nodes in pending state will be scheduled for the next command
                        node.state.update(State.pending)
        finally:
            self.lock.release()

        if restart:
            self.start_command(schedule=True)

    def close(self, task):
        """Print a final summary report line.

        Arguments: according to BaseEventHandler interface
        """
        self._success_nodes_report()


class AsyncEventHandler(BaseEventHandler):
    """Custom ClusterShell event handler class that execute commands asynchronously.

    The implemented logic is:
    - execute on all nodes independently every command in a sequence, aborting the execution on that node if any
      command fails.
    - The success ratio is checked at each node completion (either because it completed all commands or aborted
      earlier), however nodes already scheduled for execution with ClusterShell will execute the commands anyway. The
      use of the batch_size allows to control this aspect.
    - if the success ratio is met, schedule the execution of all commands to the next node.

    The typical use case is to execute read-only commands to gather the status of a fleet without any special need of
    orchestration between the nodes.
    """

    def __init__(self, nodes, commands, **kwargs):
        """Custom ClusterShell asynchronous event handler constructor.

        Arguments: according to BaseEventHandler interface
        """
        super(AsyncEventHandler, self).__init__(nodes, commands, **kwargs)

        self.pbar_ok = tqdm(desc='PASS', total=self.counters['total'], leave=True, unit='hosts', dynamic_ncols=True,
                            bar_format=colorama.Fore.GREEN + self.bar_format, file=sys.stderr)
        self.pbar_ok.refresh()
        self.pbar_ko = tqdm(desc='FAIL', total=self.counters['total'], leave=True, unit='hosts', dynamic_ncols=True,
                            bar_format=colorama.Fore.RED + self.bar_format, file=sys.stderr)
        self.pbar_ko.refresh()

    def ev_hup(self, worker):
        """Command execution completed on a node.

        This callback is triggered by ClusterShell for each node when it completes the execution of a command.

        Enqueue the next command if the success criteria are met, track the failure otherwise
        Update the progress bars accordingly

        Arguments: according to EventHandler interface
        """
        self.logger.debug("node={node}, rc={rc}, command='{command}'".format(
            node=worker.current_node, rc=worker.current_rc, command=worker.command))

        schedule_next = False
        schedule_timer = False
        self.lock.acquire()  # Avoid modifications of the same data from other callbacks triggered by ClusterShell
        try:
            node = self.nodes[worker.current_node]

            if worker.current_rc in node.commands[node.running_command_index].ok_codes:
                if node.running_command_index == (len(node.commands) - 1):
                    self.pbar_ok.update()
                    self.counters['success'] += 1
                    node.state.update(State.success)
                    schedule_timer = True  # Continue the execution on other nodes if criteria are met
                else:
                    schedule_next = True  # Continue the execution in the current node with the next command
            else:
                self.pbar_ko.update()
                self.counters['failed'] += 1
                node.state.update(State.failed)
                schedule_timer = True  # Continue the execution on other nodes if criteria are met
        finally:
            self.lock.release()

        if schedule_next:
            # Schedule the execution of the next command on this node with ClusterShell
            command = node.commands[node.running_command_index + 1]
            worker.task.shell(command.command, nodes=NodeSet.NodeSet(worker.current_node), handler=worker.eh,
                              timeout=command.timeout)
        elif schedule_timer:
            # Schedule a timer to allow to run all the commands in the next available node
            worker.task.timer(self.kwargs.get('batch_sleep', 0.0), worker.eh)

    def ev_timer(self, timer):
        """Schedule the current command on the next node or the next command on the first batch of nodes.

        This callback is triggered by ClusterShell when a scheduled Task.timer() goes off.

        Arguments: according to EventHandler interface
        """
        success_threshold = self.kwargs.get('success_threshold', 1)
        success_ratio = 1 - (float(self.counters['failed'] + self.counters['timeout']) / self.counters['total'])

        node = None
        if success_ratio >= success_threshold:
            # Success ratio is still good, looking for the next node
            self.lock.acquire()  # Avoid modifications of the same data from other callbacks triggered by ClusterShell
            try:
                for new_node in self.nodes.itervalues():
                    if new_node.state.is_pending:
                        # Found the next node where to execute all the commands
                        node = new_node
                        node.state.update(State.scheduled)
                        break
            finally:
                self.lock.release()

        if node is not None:
            # Schedule the exeuction of the first command to the next node with ClusterShell
            command = node.commands[0]
            self.logger.debug("next_node={node}, timeout={timeout}, command='{command}'".format(
                node=node.name, command=command.command, timeout=command.timeout))
            Task.task_self().shell(
                command.command, nodes=NodeSet.NodeSet(node.name), handler=timer.eh, timeout=command.timeout)
        else:
            self.logger.debug('No more nodes left')

    def close(self, task):
        """Properly close all progress bars and print results.

        Arguments: according to BaseEventHandler interface
        """
        self._commands_output_report(task)

        self.pbar_ok.close()
        self.pbar_ko.close()

        self._failed_commands_report()
        self._success_nodes_report()

        num = self.counters['success']
        tot = self.counters['total']
        success_threshold = self.kwargs.get('success_threshold', 1)
        success_ratio = float(num) / tot

        if success_ratio == 1:
            self.return_value = 0
        elif success_ratio < success_threshold:
            self.return_value = 2
        else:
            self.return_value = 1


# Required by the auto-loader in the cumin.transport.Transport factory
worker_class = ClusterShellWorker  # pylint: disable=invalid-name
DEFAULT_HANDLERS = {'sync': SyncEventHandler, 'async': AsyncEventHandler}  # Available default EventHandler classes
