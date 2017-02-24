from collections import defaultdict

import ClusterShell
import colorama

from ClusterShell.Task import NodeSet, task_self
from tqdm import tqdm

from cumin.transports import BaseWorker


class ClusterShellWorker(BaseWorker):
    """ClusterShell worker, extends BaseWorker"""

    def __init__(self, config, logger=None):
        """ ClusterShell worker constructor

            Arguments: according to BaseQuery interface
        """
        super(ClusterShellWorker, self).__init__(config, logger)
        self.task = task_self()  # Initialize a ClusterShell task

        self.default_handlers = {'sync': SyncEventHandler, 'async': AsyncEventHandler}

        # Set any SSH option
        ssh_options = config.get('clustershell', {}).get('ssh_options', [])
        for option in ssh_options:
            self.task.set_info('ssh_options', option)

    def execute(self, hosts, commands, mode=None, handler=None, timeout=0, success_threshold=1):
        """Required by BaseWorker"""
        if len(commands) == 0:
            self.logger.warning('No commands provided')
            return

        if len(commands) > 1 and mode not in self.default_handlers.keys():
            raise RuntimeError("Unknown mode '{mode}' specified, expecting one of {modes}".format(
                mode=mode, modes=self.default_handlers.keys()))

        if len(commands) == 1 and mode is None:
            mode = 'sync'

        # Pick the default handler
        if handler is True:
            handler = self.default_handlers[mode]

        # Instantiate handler
        if handler is not None:
            handler = handler(hosts, commands, success_threshold=success_threshold)

        # Schedule only the first command, the following must be handled by the handler
        self.task.shell(commands[0], nodes=NodeSet.fromlist(hosts), handler=handler)

        try:
            self.task.run(timeout=timeout)
        except ClusterShell.Task.TimeoutError:
            pass  # Handling of timeouts are delegated to the handler
        finally:
            if handler is not None:
                handler.close(self.task)

    def get_results(self):
        """Required by BaseWorker"""
        for output, nodelist in self.task.iter_buffers():
            yield NodeSet.fromlist(nodelist), output


