"""ClusterShell transport tests"""
import unittest

import mock

from cumin.transports import BaseWorker, clustershell


class TestWorkerClass(unittest.TestCase):
    """ClusterShell backend worker_class test class"""

    @mock.patch('cumin.transports.clustershell.task_self')
    def test_worker_class(self, task_self):
        """An instance of worker_class should be an instance of BaseWorker"""
        worker = clustershell.worker_class({})
        self.assertIsInstance(worker, BaseWorker)
        task_self.assert_called_once_with()


class TestClusterShellWorker(unittest.TestCase):
    """ClusterShell backend worker test class"""

    @mock.patch('cumin.transports.clustershell.SyncEventHandler', autospec=True)
    @mock.patch('cumin.transports.clustershell.AsyncEventHandler', autospec=True)
    @mock.patch('cumin.transports.clustershell.task_self')
    def setUp(self, task_self, async_event_handler, sync_event_handler):
        """Initialize default properties and instances"""
        self.worker = clustershell.worker_class({})
        self.nodes = ['node1', 'node2']
        self.nodes_set = clustershell.NodeSet.fromlist(self.nodes)
        self.commands = ['command1', 'command2']
        self.task_self = task_self
        self.async_event_handler = async_event_handler
        self.sync_event_handler = sync_event_handler

    @mock.patch('cumin.transports.clustershell.task_self')
    def test_instantiation(self, task_self):
        """An instance of ClusterShellWorker should be an instance of BaseWorker and initialize ClusterShell"""
        worker = clustershell.ClusterShellWorker({'clustershell': {'ssh_options': ['option1', 'option2']}})
        self.assertIsInstance(worker, BaseWorker)
        task_self.assert_called_once_with()
        worker.task.set_info.assert_has_calls(
            [mock.call('ssh_options', 'option1'), mock.call('ssh_options', 'option2')])

    def test_execute_default_sync_handler(self):
        """Calling execute() in sync mode without event handler should use the default sync event handler"""
        self.worker.execute(self.nodes, self.commands, 'sync', handler=True)
        self.worker.task.shell.assert_called_once_with(
            'command1', nodes=self.nodes_set, handler=self.sync_event_handler(self.nodes, self.commands))

    def test_execute_default_async_handler(self):
        """Calling execute() in async mode without event handler should use the default async event handler"""
        self.worker.execute(self.nodes, self.commands, 'async', handler=True)
        self.worker.task.shell.assert_called_once_with(
            'command1', nodes=self.nodes_set, handler=self.async_event_handler(self.nodes, self.commands))

    def test_execute_timeout(self):
        """Calling execute() and let the timeout expire should be handled by the default event handler"""
        self.worker.task.run = mock.Mock(side_effect=clustershell.ClusterShell.Task.TimeoutError)
        self.worker.execute(self.nodes, self.commands, 'sync', handler=True)
        # no exception raised

    def test_execute_no_hanlder(self):
        """Calling execute() should call ClusterShell task without event handler"""
        self.worker.execute(self.nodes, self.commands, 'async')
        self.worker.task.shell.assert_called_once_with('command1', nodes=self.nodes_set, handler=None)

    def test_execute_custom_handler(self):
        """Calling execute() using a custom handler should call ClusterShell task with the custom event handler"""
        event_handler = mock.Mock(spec_set=clustershell.BaseEventHandler)
        self.worker.execute(self.nodes, self.commands, 'sync', handler=event_handler)
        self.worker.task.shell.assert_called_once_with('command1', nodes=self.nodes_set, handler=event_handler())

    def test_execute_no_commands(self):
        """Calling execute() without commands should return without doing anything"""
        self.worker.execute(self.nodes, [], 'sync')
        self.assertFalse(self.worker.task.shell.called)

    def test_execute_one_command_no_mode(self):
        """Calling execute() with only one command without mode should work without raising exceptions"""
        self.worker.execute(self.nodes, [self.commands[0]])
        self.worker.task.shell.assert_called_once_with('command1', nodes=self.nodes_set, handler=None)

    def test_execute_one_command_with_mode(self):
        """Calling execute() with only one command with mode should work as if it was not specified"""
        self.worker.execute(self.nodes, [self.commands[0]], 'async')
        self.worker.task.shell.assert_called_once_with('command1', nodes=self.nodes_set, handler=None)

    def test_execute_wrong_mode(self):
        """Calling execute() with the wrong mode should raise RuntimeError"""
        with self.assertRaisesRegexp(RuntimeError, 'Unknown mode'):
            self.worker.execute(self.nodes, self.commands, 'invalid_mode')

    def test_get_results(self):
        """Calling get_results() should call ClusterShell iter_buffers with the right parameters"""
        self.worker.task.iter_buffers = TestClusterShellWorker.iter_buffers
        self.worker.execute(self.nodes, self.commands, 'async')
        for nodes, output in self.worker.get_results():
            pass
        self.assertEqual(str(nodes), 'node[90-92]')
        self.assertEqual(output, 'output 9')

    @staticmethod
    def iter_buffers():
        """A generator to simulate the buffer iteration of ClusterShell objects"""
        for i in xrange(10):
            yield 'output {}'.format(i), ['node{}0'.format(i), 'node{}1'.format(i), 'node{}2'.format(i)]


