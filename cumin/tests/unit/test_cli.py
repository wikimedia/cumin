import unittest

from logging import DEBUG, INFO

import mock

from cumin import cli

# Environment variables
_ENV = {'USER': 'root', 'SUDO_USER': 'user'}
# Command line arguments
_ARGV = ['-c', 'cumin/config.yaml', '-d', '-m', 'sync', 'host', 'command1', 'command2']


class TestCLI(unittest.TestCase):
    """CLI module tests"""

    def _validate_parsed_args(self, args):
        """Validate that the parsed args have the proper values"""
        self.assertTrue(args.debug)
        self.assertEqual(args.config, 'cumin/config.yaml')
        self.assertEqual(args.hosts, 'host')
        self.assertEqual(args.commands, ['command1', 'command2'])

    def test_parse_args(self):
        """A standard set of command line parameters should be properly parsed into their respective variables"""
        args = cli.parse_args(argv=_ARGV)
        self._validate_parsed_args(args)

        with mock.patch.object(cli.sys, 'argv', ['progname'] + _ARGV):
            args = cli.parse_args()
            self._validate_parsed_args(args)

    def test_get_running_user(self):
        """Unsufficient permissions or unknown user should raise RuntimeError and a proper user should be detected"""
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
    def test_setup_logging(self, mocked_logging, mocked_file_handler, mocked_os):
        """Calling setup_logging() should properly setup the logger"""
        mocked_os.path.exists.return_value = False
        cli.setup_logging('user', '/path/to/filename')
        mocked_logging.setLevel.assert_called_with(INFO)

        mocked_os.path.exists.return_value = True
        cli.setup_logging('user', 'filename', debug=True)
        mocked_logging.setLevel.assert_called_with(DEBUG)

    def test_parse_config(self):
        """The configuration file is properly parsed and accessible"""
        config = cli.parse_config('cumin/config.yaml')
        self.assertTrue('log_file' in config)

    @mock.patch('cumin.cli.stderr')
    @mock.patch('cumin.cli.raw_input')
    @mock.patch('cumin.cli.sys.stdout.isatty')
    @mock.patch('cumin.cli.logger')
    def test_sigint_handler(self, mocked_logging, mocked_isatty, mocked_raw_input, mocked_stderr):
        """Calling the SIGINT handler should raise KeyboardInterrupt or not based on tty and answer"""
        # Signal handler called without a tty
        mocked_isatty.return_value = False
        with self.assertRaises(cli.KeyboardInterruptError):
            cli.sigint_handler(1, None)

        # # Signal handler called with a tty, answered 'y'
        # mocked_isatty.return_value = True
        # mocked_raw_input.return_value = 'y'
        # with self.assertRaises(cli.KeyboardInterruptError):
        #     cli.sigint_handler(1, None)
        #
        # # Signal handler called with a tty, answered 'n'
        # mocked_isatty.return_value = True
        # mocked_raw_input.return_value = 'n'
        # self.assertIsNone(cli.sigint_handler(1, None))
        #
        # # Signal handler called with a tty, answered 'invalid_answer'
        # mocked_isatty.return_value = True
        # mocked_raw_input.return_value = 'invalid_answer'
        # with self.assertRaises(cli.KeyboardInterruptError):
        #     cli.sigint_handler(1, None)
        #
        # # Signal handler called with a tty, empty answer
        # mocked_isatty.return_value = True
        # mocked_raw_input.return_value = ''
        # with self.assertRaises(cli.KeyboardInterruptError):
        #     cli.sigint_handler(1, None)

    @mock.patch('cumin.cli.tqdm')
    def test_stderr(self, mocked_tqdm):
        """Calling stderr() should call tqdm.write()"""
        cli.stderr('message')
        self.assertTrue(mocked_tqdm.write.called)
