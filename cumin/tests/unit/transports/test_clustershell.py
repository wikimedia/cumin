"""ClusterShell transport tests."""

import unittest

import mock

from cumin.transports import BaseWorker, Command, clustershell, State, WorkerError


class TestNode(unittest.TestCase):
    """Node class tests."""

    def test_instantiation(self):
        """Default values should be set when a Node instance is created."""
        node = clustershell.Node('name', [Command('command1'), Command('command2')])
        self.assertEqual(node.running_command_index, -1)
        self.assertIsInstance(node.state, State)


class TestWorkerClass(unittest.TestCase):
    """ClusterShell backend worker_class test class."""

    @mock.patch('cumin.transports.clustershell.Task.task_self')
    def test_worker_class(self, task_self):
        """An instance of worker_class should be an instance of BaseWorker."""
        worker = clustershell.worker_class({})
        self.assertIsInstance(worker, BaseWorker)
        task_self.assert_called_once_with()


class TestClusterShellWorker(unittest.TestCase):
    """ClusterShell backend worker test class."""

    @mock.patch('cumin.transports.clustershell.Task.task_self')
    def setUp(self, task_self):
        """Initialize default properties and instances"""
        self.config = {
            'clustershell': {
                'ssh_options': ['-o StrictHostKeyChecking=no', '-o BatchMode=yes'],
                'fanout': 3}}

        self.worker = clustershell.worker_class(self.config)
        self.nodes = ['node1', 'node2']
        self.nodes_set = clustershell.NodeSet.NodeSet.fromlist(self.nodes)
        self.commands = [Command('command1'), Command('command2', ok_codes=[0, 100], timeout=5)]
        self.task_self = task_self
        # Mock default handlers
        clustershell.DEFAULT_HANDLERS = {
            'sync': mock.MagicMock(spec_set=clustershell.SyncEventHandler),
            'async': mock.MagicMock(spec_set=clustershell.AsyncEventHandler)}

        # Initialize the worker
        self.worker.hosts = self.nodes
        self.worker.commands = self.commands

    @mock.patch('cumin.transports.clustershell.Task.task_self')
    def test_instantiation(self, task_self):
        """An instance of ClusterShellWorker should be an instance of BaseWorker and initialize ClusterShell."""
        worker = clustershell.ClusterShellWorker(self.config)
        self.assertIsInstance(worker, BaseWorker)
        task_self.assert_called_once_with()
        worker.task.set_info.assert_has_calls(
            [mock.call('fanout', 3),
             mock.call('ssh_options', '-o StrictHostKeyChecking=no -o BatchMode=yes')], any_order=True)

    def test_execute_default_sync_handler(self):
        """Calling execute() in sync mode without event handler should use the default sync event handler."""
        self.worker.handler = 'sync'
        self.worker.execute()
        self.worker.task.shell.assert_called_once_with(
            'command1', nodes=self.nodes_set, handler=self.worker._handler_instance, timeout=None)
        self.assertTrue(clustershell.DEFAULT_HANDLERS['sync'].called)

    def test_execute_default_async_handler(self):
        """Calling execute() in async mode without event handler should use the default async event handler."""
        self.worker.handler = 'async'
        self.worker.execute()
        self.worker.task.shell.assert_called_once_with(
            'command1', nodes=self.nodes_set, handler=self.worker._handler_instance, timeout=None)
        self.assertTrue(clustershell.DEFAULT_HANDLERS['async'].called)

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
        self.assertIsInstance(self.worker._handler_instance, ConcreteBaseEventHandler)
        self.worker.task.shell.assert_called_once_with(
            'command1', nodes=self.nodes_set, handler=self.worker._handler_instance, timeout=None)

    def test_execute_no_commands(self):
        """Calling execute() without commands should return without doing anything."""
        self.worker.commands = []
        self.worker.execute()
        self.assertFalse(self.worker.task.shell.called)

    def test_execute_one_command_no_mode(self):
        """Calling execute() with only one command without mode should raise exception."""
        self.worker.commands = [self.commands[0]]
        with self.assertRaisesRegexp(RuntimeError, 'An EventHandler is mandatory.'):
            self.worker.execute()

    def test_execute_wrong_mode(self):
        """Calling execute() without setting the mode with multiple commands should raise RuntimeError."""
        with self.assertRaisesRegexp(RuntimeError, r'An EventHandler is mandatory.'):
            self.worker.execute()

    def test_execute_batch_size(self):
        """Calling execute() with a batch_size specified should run in batches."""
        self.worker.commands = [self.commands[0]]
        self.worker.handler = 'sync'
        self.worker.batch_size = 1
        self.worker.execute()
        self.worker.task.shell.assert_called_once_with(
            'command1', nodes=clustershell.NodeSet.NodeSet(self.nodes[0]), handler=self.worker._handler_instance,
            timeout=None)

    def test_get_results(self):
        """Calling get_results() should call ClusterShell iter_buffers with the right parameters."""
        self.worker.task.iter_buffers = TestClusterShellWorker.iter_buffers
        self.worker.handler = 'async'
        self.worker.execute()
        for nodes, output in self.worker.get_results():
            pass
        self.assertEqual(str(nodes), 'node[90-92]')
        self.assertEqual(output, 'output 9')

    def test_handler_getter(self):
        """Access to handler property should return the handler class or None"""
        self.assertIsNone(self.worker.handler)
        self.worker.handler = 'sync'
        self.assertEqual(self.worker._handler, clustershell.DEFAULT_HANDLERS['sync'])

    def test_handler_setter_invalid(self):
        """Raise WorkerError if trying to set it to an invalid class or value"""
        class InvalidClass(object):
            pass

        with self.assertRaisesRegexp(WorkerError, r'handler must be one of'):
            self.worker.handler = 'invalid-handler'

        with self.assertRaisesRegexp(WorkerError, r'handler must be one of'):
            self.worker.handler = InvalidClass

    def test_handler_setter_default_sync(self):
        """Should set the handler to the default handler for the sync mode"""
        self.worker.handler = 'sync'
        self.assertEqual(self.worker._handler, clustershell.DEFAULT_HANDLERS['sync'])

    def test_handler_setter_default_async(self):
        """Should set the handler to the default handler for the async mode"""
        self.worker.handler = 'async'
        self.assertEqual(self.worker._handler, clustershell.DEFAULT_HANDLERS['async'])

    def test_handler_setter_custom(self):
        """Should set the handler to the given custom class that inherit from BaseEventHandler"""
        self.worker.handler = ConcreteBaseEventHandler
        self.assertEqual(self.worker._handler, ConcreteBaseEventHandler)

    @staticmethod
    def iter_buffers():
        """A generator to simulate the buffer iteration of ClusterShell objects."""
        for i in xrange(10):
            yield 'output {}'.format(i), ['node{}0'.format(i), 'node{}1'.format(i), 'node{}2'.format(i)]


