"""CLI tests."""

import unittest
import sys

from functools import wraps
from logging import DEBUG, INFO
from StringIO import StringIO

import mock

from cumin import cli

# Environment variables
_ENV = {'USER': 'root', 'SUDO_USER': 'user'}
# Command line arguments
_ARGV = ['-c', 'doc/examples/config.yaml', '-d', '-m', 'sync', 'host', 'command1', 'command2']


def capture_stderr(func):
    """Decorator to capture stderr while running a test method.

    Arguments
    func -- the function to be decorated
    """
    @wraps(func)
    def func_wrapper(self):
        """The actual stderr capturer.

        Arguments
        self -- the 'self' of the decorated method.
        """
        # Mask stderr because ArgumentParser error print directly to stderr and nosetest doesn't capture it.
        stderr = sys.stderr
        try:
            err = StringIO()
            sys.stderr = err
            func(self)
        finally:
            sys.stderr = stderr

    return func_wrapper


class TestCLI(unittest.TestCase):
    """CLI module tests."""

    def _validate_parsed_args(self, args):
        """Validate that the parsed args have the proper values."""
        self.assertTrue(args.debug)
        self.assertEqual(args.config, 'doc/examples/config.yaml')
        self.assertEqual(args.hosts, 'host')
        self.assertEqual(args.commands, ['command1', 'command2'])

    def test_parse_args_ok(self):
        """A standard set of command line parameters should be properly parsed into their respective variables."""
        args = cli.parse_args(argv=_ARGV)
        self._validate_parsed_args(args)

        with mock.patch.object(cli.sys, 'argv', ['progname'] + _ARGV):
            args = cli.parse_args()
            self._validate_parsed_args(args)

    @capture_stderr
    def test_parse_args_no_mode(self):
        """If mode is not speficied with multiple commands, parsing the args should raise a parser error."""
        index = _ARGV.index('-m')
        with self.assertRaises(SystemExit):
            cli.parse_args(argv=_ARGV[:index] + _ARGV[index + 1:])

    def test_get_running_user(self):
        """Unsufficient permissions or unknown user should raise RuntimeError and a proper user should be detected."""
        env = {'USER': None, 'SUDO_USER': None}
        with mock.patch('os.getenv', env.get):
            with self.assertRaisesRegexp(RuntimeError, r'Unsufficient privileges, run with sudo'):
                cli.get_running_user()

        env = {'USER': 'root', 'SUDO_USER': None}
        with mock.patch('os.getenv', env.get):
            with self.assertRaisesRegexp(RuntimeError, r'Unable to determine real user'):
                cli.get_running_user()

        with mock.patch('os.getenv', _ENV.get):
            self.assertEqual(cli.get_running_user(), 'user')

    @mock.patch('cumin.cli.os')
    @mock.patch('cumin.cli.RotatingFileHandler')
    @mock.patch('cumin.cli.logger')
    def test_setup_logging(self, logging, file_handler, os):
        """Calling setup_logging() should properly setup the logger."""
        os.path.exists.return_value = False
        cli.setup_logging('/path/to/filename')
        logging.setLevel.assert_called_with(INFO)

        os.path.exists.return_value = True
        cli.setup_logging('filename', debug=True)
        logging.setLevel.assert_called_with(DEBUG)

    def test_parse_config(self):
        """The configuration file is properly parsed and accessible."""
        config = cli.parse_config('doc/examples/config.yaml')
        self.assertTrue('log_file' in config)

    @mock.patch('cumin.cli.stderr')
    @mock.patch('cumin.cli.raw_input')
    @mock.patch('cumin.cli.sys.stdout.isatty')
    @mock.patch('cumin.cli.logger')
    def test_sigint_handler(self, logging, isatty, mocked_raw_input, stderr):
        """Calling the SIGINT handler should raise KeyboardInterrupt or not based on tty and answer."""
        # Signal handler called without a tty
        isatty.return_value = False
        with self.assertRaises(cli.KeyboardInterruptError):
            cli.sigint_handler(1, None)

        # Signal handler called with a tty
        isatty.return_value = True
        with self.assertRaises(cli.KeyboardInterruptError):
            cli.sigint_handler(1, None)

        # # Signal handler called with a tty, answered 'y'
        # isatty.return_value = True
        # mocked_raw_input.return_value = 'y'
        # with self.assertRaises(cli.KeyboardInterruptError):
        #     cli.sigint_handler(1, None)
        #
        # # Signal handler called with a tty, answered 'n'
        # isatty.return_value = True
        # mocked_raw_input.return_value = 'n'
        # self.assertIsNone(cli.sigint_handler(1, None))
        #
        # # Signal handler called with a tty, answered 'invalid_answer'
        # isatty.return_value = True
        # mocked_raw_input.return_value = 'invalid_answer'
        # with self.assertRaises(cli.KeyboardInterruptError):
        #     cli.sigint_handler(1, None)
        #
        # # Signal handler called with a tty, empty answer
        # isatty.return_value = True
        # mocked_raw_input.return_value = ''
        # with self.assertRaises(cli.KeyboardInterruptError):
        #     cli.sigint_handler(1, None)

    @mock.patch('cumin.cli.tqdm')
    def test_stderr(self, tqdm):
        """Calling stderr() should call tqdm.write()."""
        cli.stderr('message')
        self.assertTrue(tqdm.write.called)

    @mock.patch('cumin.cli.stderr')
    @mock.patch('cumin.cli.raw_input')
    @mock.patch('cumin.cli.sys.stdout.isatty')
    def test_get_hosts_ok(self, isatty, mocked_raw_input, stderr):
        """Calling get_hosts() should query the backend and return the list of hosts."""
        args = cli.parse_args(argv=['host1', 'command1'])
        config = {'backend': 'direct'}
        isatty.return_value = True

        mocked_raw_input.return_value = 'y'
        self.assertListEqual(cli.get_hosts(args, config), ['host1'])

        mocked_raw_input.return_value = 'n'
        with self.assertRaises(cli.KeyboardInterruptError):
            cli.get_hosts(args, config)

        mocked_raw_input.return_value = 'invalid_answer'
        with self.assertRaises(cli.KeyboardInterruptError):
            cli.get_hosts(args, config)

        mocked_raw_input.return_value = ''
        with self.assertRaises(cli.KeyboardInterruptError):
            cli.get_hosts(args, config)

    @mock.patch('cumin.cli.stderr')
    def test_get_hosts_no_tty_ko(self, stderr):
        """Calling get_hosts() without a TTY should raise RuntimeError if --dry-run or --force are not specified."""
        args = cli.parse_args(argv=['host1', 'command1'])
        config = {'backend': 'direct'}
        with self.assertRaisesRegexp(RuntimeError, 'Not in a TTY but neither DRY-RUN nor FORCE mode were specified'):
            cli.get_hosts(args, config)
        self.assertTrue(stderr.called)

    @mock.patch('cumin.cli.stderr')
    @mock.patch('cumin.cli.sys.stdout.isatty')
    def test_get_hosts_no_tty_dry_run(self, isatty, stderr):
        """Calling get_hosts() with or without a TTY with --dry-run should return an empty list."""
        args = cli.parse_args(argv=['--dry-run', 'host1', 'command1'])
        config = {'backend': 'direct'}
        self.assertListEqual(cli.get_hosts(args, config), [])
        isatty.return_value = True
        self.assertListEqual(cli.get_hosts(args, config), [])
        self.assertTrue(stderr.called)

    @mock.patch('cumin.cli.stderr')
    @mock.patch('cumin.cli.sys.stdout.isatty')
    def test_get_hosts_no_tty_force(self, isatty, stderr):
        """Calling get_hosts() with or without a TTY with --force should return the list of hosts."""
        args = cli.parse_args(argv=['--force', 'host1', 'command1'])
        config = {'backend': 'direct'}
        self.assertListEqual(cli.get_hosts(args, config), ['host1'])
        isatty.return_value = True
        self.assertListEqual(cli.get_hosts(args, config), ['host1'])
        self.assertTrue(stderr.called)

    @mock.patch('cumin.cli.Transport')
    @mock.patch('cumin.cli.stderr')
    def test_run(self, stderr, transport):
        """Calling run() should query the hosts and execute the commands on the transport."""
        args = cli.parse_args(argv=['--force', 'host1', 'command1'])
        config = {'backend': 'direct', 'transport': 'clustershell'}
        cli.run(args, config)
        transport.new.assert_called_once_with(config, cli.logger)
