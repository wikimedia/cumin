"""CLI output comparison tests between versions.

Refer to the related paragraph in the Development page of the documentation for the instructions on how to run them.
"""
# pylint: disable=too-many-arguments
import os
import shlex
from subprocess import run

import pytest


@pytest.fixture(name='run_cumin')
def fixture_run_cumin(request):
    """Run cumin with the given additional arguments, query and commands and validate the expected return code."""
    identifier = os.getenv('CUMIN_IDENTIFIER')
    if not identifier:
        raise RuntimeError('Missing CUMIN_IDENTIFIER from current environment')

    progress = bool(os.getenv('CUMIN_PROGRESS_BARS'))

    # The _comment variable is used for the sole purpose to have pytest add a human-friendly name next to each test
    # to easily identify and understand them.
    def runner(_comment, args, query, commands, retcode):
        """Inner function to be returned by the fixture."""
        run_args = ['cumin', '-c', 'config.yaml', '--force']
        if not progress:
            run_args.append('--no-progress')
        run_args += args
        run_args.append(f'{identifier}-{query}')
        run_args += commands

        print(f'\033[37;45m### {request.node.name}\033[0m', flush=True)
        print(f'\033[37;45m### {shlex.join(run_args)}\033[0m', flush=True)
        ret = run(run_args, check=False)  # nosec
        assert ret.returncode == retcode

    return runner


@pytest.mark.parametrize('batch_args', ([], ['-b', '2'], ['-b', '2', '-s', '1'], ['-b', '2', '-p', '50']))
@pytest.mark.parametrize('query', ('1', '[1-5]'))
@pytest.mark.parametrize('comment, commands, retcode', (
    ('successful', ['ls -l /tmp'], 0),
    ('failure', ['ls -l /tmp/invalid'], 2),
))
def test_single_command_basic(run_cumin, comment, commands, retcode, query, batch_args):
    """It should run a single command with cumin in the simple case of total success/failure with various arguments."""
    run_cumin(comment, batch_args, query, commands, retcode)


@pytest.mark.parametrize('batch_args', ([], ['-b', '2'], ['-b', '2', '-s', '1'], ['-b', '2', '-p', '50']))
@pytest.mark.parametrize('comment, args, commands, retcode', (
    ('no output success', ['-t', '4'], ['sleep 1'], 0),
    ('partial success', [], ['ls -l /tmp/maybe'], 2),
    ('partial timeout', ['-t', '2'], ['h=$(hostname); sleep ${h: -1}'], 2),
    ('partial success and partial timeout', ['-t', '4'], ['h=$(hostname); sleep ${h: -1}; ls /tmp/maybe'], 2),
    ('all timeout', ['-t', '1'], ['sleep 2'], 2),
))
def test_single_command_complex(run_cumin, comment, args, commands, retcode, batch_args):
    """It should run a single command with cumin with various arguments."""
    if comment == 'partial success' and batch_args and batch_args[-1] == '50':
        retcode = 1
    run_cumin(comment, args + batch_args, '[1-5]', commands, retcode)


@pytest.mark.parametrize('comment, args, commands, retcode', (
    ('failure', [], ['ls -l /tmp/invalid'], 2),
    ('no output success', ['-t', '4'], ['sleep 1'], 0),
    ('partial success, success percentage reached', [], ['ls -l /tmp/maybe'], 2),
    ('partial timeout', ['-t', '2'], ['h=$(hostname); sleep ${h: -1}'], 2),
    ('partial success and partial timeout, success percentage reached',
     ['-t', '4'], ['h=$(hostname); sleep ${h: -1}; ls /tmp/maybe'], 2),
    ('all timeout', ['-t', '1'], ['sleep 2'], 2),
))
def test_single_command_success_percentage(run_cumin, comment, args, commands, retcode):
    """It should run a single command with cumin with various arguments related to success percentage."""
    run_cumin(comment, ['-b', '2', '-p', '70'] + args, '[1-5]', commands, retcode)