class TestBaseEventHandler(unittest.TestCase):
    """BaseEventHandler test class."""

    def setUp(self, *args):
        """Initialize default properties and instances."""
        self.nodes = ['node1', 'node2']
        self.commands = [Command('command1', ok_codes=[0, 100]), Command('command2', timeout=5)]
        self.worker = mock.MagicMock()
        self.worker.current_node = 'node1'
        self.worker.command = 'command1'
        self.worker.nodes = clustershell.NodeSet.NodeSet.fromlist(self.nodes)
        self.handler = None

    @mock.patch('cumin.transports.clustershell.colorama')
    def test_close(self, colorama):
        """Calling close should raise NotImplementedError."""
        self.handler = clustershell.BaseEventHandler(self.nodes, self.commands)
        with self.assertRaises(NotImplementedError):
            self.handler.close(self.worker)
        colorama.init.assert_called_once_with()


class ConcreteBaseEventHandler(clustershell.BaseEventHandler):
    """Concrete implementation of a BaseEventHandler."""

    def __init__(self, nodes, commands, **kwargs):
        """Initialize progress bars."""
        super(ConcreteBaseEventHandler, self).__init__(nodes, commands, **kwargs)
        self.pbar_ok = mock.Mock()
        self.pbar_ko = mock.Mock()

    def close(self, worker):
        """Required by the BaseEventHandler class."""


