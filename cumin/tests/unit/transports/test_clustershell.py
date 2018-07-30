"""ClusterShell transport tests."""
# pylint: disable=invalid-name,no-member,protected-access,attribute-defined-outside-init
from unittest import mock

import pytest

from cumin import CuminError, nodeset
from cumin.transports import BaseWorker, Command, clustershell, State, Target, WorkerError


def test_node_class_instantiation():
    """Default values should be set when a Node instance is created."""
    node = clustershell.Node('name', [Command('command1'), Command('command2')])
    assert node.running_command_index == -1
    assert isinstance(node.state, State)


@mock.patch('cumin.transports.clustershell.Task.task_self')
def test_worker_class(task_self):
    """An instance of worker_class should be an instance of BaseWorker."""
    worker = clustershell.worker_class({}, Target(nodeset('node1')))
    assert isinstance(worker, BaseWorker)
    task_self.assert_called_once_with()


class TestClusterShellWorker(object):
    """ClusterShell backend worker test class."""

    @mock.patch('cumin.transports.clustershell.Task.task_self')
    def setup_method(self, _, task_self):  # pylint: disable=arguments-differ
        """Initialize default properties and instances"""
        self.config = {
            'clustershell': {
                'ssh_options': ['-o StrictHostKeyChecking=no', '-o BatchMode=yes'],
                'fanout': 3}}

        self.target = Target(nodeset('node[1-2]'))
        self.worker = clustershell.worker_class(self.config, self.target)
        self.commands = [Command('command1'), Command('command2', ok_codes=[0, 100], timeout=5)]
        self.task_self = task_self
        # Mock default handlers
        clustershell.DEFAULT_HANDLERS = {
            'sync': mock.MagicMock(spec_set=clustershell.SyncEventHandler),
            'async': mock.MagicMock(spec_set=clustershell.AsyncEventHandler)}

        # Initialize the worker
        self.worker.commands = self.commands

    @mock.patch('cumin.transports.clustershell.Task.task_self')
    def test_instantiation(self, task_self):
        """An instance of ClusterShellWorker should be an instance of BaseWorker and initialize ClusterShell."""
        worker = clustershell.ClusterShellWorker(self.config, self.target)
        assert isinstance(worker, BaseWorker)
        task_self.assert_called_once_with()
        worker.task.set_info.assert_has_calls(
            [mock.call('fanout', 3),
             mock.call('ssh_options', '-o StrictHostKeyChecking=no -o BatchMode=yes')], any_order=True)

    def test_execute_default_sync_handler(self):
        """Calling execute() in sync mode without event handler should use the default sync event handler."""
        self.worker.handler = 'sync'
        self.worker.execute()
        args, kwargs = self.worker.task.shell.call_args
        assert args == ('command1',)
        assert kwargs['nodes'] == self.target.first_batch
        assert kwargs['handler'] == self.worker._handler_instance
        assert clustershell.DEFAULT_HANDLERS['sync'].called

    def test_execute_default_async_handler(self):
        """Calling execute() in async mode without event handler should use the default async event handler."""
        self.worker.handler = 'async'
        self.worker.execute()
        args, kwargs = self.worker.task.shell.call_args
        assert args == ('command1',)
        assert kwargs['nodes'] == self.target.first_batch
        assert kwargs['handler'] == self.worker._handler_instance
        assert clustershell.DEFAULT_HANDLERS['async'].called

    def test_execute_timeout(self):
        """Calling execute() and let the global timeout expire should call on_timeout."""
        self.worker.task.run = mock.Mock(side_effect=clustershell.Task.TimeoutError)
        self.worker.handler = 'sync'
        self.worker.execute()
        self.worker._handler_instance.on_timeout.assert_called_once_with(self.worker.task)

    def test_execute_custom_handler(self):
        """Calling execute() using a custom handler should call ClusterShell task with the custom event handler."""
        self.worker.handler = ConcreteBaseEventHandler
        self.worker.execute()
        assert isinstance(self.worker._handler_instance, ConcreteBaseEventHandler)
        args, kwargs = self.worker.task.shell.call_args
        assert args == ('command1',)
        assert kwargs['nodes'] == self.target.first_batch
        assert kwargs['handler'] == self.worker._handler_instance

    def test_execute_no_commands(self):
        """Calling execute() without commands should raise WorkerError."""
        self.worker.handler = ConcreteBaseEventHandler
        self.worker.commands = None
        with pytest.raises(WorkerError, match=r'No commands provided\.'):
            self.worker.execute()
        assert not self.worker.task.shell.called

    def test_execute_one_command_no_mode(self):
        """Calling execute() with only one command without mode should raise WorkerError."""
        self.worker.commands = [self.commands[0]]
        with pytest.raises(WorkerError, match=r'An EventHandler is mandatory\.'):
            self.worker.execute()
        assert not self.worker.task.shell.called

    def test_execute_wrong_mode(self):
        """Calling execute() without setting the mode with multiple commands should raise CuminError."""
        with pytest.raises(CuminError, match=r'An EventHandler is mandatory\.'):
            self.worker.execute()

    def test_execute_batch_size(self):
        """Calling execute() with a batch_size specified should run in batches."""
        self.worker.commands = [self.commands[0]]
        self.worker.handler = 'sync'
        self.worker.batch_size = 1
        self.worker.execute()
        args, kwargs = self.worker.task.shell.call_args
        assert args == ('command1',)
        assert kwargs['nodes'] == self.target.first_batch
        assert kwargs['handler'] == self.worker._handler_instance

    def test_get_results(self):
        """Calling get_results() should call ClusterShell iter_buffers with the right parameters."""
        self.worker.task.iter_buffers = TestClusterShellWorker.iter_buffers
        self.worker.handler = 'async'
        self.worker.execute()
        nodes = None
        output = None
        for nodes, output in self.worker.get_results():
            pass
        assert str(nodes) == 'node[90-92]'
        assert output == 'output 9'

    def test_handler_getter(self):
        """Access to handler property should return the handler class or None"""
        assert self.worker.handler is None
        self.worker.handler = 'sync'
        assert self.worker._handler == clustershell.DEFAULT_HANDLERS['sync']

    def test_handler_setter_invalid(self):
        """Raise WorkerError if trying to set it to an invalid class or value"""
        class InvalidClass(object):
            """Invalid class."""

            pass

        with pytest.raises(WorkerError, match='handler must be one of'):
            self.worker.handler = 'invalid-handler'

        with pytest.raises(WorkerError, match='handler must be one of'):
            self.worker.handler = InvalidClass

    def test_handler_setter_default_sync(self):
        """Should set the handler to the default handler for the sync mode"""
        self.worker.handler = 'sync'
        assert self.worker._handler == clustershell.DEFAULT_HANDLERS['sync']

    def test_handler_setter_default_async(self):
        """Should set the handler to the default handler for the async mode"""
        self.worker.handler = 'async'
        assert self.worker._handler == clustershell.DEFAULT_HANDLERS['async']

    def test_handler_setter_custom(self):
        """Should set the handler to the given custom class that inherit from BaseEventHandler"""
        self.worker.handler = ConcreteBaseEventHandler
        assert self.worker._handler == ConcreteBaseEventHandler

    @staticmethod
    def iter_buffers():
        """A generator to simulate the buffer iteration of ClusterShell objects."""
        for i in range(10):
            yield 'output {}'.format(i), ['node{}0'.format(i), 'node{}1'.format(i), 'node{}2'.format(i)]


