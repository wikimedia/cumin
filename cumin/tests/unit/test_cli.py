"""CLI tests."""
import argparse

from logging import DEBUG, INFO
from unittest import mock

import pytest

from cumin import cli, CuminError, LOGGING_TRACE_LEVEL_NUMBER, nodeset, transports


# Environment variables
_ENV = {'USER': 'root', 'SUDO_USER': 'user'}
# Command line arguments
_ARGV = ['-c', 'doc/examples/config.yaml', '-d', '-m', 'sync', 'host', 'command1', 'command2']


def _validate_parsed_args(args, no_commands=False):
    """Validate that the parsed args have the proper values."""
    assert args.debug
    assert args.config == 'doc/examples/config.yaml'
    assert args.hosts == 'host'
    if no_commands:
        assert args.dry_run
    else:
        assert args.commands == ['command1', 'command2']


def test_get_parser():
    """Calling get_parser() should return a populated argparse.ArgumentParser object."""
    parser = cli.get_parser()
    assert isinstance(parser, argparse.ArgumentParser)
    assert parser.prog == 'cumin'


def test_parse_args_help(capsys):
    """Calling cumin with -h/--help should return its help message."""
    with pytest.raises(SystemExit) as e:
        cli.parse_args(['-h'])

    out, _ = capsys.readouterr()
    assert e.value.code == 0
    assert 'Cumin CLI - Automation and orchestration framework written in Python' in out


def test_parse_args_ok():
    """A standard set of command line parameters should be properly parsed into their respective variables."""
    args = cli.parse_args(_ARGV)
    _validate_parsed_args(args)


def test_parse_args_no_commands():
    """If no commands are specified, dry-run mode should be implied."""
    args = cli.parse_args(_ARGV[:-2])
    _validate_parsed_args(args, no_commands=True)


def test_parse_args_no_mode():
    """If mode is not specified with multiple commands, parsing the args should raise a parser error."""
    index = _ARGV.index('-m')
    with pytest.raises(SystemExit):
        cli.parse_args(_ARGV[:index] + _ARGV[index + 1:])


def test_target_batch_size():
    """Calling target_batch_size() should properly parse integer values."""
    assert cli.target_batch_size('1') == {'value': 1, 'ratio': None}
    assert cli.target_batch_size('100') == {'value': 100, 'ratio': None}


@pytest.mark.parametrize('percentage', (('0%', 0.0), ('50%', 0.5), ('100%', 1.0)))
def test_target_batch_size_perc(percentage):
    """Calling target_batch_size() with a valid percentage should properly parse it."""
    assert cli.target_batch_size(percentage[0]) == {'value': None, 'ratio': percentage[1]}


@pytest.mark.parametrize('percentage', ('-1%', '101%'))
def test_target_batch_size_perc_ko(percentage):
    """Calling target_batch_size() with invalid percentage should raise argparse.ArgumentTypeError."""
    with pytest.raises(argparse.ArgumentTypeError, match='not a valid percentage'):
        cli.target_batch_size(percentage)


@pytest.mark.parametrize('value', ('0', '-1'))
def test_target_batch_size_val_ko(value):
    """Calling target_batch_size() with invalid value should raise argparse.ArgumentTypeError."""
    with pytest.raises(argparse.ArgumentTypeError, match='is not a valid value'):
        cli.target_batch_size(value)


def test_get_running_user():
    """Unsufficient permissions or unknown user should raise CuminError and a proper user should be detected."""
    env = {'USER': None, 'SUDO_USER': None}
    with mock.patch('os.getenv', env.get):
        with pytest.raises(CuminError, match='Insufficient privileges, run with sudo'):
            cli.get_running_user()

    env = {'USER': 'root', 'SUDO_USER': None}
    with mock.patch('os.getenv', env.get):
        with pytest.raises(CuminError, match='Unable to determine real user'):
            cli.get_running_user()

    with mock.patch('os.getenv', _ENV.get):
        assert cli.get_running_user() == 'user'


@mock.patch('cumin.cli.os.path.exists')
@mock.patch('cumin.cli.os.makedirs')
@mock.patch('cumin.cli.RotatingFileHandler')
@mock.patch('cumin.cli.logging.getLogger')
def test_setup_logging(mocked_get_logger, mocked_file_handler, mocked_os_makedirs, mocked_os_path_exists):
    """Calling setup_logging() should properly setup the logger."""
    mocked_os_path_exists.return_value = False
    cli.setup_logging('/path/to/filename.yaml')
    assert mock.call().setLevel(INFO) in mocked_get_logger.mock_calls
    assert mocked_file_handler.called
    assert mocked_os_makedirs.called
    assert mocked_os_path_exists.called

    mocked_file_handler.reset_mock()
    mocked_os_makedirs.reset_mock()
    mocked_os_path_exists.reset_mock()

    mocked_os_path_exists.side_effect = FileNotFoundError
    cli.setup_logging('filename.yaml')
    assert mock.call().setLevel(INFO) in mocked_get_logger.mock_calls
    assert mocked_file_handler.called
    assert not mocked_os_makedirs.called
    assert not mocked_os_path_exists.called

    mocked_os_path_exists.return_value = True
    cli.setup_logging('filename.yaml', debug=True)
    assert mock.call().setLevel(DEBUG) in mocked_get_logger.mock_calls

    mocked_os_path_exists.return_value = True
    cli.setup_logging('filename.yaml', trace=True)
    assert mock.call().setLevel(LOGGING_TRACE_LEVEL_NUMBER) in mocked_get_logger.mock_calls