class BaseEventHandler(ClusterShell.Event.EventHandler):
    """ClusterShell event handler extension base class"""

    short_command_length = 35

    def __init__(self, nodes, commands, **kwargs):
        """ ClusterShell event handler extension constructor

            If inherited classes defines a self.pbar_ko tqdm progress bar, it will be updated on ev_error and
            ev_timeout events.

            Arguments:
            nodes    -- the list of nodes with which this worker was initiliazed
            commands -- the list of commands that has to be executed on the nodes
            **kwargs -- optional additional keyword arguments that might be used by classes that extend this base class
        """
        super(BaseEventHandler, self).__init__()
        self.nodes = nodes
        self.commands = commands
        self.kwargs = kwargs
        self.success_nodes = []
        self.failed_commands = defaultdict(list)

        # Initialize color and progress bar formats
        # TODO: decouple the output handling from the event handling
        colorama.init()
        self.bar_format = ('{desc} |{bar}| {percentage:3.0f}% ({n_fmt}/{total_fmt}) '
                           '[{elapsed}<{remaining}, {rate_fmt}]') + colorama.Style.RESET_ALL

    def close(self, task):
        """ Additional method called at the end of the execution, useful for reporting and final actions

            Arguments:
            task -- a ClusterShell Task instance
        """
        raise NotImplementedError

    def ev_error(self, worker):
        """ Update the current fail progress bar and print the error

            Arguments: according to EventHandler interface
        """
        self.failed_commands[worker.command].append(worker.current_node)
        if hasattr(self, 'pbar_ko'):
            self.pbar_ko.update()
        tqdm.write(worker.current_errmsg)

    def ev_timeout(self, worker):
        """ Update the current fail progress bar

            Arguments: according to EventHandler interface
        """
        if hasattr(self, 'pbar_ko'):
            self.pbar_ko.update(worker.num_timeout())

    def _print_report_line(self, num, tot, message, color=colorama.Fore.RED, nodes=None):
        """ Helper to print a tqdm-friendly colored status line with success/failure ratio and optional list of nodes

            Arguments:
            num     - the number of affecte nodes
            tot     - the total number of nodes
            message - the message to print
            color   - the colorama color to use for the line [optional, default: colorama.Fore.RED]
            nodes   - the list of nodes affected [optional, default: None]
        """
        if nodes is None:
            nodes = ''
            message_end = ''
        else:
            nodes = NodeSet.fromlist(nodes)
            message_end = ': '

        tqdm.write('{color}{perc:.1%} ({num}/{tot}) {message}{message_end}{nodes_color}{nodes}{reset}'.format(
            color=color, perc=(float(num) / tot), num=num, tot=tot, message=message, message_end=message_end,
            nodes_color=colorama.Fore.CYAN, nodes=nodes, reset=colorama.Style.RESET_ALL))

    def _get_short_command(self, command):
        """ Return a shortened representation of a command omitting the central part

            Arguments:
            command - the command to be shortened
        """
        sublen = (self.short_command_length - 3) // 2  # The -3 is for the ellipsis
        return (command[:sublen] + '...' + command[-sublen:]) if len(command) > self.short_command_length else command

    def _commands_output_report(self, buffer_iterator, command=None):
        """ Helper to print the commands output in a colored and tqdm-friendly way

            Arguments:
            buffer_iterator - any ClusterShell object that implements iter_buffers() like Task and Worker objects.
            command         - command the output is referring to [optional, default: None]
        """
        nodelist = None
        if command is not None:
            output_message = "----- OUTPUT of '{command}' -----".format(command=self._get_short_command(command))
        else:
            output_message = '----- OUTPUT -----'

        for output, nodelist in buffer_iterator.iter_buffers():
            tqdm.write(colorama.Fore.BLUE + '===== NODE GROUP =====' + colorama.Style.RESET_ALL)
            tqdm.write('{color}({num}) {nodes}{reset}'.format(
                color=colorama.Fore.CYAN, num=len(nodelist), nodes=NodeSet.fromlist(nodelist),
                reset=colorama.Style.RESET_ALL))
            tqdm.write(colorama.Fore.BLUE + output_message + colorama.Style.RESET_ALL)
            tqdm.write('{output}'.format(output=output))

        if nodelist is None:
            message = '===== NO OUTPUT ====='
        else:
            message = '================'

        tqdm.write(colorama.Fore.BLUE + message + colorama.Style.RESET_ALL)

    def _timeout_nodes_report(self, buffer_iterator):
        """ Helper to print the nodes that timed out in a colored and tqdm-friendly way

            Arguments:
            buffer_iterator - any ClusterShell object that implements iter_buffers() like Task and Worker objects.
        """
        timeout = buffer_iterator.num_timeout()
        if timeout == 0:
            return

        tot = len(self.nodes)
        self._print_report_line(timeout, tot, 'of nodes timed out', nodes=buffer_iterator.iter_keys_timeout())

    def _failed_commands_report(self, filter_command=None):
        """ Helper to print the nodes that failed to execute commands in a colored and tqdm-friendly way

            Arguments:
            filter_command - print only the nodes that failed to execute this specific command [optional, default: None]
        """
        tot = len(self.nodes)
        for command, nodes in self.failed_commands.iteritems():
            fail = len(nodes)
            if fail == 0:
                continue

            if filter_command is not None and command is not None and command != filter_command:
                continue

            message = "of nodes failed to execute command '{command}'".format(command=self._get_short_command(command))
            self._print_report_line(fail, tot, message, nodes=nodes)

    def _success_nodes_report(self):
        """Helper to print how many nodes succesfully executed all commands in a colored and tqdm-friendly way"""
        tot = len(self.nodes)
        succ = len(self.success_nodes)
        message = 'of nodes succesfully executed all commands'
        if succ == tot or len(self.success_nodes) == 0:
            nodes = None
        else:
            nodes = self.success_nodes

        if succ == 0:
            color = colorama.Fore.RED
        elif succ == tot:
            color = colorama.Fore.GREEN
        else:
            color = colorama.Fore.YELLOW

        self._print_report_line(succ, tot, message, color=color, nodes=nodes)