class TestBaseEventHandler(object):
    """BaseEventHandler test class."""

    def setup_method(self, *args):  # pylint: disable=arguments-differ
        """Initialize default properties and instances."""
        self.target = Target(nodeset('node[1-2]'))
        self.commands = [Command('command1', ok_codes=[0, 100]), Command('command2', timeout=5)]
        self.worker = mock.MagicMock()
        self.worker.current_node = 'node1'
        self.worker.command = 'command1'
        self.worker.nodes = self.target.hosts
        self.handler = None
        self.args = args

    @mock.patch('cumin.transports.clustershell.colorama')
    def test_close(self, colorama):
        """Calling close should raise NotImplementedError."""
        self.handler = clustershell.BaseEventHandler(self.target, self.commands)
        with pytest.raises(NotImplementedError):
            self.handler.close(self.worker)
        colorama.init.assert_called_once_with(autoreset=True)


class ConcreteBaseEventHandler(clustershell.BaseEventHandler):
    """Concrete implementation of a BaseEventHandler."""

    def __init__(self, nodes, commands, **kwargs):
        """Initialize progress bars."""
        super().__init__(nodes, commands, **kwargs)
        self.pbar_ok = mock.Mock()
        self.pbar_ko = mock.Mock()

    def close(self, task):
        """Required by the BaseEventHandler class."""