class TestConcreteBaseEventHandler(TestBaseEventHandler):
    """ConcreteBaseEventHandler test class."""

    @mock.patch('cumin.transports.clustershell.colorama')
    @mock.patch('cumin.transports.clustershell.tqdm')
    def setUp(self, tqdm, colorama):
        """Initialize default properties and instances."""
        super(TestConcreteBaseEventHandler, self).setUp()
        self.handler = ConcreteBaseEventHandler(
            self.nodes, self.commands, batch_size=len(self.nodes), batch_sleep=0.0, first_batch=self.nodes)
        self.worker.eh = self.handler
        self.tqdm = tqdm
        self.colorama = colorama

    def test_instantiation(self):
        """An instance of ConcreteBaseEventHandler should be an instance of BaseEventHandler and initialize colorama."""
        self.assertListEqual(sorted(self.handler.nodes.keys()), self.nodes)
        self.colorama.init.assert_called_once_with()

    @mock.patch('cumin.transports.clustershell.tqdm')
    def test_on_timeout(self, tqdm):
        """Calling on_timeout() should update the fail progress bar."""
        for node in self.nodes:
            self.worker.current_node = node
            self.handler.ev_pickup(self.worker)
        self.worker.task.num_timeout.return_value = 1
        self.worker.task.iter_keys_timeout.return_value = [self.nodes[0]]

        self.assertFalse(self.handler.global_timedout)
        self.handler.on_timeout(self.worker.task)
        self.assertTrue(self.handler.pbar_ko.update.called)
        self.assertTrue(self.handler.global_timedout)

    def test_ev_pickup(self):
        """Calling ev_pickup() should set the state of the current node to running."""
        for node in self.nodes:
            self.worker.current_node = node
            self.handler.ev_pickup(self.worker)
        self.assertListEqual([node for node in self.worker.eh.nodes.itervalues() if node.state.is_running],
                             self.worker.eh.nodes.values())

    @mock.patch('cumin.transports.clustershell.tqdm')
    def test_ev_read_many_hosts(self, tqdm):
        """Calling ev_read() should not print the worker message if matching multiple hosts."""
        for node in self.nodes:
            self.worker.current_node = node
            self.worker.current_msg = 'Node output'
            self.handler.ev_read(self.worker)
        self.assertFalse(tqdm.write.called)

    @mock.patch('cumin.transports.clustershell.tqdm')
    def test_ev_read_single_host(self, tqdm):
        """Calling ev_read() should print the worker message if matching a single host."""
        nodes = ['node1']
        self.nodes = nodes
        self.handler = ConcreteBaseEventHandler(
            nodes, self.commands, batch_size=len(self.nodes), batch_sleep=0.0, first_batch=self.nodes)

        output = 'node1 output'
        self.worker.nodes = clustershell.NodeSet.NodeSet.fromlist(nodes)
        self.worker.current_node = nodes[0]
        self.worker.current_msg = output
        self.handler.ev_read(self.worker)
        tqdm.write.assert_has_calls([mock.call(output)])

    def test_ev_timeout(self):
        """Calling ev_timeout() should increase the counters for the timed out hosts."""
        for node in self.nodes:
            self.worker.current_node = node
            self.handler.ev_pickup(self.worker)

        self.assertEqual(self.handler.counters['timeout'], 0)
        self.worker.task.num_timeout.return_value = 2
        self.handler.ev_timeout(self.worker)
        self.assertEqual(self.handler.counters['timeout'], 2)


class TestSyncEventHandler(TestBaseEventHandler):
    """SyncEventHandler test class."""

    @mock.patch('cumin.transports.clustershell.logging')
    @mock.patch('cumin.transports.clustershell.colorama')
    @mock.patch('cumin.transports.clustershell.tqdm')
    def setUp(self, tqdm, colorama, logger):
        """Initialize default properties and instances."""
        super(TestSyncEventHandler, self).setUp()
        self.handler = clustershell.SyncEventHandler(
            self.nodes, self.commands, success_threshold=1, batch_size=len(self.nodes), batch_sleep=0, logger=None,
            first_batch=self.nodes)
        self.worker.eh = self.handler
        self.tqdm = tqdm
        self.colorama = colorama

    def test_instantiation(self):
        """An instance of SyncEventHandler should be an instance of BaseEventHandler."""
        self.assertIsInstance(self.handler, clustershell.BaseEventHandler)

    @mock.patch('cumin.transports.clustershell.tqdm')
    def test_start_command_no_schedule(self, tqdm):
        """Calling start_command() should reset the success counter and initialize the progress bars."""
        self.handler.start_command()
        self.assertTrue(tqdm.called)
        self.assertEqual(self.handler.counters['success'], 0)

    @mock.patch('cumin.transports.clustershell.Task.task_self')
    @mock.patch('cumin.transports.clustershell.tqdm')
    def test_start_command_schedule(self, tqdm, task_self):
        """Calling start_command() with schedule should also change the state of the first batch nodes."""
        # Reset the state of nodes to pending
        for node in self.handler.nodes.itervalues():
            node.state.update(clustershell.State.running)
            node.state.update(clustershell.State.success)
            node.state.update(clustershell.State.pending)

        self.handler.start_command(schedule=True)
        self.assertTrue(tqdm.called)
        self.assertEqual(self.handler.counters['success'], 0)
        self.assertListEqual(sorted(node.name for node in self.handler.nodes.itervalues() if node.state.is_scheduled),
                             sorted(['node1', 'node2']))
        self.assertTrue(task_self.called)

    @mock.patch('cumin.transports.clustershell.tqdm')
    def test_end_command(self, tqdm):
        """Calling end_command() should wrap up the command execution."""
        self.assertFalse(self.handler.end_command())
        self.handler.counters['success'] = 2
        self.assertTrue(self.handler.end_command())
        self.handler.kwargs['success_threshold'] = 0.5
        self.handler.counters['success'] = 1
        self.assertTrue(self.handler.end_command())
        self.handler.current_command_index = 1
        self.assertFalse(self.handler.end_command())
        self.assertTrue(tqdm.write.called)

    @mock.patch('cumin.transports.clustershell.tqdm')
    def test_on_timeout(self, tqdm):
        """Calling on_timeout() should call end_command()."""
        self.worker.task.num_timeout.return_value = 0
        self.worker.task.iter_keys_timeout.return_value = []
        self.handler.on_timeout(self.worker.task)
        self.assertTrue(tqdm.write.called)

    def test_ev_timer(self):
        """Calling ev_timer() should schedule the execution of the next node/command."""
        # TODO: improve testing of ev_timer
        self.handler.ev_timer(mock.Mock())

    @mock.patch('cumin.transports.clustershell.Task.Task.timer')
    def test_ev_hup_ok(self, timer):
        """Calling ev_hup with a worker that has exit status zero should update the success progress bar."""
        self.worker.current_rc = 100
        self.handler.ev_pickup(self.worker)
        self.handler.ev_hup(self.worker)
        self.assertTrue(self.handler.pbar_ok.update.called)
        self.assertFalse(timer.called)
        self.assertTrue(self.handler.nodes[self.worker.current_node].state.is_success)

    @mock.patch('cumin.transports.clustershell.Task.Task.timer')
    def test_ev_hup_ko(self, timer):
        """Calling ev_hup with a worker that has exit status non-zero should update the failed progress bar."""
        self.worker.current_rc = 1
        self.handler.ev_pickup(self.worker)
        self.handler.ev_hup(self.worker)
        self.assertTrue(self.handler.pbar_ko.update.called)
        self.assertFalse(timer.called)
        self.assertTrue(self.handler.nodes[self.worker.current_node].state.is_failed)

    @mock.patch('cumin.transports.clustershell.tqdm')
    def test_close(self, tqdm):
        """Calling close should print the report when needed."""
        self.handler.current_command_index = 2
        self.handler.close(self.worker)
        self.assertTrue(tqdm.write.called)