class TestBaseEventHandler(unittest.TestCase):
    """BaseEventHandler test class"""
    def setUp(self, *args):
        """Initialize default properties and instances"""
        self.nodes = ['node1', 'node2']
        self.commands = ['command1', 'command2']
        self.worker = mock.MagicMock()
        self.worker.current_node = 'node1'
        self.worker.command = 'command1'
        self.handler = None

    @mock.patch('cumin.transports.clustershell.colorama')
    def test_close(self, colorama):
        """Calling close should raise NotImplementedError"""
        self.handler = clustershell.BaseEventHandler(self.nodes, self.commands)
        with self.assertRaises(NotImplementedError):
            self.handler.close(self.worker)
        colorama.init.assert_called_once_with()


class ConcreteBaseEventHandler(clustershell.BaseEventHandler):
    """Concrete implementation of a BaseEventHandler"""

    def __init__(self, nodes, commands, **kwargs):
        """Initialize progress bars"""
        super(ConcreteBaseEventHandler, self).__init__(nodes, commands, **kwargs)
        self.pbar_ok = mock.Mock()
        self.pbar_ko = mock.Mock()

    def close(self, worker):
        """Required by the BaseEventHandler class"""


class TestConcreteBaseEventHandler(TestBaseEventHandler):
    """ConcreteBaseEventHandler test class"""

    @mock.patch('cumin.transports.clustershell.colorama')
    def setUp(self, colorama):
        """Initialize default properties and instances"""
        super(TestConcreteBaseEventHandler, self).setUp()
        self.handler = ConcreteBaseEventHandler(self.nodes, self.commands)
        self.worker.eh = self.handler
        self.colorama = colorama

    def test_instantiation(self):
        """An instance of ConcreteBaseEventHandler should be an instance of BaseEventHandler and initialize colorama"""
        self.assertListEqual(self.handler.nodes, self.nodes)
        self.colorama.init.assert_called_once_with()

    def test_ev_error(self):
        """Calling ev_error should update the fail progress bar"""
        self.handler.ev_error(self.worker)
        self.handler.pbar_ko.update.assert_called_once_with()

    def test_ev_timeout(self):
        """Calling test_ev_timeout should update the fail progress bar"""
        self.handler.ev_timeout(self.worker)
        self.assertTrue(self.handler.pbar_ko.update.called)