class SyncEventHandler(BaseEventHandler):
    """ Custom ClusterShell event handler class that execute commands synchronously

        The implemented logic is:
        - execute command_N on all nodes where command_N-1 was successful (all nodes at first iteration)
        - if success ratio of the execution of command_N < success threshold, then:
          - abort the execution
        - else:
          - re-start from the top with N=N+1

        The typical use case is to orchestrate some operation across a fleet, ensuring that each command is completed
        by enough hosts before proceeding with the next one.
    """

    def __init__(self, nodes, commands, **kwargs):
        """ Custom ClusterShell synchronous event handler constructor

            Arguments: according to BaseEventHandler interface
        """
        super(SyncEventHandler, self).__init__(nodes, commands, **kwargs)
        # Slicing the commands list to get a copy
        self.nodes_commands = commands[:]

    def ev_start(self, worker):
        """ Worker started, initialize progress bars and variables for this command execution

            Arguments: according to EventHandler interface
        """
        command = self.nodes_commands.pop(0)
        self.success_nodes = []
        if command != worker.command:
            raise RuntimeError('{} != {}'.format(command, worker.command))

        self.pbar_ok = tqdm(total=len(self.nodes), leave=True, unit='hosts', dynamic_ncols=True,
                            bar_format=colorama.Fore.GREEN + self.bar_format)
        self.pbar_ok.desc = 'PASS'
        self.pbar_ok.refresh()
        self.pbar_ko = tqdm(total=len(self.nodes), leave=True, unit='hosts', dynamic_ncols=True,
                            bar_format=colorama.Fore.RED + self.bar_format)
        self.pbar_ko.desc = 'FAIL'
        self.pbar_ko.refresh()

    def ev_hup(self, worker):
        """ Command execution completed

            Update the progress bars and keep track of nodes based on the success/failure of the command's execution

            Arguments: according to EventHandler interface
        """
        if worker.current_rc != 0:
            self.pbar_ko.update()
            self.failed_commands[worker.command].append(worker.current_node)
        else:
            self.pbar_ok.update()
            self.success_nodes.append(worker.current_node)

    def ev_close(self, worker):
        """ Worker terminated, print the output of the command execution and the summary report lines

            Arguments: according to EventHandler interface
        """
        self._commands_output_report(worker, command=worker.command)

        self.pbar_ok.close()
        self.pbar_ko.close()

        self._timeout_nodes_report(worker)
        self._failed_commands_report(filter_command=worker.command)

        success_threshold = self.kwargs.get('success_threshold', 1)
        tot = len(self.nodes)
        succ = len(self.success_nodes)
        success_ratio = float(succ) / tot

        if len(self.nodes_commands) == 0:
            return  # This was the last command

        # Schedule the next command
        if success_ratio >= success_threshold:
            worker.task.shell(self.nodes_commands[0], nodes=NodeSet.fromlist(self.success_nodes), handler=worker.eh)
            message = 'success ratio (>= {perc:.1%} threshold) for command: {command}'.format(
                perc=success_threshold, command=self._get_short_command(worker.command))

            if success_ratio == 1:
                color = colorama.Fore.GREEN
            else:
                color = colorama.Fore.YELLOW
        else:
            message = 'success ratio < success threshold ({perc:.1%}). Aborting.'.format(perc=success_threshold)
            color = colorama.Fore.RED

        self._print_report_line(succ, tot, message, color=color)

    def close(self, task):
        """ Print a final summary report line

            Arguments: according to BaseEventHandler interface
        """
        if len(self.commands) > 1 and len(self.nodes_commands) == 0:
            self._success_nodes_report()


class AsyncEventHandler(BaseEventHandler):
    """ Custom ClusterShell event handler class that execute commands asynchronously

        The implemented logic is to execute on all nodes, independently one to each other, command_N only if
        command_N-1 was succesful, aborting the execution on that node otherwise.

        The typical use case is to execute read-only commands to gather the status of a fleet without any special need
        of orchestration between the hosts.
    """

    def __init__(self, nodes, commands, **kwargs):
        """ Custom ClusterShell asynchronous event handler constructor

            Arguments: according to BaseEventHandler interface
        """
        super(AsyncEventHandler, self).__init__(nodes, commands, **kwargs)
        # Map commands to all nodes .Slicing the commands list to get a copy
        self.nodes_commands = {node: commands[:] for node in nodes}

        self.pbar_ok = tqdm(total=len(self.nodes), leave=True, unit='hosts', dynamic_ncols=True,
                            bar_format=colorama.Fore.GREEN + self.bar_format)
        self.pbar_ok.desc = 'PASS'
        self.pbar_ok.refresh()
        self.pbar_ko = tqdm(total=len(self.nodes), leave=True, unit='hosts', dynamic_ncols=True,
                            bar_format=colorama.Fore.RED + self.bar_format)
        self.pbar_ko.desc = 'FAIL'
        self.pbar_ko.refresh()

    def ev_pickup(self, worker):
        """ Command execution started, remove the command from the node's queue

            Arguments: according to EventHandler interface
        """
        command = self.nodes_commands[worker.current_node].pop(0)
        if command != worker.command:
            raise RuntimeError('{} != {}'.format(command, worker.command))

    def ev_hup(self, worker):
        """ Command execution completed

            Enqueue the next command if the previous was successful, track the failure otherwise
            Update the progress bars accordingly

            Arguments: according to EventHandler interface
        """
        if worker.current_rc != 0:
            self.pbar_ko.update()
            self.failed_commands[worker.command].append(worker.current_node)
            return

        try:
            worker.task.shell(self.nodes_commands[worker.current_node][0],
                              nodes=worker.current_node, handler=worker.eh)
        except IndexError:
            # All commands completed
            self.pbar_ok.update()
            self.success_nodes.append(worker.current_node)

    def close(self, task):
        """ Properly close all progress bars and print results

            Arguments: according to BaseEventHandler interface
        """
        self._commands_output_report(task)

        self.pbar_ok.close()
        self.pbar_ko.close()

        self._timeout_nodes_report(task)
        self._failed_commands_report()
        if len(self.commands) > 1:
            self._success_nodes_report()


worker_class = ClusterShellWorker  # Required by the auto-loader in the cumin.transport.Transport factory