class TestConcreteBaseEventHandler(TestBaseEventHandler):
    """ConcreteBaseEventHandler test class."""

    @mock.patch('cumin.transports.clustershell.colorama')
    @mock.patch('cumin.transports.clustershell.tqdm')
    def setup_method(self, _, tqdm, colorama):  # pylint: disable=arguments-differ
        """Initialize default properties and instances."""
        super().setup_method()
        self.handler = ConcreteBaseEventHandler(self.target, self.commands)
        self.worker.eh = self.handler
        self.colorama = colorama
        assert not tqdm.write.called

    def test_instantiation(self):
        """An instance of ConcreteBaseEventHandler should be an instance of BaseEventHandler and initialize colorama."""
        assert sorted(self.handler.nodes.keys()) == list(self.target.hosts)
        self.colorama.init.assert_called_once_with(autoreset=True)

    @mock.patch('cumin.transports.clustershell.tqdm')
    def test_on_timeout(self, tqdm):
        """Calling on_timeout() should update the fail progress bar."""
        for node in self.target.hosts:
            self.worker.current_node = node
            self.handler.ev_pickup(self.worker, node)
            self.handler.ev_close(self.worker, True)
        self.worker.task.num_timeout.return_value = 1
        self.worker.task.iter_keys_timeout.return_value = [self.target.hosts[0]]

        assert not self.handler.global_timedout
        self.handler.on_timeout(self.worker.task)
        assert self.handler.pbar_ko.update.called
        assert self.handler.global_timedout
        assert tqdm.write.called

    def test_ev_pickup(self):
        """Calling ev_pickup() should set the state of the current node to running."""
        for node in self.target.hosts:
            self.handler.ev_pickup(self.worker, node)
        running_nodes = [node for node in self.worker.eh.nodes.values() if node.state.is_running]
        assert running_nodes == list(self.worker.eh.nodes.values())

    @mock.patch('cumin.transports.clustershell.tqdm')
    def test_ev_read_many_hosts(self, tqdm):
        """Calling ev_read() should not print the worker message if matching multiple hosts."""
        for node in self.target.hosts:
            self.handler.ev_read(self.worker, node, self.worker.SNAME_STDOUT, 'Node output')
        assert not tqdm.write.called

    @mock.patch('cumin.transports.clustershell.tqdm')
    def test_ev_read_single_host(self, tqdm):
        """Calling ev_read() should print the worker message if matching a single host."""
        self.target = Target(nodeset('node1'))
        self.handler = ConcreteBaseEventHandler(self.target, self.commands)

        output = b'node1 output'
        self.worker.nodes = self.target.hosts
        self.handler.ev_read(self.worker, self.target.hosts[0], self.worker.SNAME_STDOUT, output)
        assert tqdm.write.call_args[0][0] == output.decode()

    def test_ev_close(self):
        """Calling ev_close() should increase the counters for the timed out hosts."""
        for node in self.target.hosts:
            self.handler.ev_pickup(self.worker, node)

        assert self.handler.counters['timeout'] == 0
        self.worker.task.num_timeout.return_value = 2
        self.handler.ev_close(self.worker, True)
        assert self.handler.counters['timeout'] == 2