class TestSyncEventHandler(TestBaseEventHandler):
    """SyncEventHandler test class"""

    @mock.patch('cumin.transports.clustershell.colorama')
    @mock.patch('cumin.transports.clustershell.tqdm')
    def setUp(self, tqdm, colorama):
        """Initialize default properties and instances"""
        super(TestSyncEventHandler, self).setUp()
        self.handler = clustershell.SyncEventHandler(self.nodes, self.commands)
        self.worker.eh = self.handler
        if self._testMethodName != 'test_instantiation':
            # Don't start the handler for the instantiation test
            self.handler.ev_start(self.worker)

    def test_instantiation(self):
        """An instance of SyncEventHandler should be an instance of BaseEventHandler and initialize nodes_commands"""
        self.assertIsInstance(self.handler, clustershell.BaseEventHandler)
        self.assertListEqual(self.handler.nodes_commands, self.commands)

    def test_ev_start(self):
        """Calling ev_start should initialize tqdm and refresh it"""
        self.assertTrue(self.handler.pbar_ok.refresh.called)

        # Running it again should fail
        with self.assertRaisesRegexp(RuntimeError, r'command2 !='):
            self.handler.ev_start(self.worker)

    def test_ev_hup_ok(self):
        """Calling ev_hup with a worker that has exit status zero should update the success progress bar"""
        self.worker.current_rc = 0
        self.handler.ev_hup(self.worker)
        self.assertTrue(self.handler.pbar_ok.update.called)

    def test_ev_hup_ko(self):
        """Calling ev_hup with a worker that has exit status non-zero should update the failed progress bar"""
        self.worker.current_rc = 1
        self.handler.ev_hup(self.worker)
        self.assertTrue(self.handler.pbar_ko.update.called)

    def test_ev_close(self):
        """Calling close should close progress bars"""
        self.worker.task.iter_buffers = TestClusterShellWorker.iter_buffers
        self.worker.num_timeout.return_value = 0
        self.handler.ev_close(self.worker)
        self.assertTrue(self.handler.pbar_ko.close.called)


class TestAsyncEventHandler(TestBaseEventHandler):
    """AsyncEventHandler test class"""

    @mock.patch('cumin.transports.clustershell.colorama')
    @mock.patch('cumin.transports.clustershell.tqdm')
    def setUp(self, tqdm, colorama):
        """Initialize default properties and instances"""
        super(TestAsyncEventHandler, self).setUp()
        self.handler = clustershell.AsyncEventHandler(self.nodes, self.commands)
        self.worker.eh = self.handler

    def test_instantiation(self):
        """An instance of AsyncEventHandler should be an instance of BaseEventHandler and initialize progress bars"""
        self.assertIsInstance(self.handler, clustershell.BaseEventHandler)
        self.assertTrue(self.handler.pbar_ok.refresh.called)

    def test_ev_pickup(self):
        """Calling ev_pickup should not raise exception the first time, raise the second one"""
        self.handler.ev_start(self.worker)
        self.handler.ev_pickup(self.worker)
        # no exception raised

        with self.assertRaisesRegexp(RuntimeError, r'command2 !='):
            self.handler.ev_pickup(self.worker)

    def test_ev_hup_ok(self):
        """Calling ev_hup with a worker that has zero exit status should update enqueue the next command"""
        self.handler.ev_start(self.worker)
        self.handler.ev_pickup(self.worker)
        self.worker.current_rc = 0
        self.handler.ev_hup(self.worker)
        self.worker.task.shell.assert_called_once_with('command2', nodes=self.worker.current_node, handler=self.handler)

        # Calling it again
        self.worker.command = 'command2'
        self.handler.ev_pickup(self.worker)
        self.worker.current_rc = 0
        self.handler.ev_hup(self.worker)
        self.assertListEqual(self.handler.success_nodes, ['node1'])
        self.assertTrue(self.handler.pbar_ok.update.called)

    def test_ev_hup_ko(self):
        """Calling ev_hup with a worker that has non-zero exit status should not enqueue the next command"""
        self.handler.ev_start(self.worker)
        self.handler.ev_pickup(self.worker)
        self.worker.current_rc = 1
        self.handler.ev_hup(self.worker)
        self.assertFalse(self.worker.task.shell.called)
        self.assertTrue(self.handler.pbar_ko.update.called)

    @mock.patch('cumin.transports.clustershell.colorama')
    def test_close(self, colorama):
        """Calling close with a worker should close progress bars"""
        self.handler.ev_start(self.worker)
        self.worker.task.iter_buffers = TestClusterShellWorker.iter_buffers
        self.worker.num_timeout.return_value = 0
        self.handler.close(self.worker)
        self.assertTrue(self.handler.pbar_ok.close.called)