class TestAsyncEventHandler(TestBaseEventHandler):
    """AsyncEventHandler test class."""

    @mock.patch('cumin.transports.clustershell.logging')
    @mock.patch('cumin.transports.clustershell.colorama')
    @mock.patch('cumin.transports.clustershell.tqdm')
    def setUp(self, tqdm, colorama, logger):
        """Initialize default properties and instances."""
        super(TestAsyncEventHandler, self).setUp()
        self.handler = clustershell.AsyncEventHandler(self.nodes, self.commands)
        self.worker.eh = self.handler

    def test_instantiation(self):
        """An instance of AsyncEventHandler should be an instance of BaseEventHandler and initialize progress bars."""
        self.assertIsInstance(self.handler, clustershell.BaseEventHandler)
        self.assertTrue(self.handler.pbar_ok.refresh.called)

    def test_ev_hup_ok(self):
        """Calling ev_hup with a worker that has zero exit status should enqueue the next command."""
        for node in self.handler.nodes.itervalues():
            node.state.update(State.scheduled)
        self.handler.ev_pickup(self.worker)
        self.worker.current_rc = 0
        self.handler.ev_hup(self.worker)
        self.worker.task.shell.assert_called_once_with(
            'command2', nodes=clustershell.NodeSet.NodeSet(self.worker.current_node), handler=self.handler, timeout=5)

        # Calling it again
        self.worker.command = 'command2'
        self.handler.ev_pickup(self.worker)
        self.worker.current_rc = 0
        self.handler.ev_hup(self.worker)
        self.assertEqual(self.handler.counters['success'], 1)
        self.assertTrue(self.handler.pbar_ok.update.called)

    def test_ev_hup_ko(self):
        """Calling ev_hup with a worker that has non-zero exit status should not enqueue the next command."""
        for node in self.handler.nodes.itervalues():
            node.state.update(State.scheduled)
        self.handler.ev_pickup(self.worker)
        self.worker.current_rc = 1
        self.handler.ev_hup(self.worker)
        self.assertTrue(self.handler.pbar_ko.update.called)

    def test_ev_timer(self):
        """Calling ev_timer() should schedule the execution of the next node/command."""
        # TODO: improve testing of ev_timer
        self.handler.ev_timer(mock.Mock())

    @mock.patch('cumin.transports.clustershell.tqdm')
    def test_close(self, tqdm):
        """Calling close with a worker should close progress bars."""
        self.worker.task.iter_buffers = TestClusterShellWorker.iter_buffers
        self.worker.num_timeout.return_value = 0
        self.handler.close(self.worker)
        self.assertTrue(self.handler.pbar_ok.close.called)
        self.assertTrue(tqdm.write.called)