class TestSyncEventHandler(TestBaseEventHandler):
    """SyncEventHandler test class."""

    @mock.patch('cumin.transports.clustershell.logging')
    @mock.patch('cumin.transports.clustershell.colorama')
    @mock.patch('cumin.transports.clustershell.tqdm')
    def setup_method(self, _, tqdm, colorama, logger):  # pylint: disable=arguments-differ
        """Initialize default properties and instances."""
        super().setup_method()
        self.handler = clustershell.SyncEventHandler(self.target, self.commands, success_threshold=1)
        self.worker.eh = self.handler
        self.colorama = colorama
        self.logger = logger
        assert not tqdm.write.called

    def test_instantiation(self):
        """An instance of SyncEventHandler should be an instance of BaseEventHandler."""
        assert isinstance(self.handler, clustershell.BaseEventHandler)

    @mock.patch('cumin.transports.clustershell.tqdm')
    def test_start_command_no_schedule(self, tqdm):
        """Calling start_command() should reset the success counter and initialize the progress bars."""
        self.handler.start_command()
        assert tqdm.called
        assert self.handler.counters['success'] == 0

    @mock.patch('cumin.transports.clustershell.Task.task_self')
    @mock.patch('cumin.transports.clustershell.tqdm')
    def test_start_command_schedule(self, tqdm, task_self):
        """Calling start_command() with schedule should also change the state of the first batch nodes."""
        # Reset the state of nodes to pending
        for node in self.handler.nodes.values():
            node.state.update(clustershell.State.running)
            node.state.update(clustershell.State.success)
            node.state.update(clustershell.State.pending)

        self.handler.start_command(schedule=True)
        assert tqdm.called
        assert self.handler.counters['success'] == 0
        scheduled_nodes = sorted(node.name for node in self.handler.nodes.values() if node.state.is_scheduled)
        assert scheduled_nodes == sorted(['node1', 'node2'])
        assert task_self.called

    @mock.patch('cumin.transports.clustershell.tqdm')
    def test_end_command(self, tqdm):
        """Calling end_command() should wrap up the command execution."""
        assert not self.handler.end_command()
        self.handler.counters['success'] = 2
        assert self.handler.end_command()
        self.handler.success_threshold = 0.5
        self.handler.counters['success'] = 1
        assert self.handler.end_command()
        self.handler.current_command_index = 1
        assert not self.handler.end_command()
        assert tqdm.write.called

    @mock.patch('cumin.transports.clustershell.tqdm')
    def test_on_timeout(self, tqdm):
        """Calling on_timeout() should call end_command()."""
        self.worker.task.num_timeout.return_value = 0
        self.worker.task.iter_keys_timeout.return_value = []
        self.handler.on_timeout(self.worker.task)
        assert tqdm.write.called

    def test_ev_timer(self):
        """Calling ev_timer() should schedule the execution of the next node/command."""
        # TODO: improve testing of ev_timer
        self.handler.ev_timer(mock.Mock())

    @mock.patch('cumin.transports.clustershell.Task.Task.timer')
    def test_ev_hup_ok(self, timer):
        """Calling ev_hup with a worker that has exit status zero should update the success progress bar."""
        self.handler.ev_pickup(self.worker, self.worker.current_node)
        self.handler.ev_hup(self.worker, self.worker.current_node, 100)
        assert self.handler.pbar_ok.update.called
        assert not timer.called
        assert self.handler.nodes[self.worker.current_node].state.is_success

    @mock.patch('cumin.transports.clustershell.Task.Task.timer')
    def test_ev_hup_ko(self, timer):
        """Calling ev_hup with a worker that has exit status non-zero should update the failed progress bar."""
        self.handler.ev_pickup(self.worker, self.worker.current_node)
        self.handler.ev_hup(self.worker, self.worker.current_node, 1)
        assert self.handler.pbar_ko.update.called
        assert not timer.called
        assert self.handler.nodes[self.worker.current_node].state.is_failed

    @mock.patch('cumin.transports.clustershell.tqdm')
    def test_close(self, tqdm):  # pylint: disable=arguments-differ
        """Calling close should print the report when needed."""
        self.handler.current_command_index = 2
        self.handler.close(self.worker)
        assert tqdm.write.called


class TestAsyncEventHandler(TestBaseEventHandler):
    """AsyncEventHandler test class."""

    @mock.patch('cumin.transports.clustershell.logging')
    @mock.patch('cumin.transports.clustershell.colorama')
    @mock.patch('cumin.transports.clustershell.tqdm')
    def setup_method(self, _, tqdm, colorama, logger):  # pylint: disable=arguments-differ
        """Initialize default properties and instances."""
        super().setup_method()
        self.handler = clustershell.AsyncEventHandler(self.target, self.commands)
        self.worker.eh = self.handler
        self.colorama = colorama
        self.logger = logger
        assert not tqdm.write.called

    def test_instantiation(self):
        """An instance of AsyncEventHandler should be an instance of BaseEventHandler and initialize progress bars."""
        assert isinstance(self.handler, clustershell.BaseEventHandler)
        assert self.handler.pbar_ok.refresh.called

    def test_ev_hup_ok(self):
        """Calling ev_hup with a worker that has zero exit status should enqueue the next command."""
        self.handler.ev_pickup(self.worker, self.worker.current_node)
        self.handler.ev_hup(self.worker, self.worker.current_node, 0)
        self.worker.task.shell.assert_called_once_with(
            'command2', handler=self.handler, timeout=5, stdin=False, nodes=nodeset(self.worker.current_node))

        # Calling it again
        self.worker.command = 'command2'
        self.handler.ev_pickup(self.worker, self.worker.current_node)
        self.handler.ev_hup(self.worker, self.worker.current_node, 0)
        assert self.handler.counters['success'] == 1
        assert self.handler.pbar_ok.update.called

    def test_ev_hup_ko(self):
        """Calling ev_hup with a worker that has non-zero exit status should not enqueue the next command."""
        self.handler.ev_pickup(self.worker, self.worker.current_node)
        self.handler.ev_hup(self.worker, self.worker.current_node, 1)
        assert self.handler.pbar_ko.update.called

    def test_ev_timer(self):
        """Calling ev_timer() should schedule the execution of the next node/command."""
        # TODO: improve testing of ev_timer
        self.handler.ev_timer(mock.Mock())

    @mock.patch('cumin.transports.clustershell.tqdm')
    def test_close(self, tqdm):  # pylint: disable=arguments-differ
        """Calling close with a worker should close progress bars."""
        self.worker.task.iter_buffers = TestClusterShellWorker.iter_buffers
        self.worker.num_timeout.return_value = 0
        self.handler.close(self.worker)
        assert self.handler.pbar_ok.close.called
        assert tqdm.write.called