@pytest.mark.parametrize('mode_args', (['-m', 'sync'], ['-m', 'async']))
@pytest.mark.parametrize('batch_args', ([], ['-b', '2'], ['-b', '2', '-s', '1'], ['-b', '2', '-p', '50']))
@pytest.mark.parametrize('query', ('1', '[1-5]'))
@pytest.mark.parametrize('comment, commands, retcode', (
    ('successful', ['ls -l /tmp', 'hostname', 'cat /tmp/out'], 0),
    ('failure', ['ls -l /tmp/invalid'], 2),
))
def test_multi_commands_basic(run_cumin, comment, commands, retcode, query, batch_args, mode_args):
    """It should run multiple commands with cumin in the simple case of total success/failure with various arguments."""
    run_cumin(comment, batch_args + mode_args, query, commands, retcode)


@pytest.mark.parametrize('mode_args', (['-m', 'sync'], ['-m', 'async']))
@pytest.mark.parametrize('batch_args', ([], ['-b', '2'], ['-b', '2', '-s', '1'], ['-b', '2', '-p', '50']))
@pytest.mark.parametrize('comment, args, commands, retcode', (
    ('no output command 2 success', [], ['cat /tmp/out', 'sleep 1', 'hostname'], 0),
    ('command 1 all failed', [], ['ls -l /tmp/invalid', 'hostname', 'date'], 2),
    ('command 3 all failed', [], ['ls -l /tmp', 'hostname', 'ls -l /tmp/invalid'], 2),
    ('partial success command 2', [], ['ls -l /tmp', 'ls -l /tmp/maybe', 'cat /tmp/out'], 2),
    ('partial success command 3', [], ['ls -l /tmp', 'hostname', 'ls -l /tmp/maybe'], 2),
    ('partial timeout command 2', ['-t', '2'], ['ls -l /tmp', 'h=$(hostname); sleep ${h: -1}', 'hostname'], 2),
    ('partial timeout command 3', ['-t', '4'], ['ls -l /tmp', 'hostname', 'h=$(hostname); sleep ${h: -1}'], 2),
    ('partial success and partial timeout command 1', ['-t', '2'],
     ['h=$(hostname); sleep ${h: -1}; ls -l /tmp/maybe', 'hostname', 'cat /tmp/out'], 2),
    ('partial success and partial timeout command 3', ['-t', '2'],
     ['hostname', 'cat /tmp/out', 'h=$(hostname); sleep ${h: -1}; ls -l /tmp/maybe'], 2),
    ('command 2 all timeout', ['-t', '1'], ['cat /tmp/out', 'sleep 2', 'date'], 2),
))
def test_multi_commands_complex(run_cumin, comment, args, commands, retcode, batch_args, mode_args):
    """It should run multiple commands with cumin with various arguments."""
    if ((comment.startswith('partial success command') or comment == 'partial timeout command 3')
            and batch_args and batch_args[-1] == '50'):
        retcode = 1
    run_cumin(comment, args + batch_args + mode_args, '[1-5]', commands, retcode)


@pytest.mark.parametrize('mode_args', (['-m', 'sync'], ['-m', 'async']))
@pytest.mark.parametrize('comment, args, commands, retcode', (
    ('partial success command 3, success percentage reached', [], ['ls -l /tmp', 'hostname', 'ls -l /tmp/maybe'], 2),
    ('partial success and partial timeout command 1, success percentage reached',
     ['-t', '2'], ['h=$(hostname); sleep ${h: -1}; ls -l /tmp/maybe', 'hostname', 'cat /tmp/out'], 2),
    ('partial success and partial timeout command 3, success percentage reached',
     ['-t', '2'], ['hostname', 'cat /tmp/out', 'h=$(hostname); sleep ${h: -1}; ls -l /tmp/maybe'], 2),
))
def test_multi_commands_success_percentage(run_cumin, comment, args, commands, retcode, mode_args):
    """It should run a single command with cumin with various arguments related to success percentage."""
    run_cumin(comment, ['-b', '2', '-p', '70'] + args + mode_args, '[1-5]', commands, retcode)