@mock.patch('cumin.cli.stderr')
@mock.patch('builtins.input')
@mock.patch('cumin.cli.sys.stdout.isatty')
@mock.patch('cumin.cli.logger')
def test_sigint_handler(logging, isatty, mocked_input, stderr):  # pylint: disable=unused-argument
    """Calling the SIGINT handler should raise KeyboardInterrupt or not based on tty and answer."""
    # Signal handler called without a tty
    isatty.return_value = False
    with pytest.raises(cli.KeyboardInterruptError):
        cli.sigint_handler(1, None)

    # Signal handler called with a tty
    isatty.return_value = True
    with pytest.raises(cli.KeyboardInterruptError):
        cli.sigint_handler(1, None)

    # # Signal handler called with a tty, answered 'y'
    # isatty.return_value = True
    # mocked_input.return_value = 'y'
    # with pytest.raises(cli.KeyboardInterruptError):
    #     cli.sigint_handler(1, None)
    #
    # # Signal handler called with a tty, answered 'n'
    # isatty.return_value = True
    # mocked_input.return_value = 'n'
    # assert cli.sigint_handler(1, None) is None
    #
    # # Signal handler called with a tty, answered 'invalid_answer'
    # isatty.return_value = True
    # mocked_input.return_value = 'invalid_answer'
    # with pytest.raises(cli.KeyboardInterruptError):
    #     cli.sigint_handler(1, None)
    #
    # # Signal handler called with a tty, empty answer
    # isatty.return_value = True
    # mocked_input.return_value = ''
    # with pytest.raises(cli.KeyboardInterruptError):
    #     cli.sigint_handler(1, None)


@mock.patch('cumin.cli.tqdm')
def test_stderr(tqdm):
    """Calling stderr() should call tqdm.write()."""
    cli.stderr('message')
    assert tqdm.write.called


@mock.patch('cumin.cli.stderr')
@mock.patch('builtins.input')
@mock.patch('cumin.cli.sys.stdout.isatty')
def test_get_hosts_ok(isatty, mocked_input, stderr):
    """Calling get_hosts() should query the backend and return the list of hosts."""
    args = cli.parse_args(['D{host1}', 'command1'])
    config = {'backend': 'direct'}
    isatty.return_value = True

    mocked_input.return_value = 'y'
    assert cli.get_hosts(args, config) == nodeset('host1')

    mocked_input.return_value = 'n'
    with pytest.raises(cli.KeyboardInterruptError):
        cli.get_hosts(args, config)

    mocked_input.return_value = 'invalid_answer'
    with pytest.raises(cli.KeyboardInterruptError):
        cli.get_hosts(args, config)

    mocked_input.return_value = ''
    with pytest.raises(cli.KeyboardInterruptError):
        cli.get_hosts(args, config)

    assert stderr.called


@mock.patch('cumin.cli.stderr')
@mock.patch('cumin.cli.sys.stdout.isatty')
def test_get_hosts_no_tty_ko(isatty, stderr):
    """Calling get_hosts() without a TTY should raise CuminError if --dry-run or --force are not specified."""
    args = cli.parse_args(['D{host1}', 'command1'])
    config = {'backend': 'direct'}
    isatty.return_value = False
    with pytest.raises(CuminError, match='Not in a TTY but neither DRY-RUN nor FORCE mode were specified'):
        cli.get_hosts(args, config)
    assert stderr.called


@mock.patch('cumin.cli.stderr')
@mock.patch('cumin.cli.sys.stdout.isatty')
def test_get_hosts_no_tty_dry_run(isatty, stderr):
    """Calling get_hosts() with or without a TTY with --dry-run should return an empty list."""
    args = cli.parse_args(['--dry-run', 'D{host1}', 'command1'])
    config = {'backend': 'direct'}
    assert cli.get_hosts(args, config) == []
    isatty.return_value = True
    assert cli.get_hosts(args, config) == []
    assert stderr.called


@mock.patch('cumin.cli.stderr')
@mock.patch('cumin.cli.sys.stdout.isatty')
def test_get_hosts_no_tty_force(isatty, stderr):
    """Calling get_hosts() with or without a TTY with --force should return the list of hosts."""
    args = cli.parse_args(['--force', 'D{host1}', 'command1'])
    config = {'backend': 'direct'}
    assert cli.get_hosts(args, config) == nodeset('host1')
    isatty.return_value = True
    assert cli.get_hosts(args, config) == nodeset('host1')
    assert stderr.called


@mock.patch('cumin.cli.cumin.transport.Transport')
@mock.patch('cumin.cli.stderr')
def test_run(stderr, transport):
    """Calling run() should query the hosts and execute the commands on the transport."""
    args = cli.parse_args(['--force', 'D{host1}', 'command1'])
    config = {'backend': 'direct', 'transport': 'clustershell'}
    cli.run(args, config)
    assert transport.new.call_args[0][0] is config
    assert isinstance(transport.new.call_args[0][1], transports.Target)
    assert stderr.called


def test_validate_config_valid():
    """A valid config should be validated without raising exception."""
    cli.validate_config({'log_file': '/var/log/cumin/cumin.log'})


def test_validate_config_invalid():
    """An invalid config should raise CuminError."""
    with pytest.raises(CuminError, match='Missing required parameter'):
        cli.validate_config({})
