"""CLI integration tests."""
# pylint: disable=protected-access


import copy
import json
import os
import re
import sys

import pytest

from cumin import __version__, cli

# Set environment variables
_ENV = {'USER': 'root', 'SUDO_USER': 'user'}
for key, value in _ENV.items():
    os.environ[key] = value

# Dictionary with expected strings to match in the execution stderr:
# {label: string_to_match}
_EXPECTED_LINES = {
    'all_targeted': '5 hosts will be targeted',
    'failed': 'failed',
    'global_timeout': 'global timeout',
    'successfully': 'successfully',
    'dry_run': 'DRY-RUN mode enabled, aborting',
    'subfanout_targeted': '2 hosts will be targeted',
    'ls_success': "100.0% (5/5) success ratio (>= 100.0% threshold) for command: 'ls -la /tmp'.",
    'ls_success_threshold': "100.0% (5/5) success ratio (>= 50.0% threshold) for command: 'ls -la /tmp'.",
    'ls_partial_success': "/5) of nodes failed to execute command 'ls -la /tmp/maybe'",
    'ls_partial_success_ratio_re':
        r"[4-6]0\.0% \([2-3]/5\) success ratio \(< 100\.0% threshold\) for command: 'ls -la /tmp/maybe'\. Aborting.",
    'ls_partial_success_threshold_ratio':
        "60.0% (3/5) success ratio (>= 50.0% threshold) for command: 'ls -la /tmp/maybe'.",
    'ls_failure_batch': "40.0% (2/5) of nodes failed to execute command 'ls -la /tmp/non_existing'",
    'ls_failure_batch_threshold': "80.0% (4/5) of nodes failed to execute command 'ls -la /tmp/non_existing'",
    'ls_total_failure': "100.0% (5/5) of nodes failed to execute command 'ls -la /tmp/non_existing'",
    'ls_total_failure_threshold_ratio':
        "0.0% (0/5) success ratio (< 50.0% threshold) for command: 'ls -la /tmp/non_existing'. Aborting.",
    'date_success': "100.0% (5/5) success ratio (>= 100.0% threshold) for command: 'date'.",
    'date_success_subfanout': "100.0% (2/2) success ratio (>= 100.0% threshold) for command: 'date'.",
    'date_success_threshold': "100.0% (5/5) success ratio (>= 50.0% threshold) for command: 'date'.",
    'date_success_threshold_partial': "60.0% (3/5) success ratio (>= 50.0% threshold) for command: 'date'.",
    'all_success': '100.0% (5/5) success ratio (>= 100.0% threshold) of nodes successfully executed all commands.',
    'all_success_subfanout':
        '100.0% (2/2) success ratio (>= 100.0% threshold) of nodes successfully executed all commands.',
    'all_success_threshold':
        '100.0% (5/5) success ratio (>= 50.0% threshold) of nodes successfully executed all commands.',
    'all_failure':
        '0.0% (0/5) success ratio (< 100.0% threshold) of nodes successfully executed all commands. Aborting.',
    'all_failure_threshold':
        '0.0% (0/5) success ratio (< 50.0% threshold) of nodes successfully executed all commands. Aborting.',
    'global_timeout_executing_re': (r'([2-6]|)0\.0% \([0-3]/5\) of nodes were executing a command when the global '
                                    r'timeout occurred'),
    'global_timeout_executing_threshold_re':
        r'([2-6]|)0\.0% \([0-3]/5\) of nodes were executing a command when the global timeout occurred',
    'global_timeout_pending_re': (r'([2-6]|)0\.0% \([0-3]/5\) of nodes were pending execution when the global timeout '
                                  r'occurred'),
    'global_timeout_pending_threshold_re':
        r'([2-6]|)0\.0% \([0-3]/5\) of nodes were pending execution when the global timeout occurred',
    'sleep_total_failure': "0.0% (0/5) success ratio (< 100.0% threshold) for command: 'sleep 2'. Aborting.",
    'sleep_success': "100.0% (5/5) success ratio (>= 100.0% threshold) for command: 'sleep 0.5'.",
    'sleep_success_threshold': "100.0% (5/5) success ratio (>= 50.0% threshold) for command: 'sleep 0.5'.",
    'sleep_timeout': "100.0% (5/5) of nodes timeout to execute command 'sleep 2'",
    'sleep_timeout_threshold_re': r"[4-8]0\.0% \([2-4]/5\) of nodes timeout to execute command 'sleep 2'",
    'sync': {
        'ls_total_failure_ratio':
            "0.0% (0/5) success ratio (< 100.0% threshold) for command: 'ls -la /tmp/non_existing'. Aborting.",
    },
    'async': {
        'ls_total_failure_ratio':
            "0.0% (0/5) success ratio (< 100.0% threshold). Aborting.",
    },
}

# Tuple of dictionaries with commands to execute for each variant parameters, with the following fields:
# rc: expected return code
# commands: list of commands to execute
# assert_true: list of labels of strings to match with assertTrue() against stderr. [optional]
# assert_false: list of labels of strings to match with assertFalse() against stderr. [optional]
# additional_params: list of additional parameters to pass to the CLI. [optional]
_VARIANTS_COMMANDS = (
    {'rc': 0, 'commands': ['ls -la /tmp', 'date'], 'assert_true': ['all_success'],
     'assert_false': ['failed', 'global_timeout']},
    {'rc': None, 'commands': ['ls -la /tmp/maybe', 'date']},
    {'rc': 2, 'commands': ['ls -la /tmp/non_existing', 'date'], 'assert_true': ['all_failure'],
     'assert_false': ['global_timeout']},
    {'rc': 0, 'commands': ['date', 'date', 'date'], 'assert_true': ['all_success'],
     'assert_false': ['failed', 'global_timeout']},
    {'rc': 2, 'additional_params': ['--global-timeout', '1'], 'commands': ['date', 'sleep 2']},
    {'rc': None, 'additional_params': ['--global-timeout', '1'], 'commands': ['sleep 0.99', 'date']},
    {'rc': 2, 'additional_params': ['-t', '1'], 'commands': ['sleep 2', 'date'],
     'assert_false': ['failed', 'global_timeout', 'date_success']},
    {'rc': 0, 'additional_params': ['-t', '2'], 'commands': ['sleep 0.5', 'date'],
     'assert_false': ['failed', 'global_timeout']},
)

# Tuple of lists of additional parameters to pass to the CLI.
_VARIANTS_PARAMETERS = (
    ['-m', 'sync'],
    ['-m', 'sync', '--batch-size', '2'],
    ['-m', 'sync', '--batch-size', '2', '--batch-sleep', '1.0'],
    ['-m', 'sync', '-p', '50'],
    ['-m', 'sync', '-p', '50', '--batch-size', '2'],
    ['-m', 'sync', '-p', '50', '--batch-size', '2', '--batch-sleep', '1.0'],
    ['-m', 'async'],
    ['-m', 'async', '--batch-size', '2'],
    ['-m', 'async', '--batch-size', '2', '--batch-sleep', '1.0'],
    ['-m', 'async', '-p', '50'],
    ['-m', 'async', '-p', '50', '--batch-size', '2'],
    ['-m', 'async', '-p', '50', '--batch-size', '2', '--batch-sleep', '1.0'],
)

# Expected output for the -o/--out txt option for one node
_TXT_EXPECTED_SINGLE_OUTPUT = """{prefix}{node_id}: First
{prefix}{node_id}: Second
{prefix}{node_id}: Third"""

# Expected output for the -o/--out json option for one node
_JSON_EXPECTED_SINGLE_OUTPUT = 'First\nSecond\nThird'


def make_method(name, commands_set):
    """Method generator with a dynamic name and docstring."""
    params = copy.deepcopy(commands_set)  # Needed to have a different one for each method

    @pytest.mark.variant_params(params)
    def test_variant(self, capsys):
        """Test variant generated function"""
        argv = self.default_params + params['params'] + [self.all_nodes] + params['commands']
        rc = cli.main(argv=argv)
        out, err = capsys.readouterr()
        sys.stdout.write(out)
        sys.stderr.write(err)

        if params['rc'] is None:
            params['rc'] = get_rc(params)

        assert rc == params['rc']
        assert _EXPECTED_LINES['all_targeted'] in err, _EXPECTED_LINES['all_targeted']

        labels = params.get('assert_true', [])
        labels += get_global_timeout_expected_lines(params)

        if 'async' in params['params']:
            mode = 'async'
        else:
            mode = 'sync'
            labels += (get_ls_expected_lines(params) + get_date_expected_lines(params) +
                       get_timeout_expected_lines(params))

        for label in labels:
            if label in ('all_success', 'all_failure') and '-p' in params['params']:
                label = '{label}_threshold'.format(label=label)

            if label in _EXPECTED_LINES[mode]:
                string = _EXPECTED_LINES[mode][label]
            else:
                string = _EXPECTED_LINES[label]

            if label.endswith('_re'):
                assert re.search(string, err) is not None, string
            else:
                assert string in err, string

        for label in params.get('assert_false', []):
            assert _EXPECTED_LINES[label] not in err, _EXPECTED_LINES[label]

    # Dynamically set the name and docstring of the generated function to distinguish them
    test_variant.__name__ = 'test_variant_{name}'.format(name=name)
    test_variant.__doc__ = 'variant_function called with params: {params}'.format(params=params)

    return test_variant


def add_variants_methods(indexes):
    """Decorator to add generated tests to a TestClass subclass."""
    def func_wrapper(cls):
        """Dynamic test generator."""
        for i in indexes:
            for j, commands_set in enumerate(_VARIANTS_COMMANDS):
                commands_set['params'] = _VARIANTS_PARAMETERS[i] + commands_set.get('additional_params', [])
                test_input = make_method('params{i:02d}_commands{j:02d}'.format(i=i, j=j), commands_set)
                if test_input.__doc__ is None:
                    raise AssertionError("Missing __doc__ for test {name}".format(name=test_input.__name__))
                setattr(cls, test_input.__name__, test_input)
        return cls

    return func_wrapper


def get_rc(params):
    """Return the expected return code based on the parameters.

    Arguments:
        params: a dictionary with all the parameters passed to the variant_function
    """
    return_value = 2
    if '-p' in params['params'] and '--global-timeout' not in params['params']:
        return_value = 1

    return return_value


def get_global_timeout_expected_lines(params):  # pylint: disable=invalid-name
    """Return a list of expected lines labels for global timeout-based tests.

    Arguments:
        params: a dictionary with all the parameters passed to the variant_function
    """
    expected = []
    if '--global-timeout' not in params['params']:
        return expected

    if '-p' in params['params']:
        expected = ['global_timeout_executing_threshold_re', 'global_timeout_pending_threshold_re']
    else:
        expected = ['global_timeout_executing_re', 'global_timeout_pending_re']

    return expected


def get_timeout_expected_lines(params):
    """Return a list of expected lines labels for timeout-based tests.

    Arguments:
        params: a dictionary with all the parameters passed to the variant_function
    """
    expected = []
    if '-t' not in params['params']:
        return expected

    if params['rc'] == 0:
        # Test successful cases
        if '-p' in params['params']:
            expected = ['sleep_success_threshold', 'date_success_threshold']
        else:
            expected = ['date_success', 'sleep_success']
    else:
        # Test timeout cases
        if '--batch-size' in params['params']:
            expected = ['sleep_timeout_threshold_re']
        else:
            expected = ['sleep_timeout']

    return expected


def get_date_expected_lines(params):
    """Return a list of expected lines labels for the date command based on parameters.

    Arguments:
        params: a dictionary with all the parameters passed to the variant_function
    """
    expected = []
    if 'ls -la /tmp/non_existing' in params['commands']:
        return expected

    if '-p' in params['params']:
        if 'ls -la /tmp/maybe' in params['commands']:
            expected = ['date_success_threshold_partial']
        elif 'ls -la /tmp' in params['commands']:
            expected = ['date_success_threshold']
    elif 'ls -la /tmp' in params['commands']:
        expected = ['date_success']

    return expected


def get_ls_expected_lines(params):
    """Return a list of expected lines labels for the ls command based on the parameters.

    Arguments:
        params: a dictionary with all the parameters passed to the variant_function
    """
    expected = []
    if 'ls -la /tmp' in params['commands']:
        if '-p' in params['params']:
            expected = ['ls_success_threshold']
        else:
            expected = ['ls_success']
    elif 'ls -la /tmp/maybe' in params['commands']:
        if '-p' in params['params']:
            expected = ['ls_partial_success', 'ls_partial_success_threshold_ratio']
        else:
            expected = ['ls_partial_success', 'ls_partial_success_ratio_re']
    elif 'ls -la /tmp/non_existing' in params['commands']:
        if '--batch-size' in params['params']:
            if '-p' in params['params']:
                expected.append('ls_failure_batch_threshold')
            else:
                expected.append('ls_failure_batch')
        else:
            expected.append('ls_total_failure')

        if '-p' in params['params']:
            expected.append('ls_total_failure_threshold_ratio')
        else:
            expected.append('ls_total_failure_ratio')

    return expected


@add_variants_methods(range(len(_VARIANTS_PARAMETERS)))
class TestCLI(object):
    """CLI module tests."""

    def setup_method(self, _):
        """Set default properties."""
        # pylint: disable=attribute-defined-outside-init
        self.identifier = os.getenv('CUMIN_IDENTIFIER')
        assert self.identifier is not None, 'Unable to find CUMIN_IDENTIFIER environmental variable'
        self.config = os.path.join(os.getenv('CUMIN_TMPDIR', ''), 'config.yaml')
        self.default_params = ['--force', '-d', '-c', self.config]
        self.nodes_prefix = '{identifier}-'.format(identifier=self.identifier)
        self.all_nodes = '{prefix}[1-5]'.format(prefix=self.nodes_prefix)

    def _get_nodes(self, nodes):
        """Return the query for the nodes selection.

        Arguments:
            nodes: a string with the NodeSet nodes selection
        """
        if nodes is None:
            return self.all_nodes

        return '{prefix}[{nodes}]'.format(prefix=self.nodes_prefix, nodes=nodes)

    def test_single_command_subfanout(self, capsys):
        """Executing one command on a subset of nodes smaller than the ClusterShell fanout."""
        params = [self._get_nodes('1-2'), 'date']
        rc = cli.main(argv=self.default_params + params)
        out, err = capsys.readouterr()
        sys.stdout.write(out)
        sys.stderr.write(err)
        assert _EXPECTED_LINES['subfanout_targeted'] in err, _EXPECTED_LINES['subfanout_targeted']
        assert _EXPECTED_LINES['date_success_subfanout'] in err, _EXPECTED_LINES['date_success_subfanout']
        assert _EXPECTED_LINES['all_success_subfanout'] in err, _EXPECTED_LINES['all_success_subfanout']
        assert _EXPECTED_LINES['failed'] not in err, _EXPECTED_LINES['failed']
        assert _EXPECTED_LINES['global_timeout'] not in err, _EXPECTED_LINES['global_timeout']
        assert rc == 0

    def test_single_command_supfanout(self, capsys):
        """Executing one command on a subset of nodes greater than the ClusterShell fanout."""
        params = [self.all_nodes, 'date']
        rc = cli.main(argv=self.default_params + params)
        out, err = capsys.readouterr()
        sys.stdout.write(out)
        sys.stderr.write(err)
        assert _EXPECTED_LINES['all_targeted'] in err, _EXPECTED_LINES['all_targeted']
        assert _EXPECTED_LINES['date_success'] in err, _EXPECTED_LINES['date_success']
        assert _EXPECTED_LINES['all_success'] in err, _EXPECTED_LINES['all_success']
        assert _EXPECTED_LINES['failed'] not in err, _EXPECTED_LINES['failed']
        assert _EXPECTED_LINES['global_timeout'] not in err, _EXPECTED_LINES['global_timeout']
        assert rc == 0

    def test_dry_run(self, capsys):
        """With --dry-run only the matching hosts are printed."""
        params = ['--dry-run', self.all_nodes, 'date']
        rc = cli.main(argv=self.default_params + params)
        out, err = capsys.readouterr()
        sys.stdout.write(out)
        sys.stderr.write(err)
        assert _EXPECTED_LINES['all_targeted'] in err, _EXPECTED_LINES['all_targeted']
        assert _EXPECTED_LINES['dry_run'] in err, _EXPECTED_LINES['dry_run']
        assert _EXPECTED_LINES['successfully'] not in err, _EXPECTED_LINES['successfully']
        assert _EXPECTED_LINES['failed'] not in err, _EXPECTED_LINES['failed']
        assert _EXPECTED_LINES['global_timeout'] not in err, _EXPECTED_LINES['global_timeout']
        assert rc == 0

    def test_timeout(self, capsys):
        """With a timeout shorter than a command it should fail."""
        params = ['--global-timeout', '1', self.all_nodes, 'sleep 2']
        rc = cli.main(argv=self.default_params + params)
        out, err = capsys.readouterr()
        sys.stdout.write(out)
        sys.stderr.write(err)
        assert _EXPECTED_LINES['all_targeted'] in err, _EXPECTED_LINES['all_targeted']
        assert re.search(_EXPECTED_LINES['global_timeout_executing_re'], err) is not None, \
            _EXPECTED_LINES['global_timeout_executing_re']
        assert re.search(_EXPECTED_LINES['global_timeout_pending_re'], err) is not None, \
            _EXPECTED_LINES['global_timeout_pending_re']
        assert _EXPECTED_LINES['sleep_total_failure'] in err, _EXPECTED_LINES['sleep_total_failure']
        assert _EXPECTED_LINES['all_failure'] in err, _EXPECTED_LINES['all_failure']
        assert _EXPECTED_LINES['failed'] not in err, _EXPECTED_LINES['failed']
        assert rc == 2

    def test_version(self, capsys):  # pylint: disable=no-self-use
        """Calling --version should return the version and exit."""
        with pytest.raises(SystemExit) as e:
            cli.main(argv=['--version'])

        out, err = capsys.readouterr()
        sys.stdout.write(out)
        sys.stderr.write(err)
        assert e.type == SystemExit
        assert e.value.code == 0
        assert err == ''
        assert len(out.splitlines()) == 1
        assert __version__ in out

    def test_out_txt(self, capsys):
        """The -o/--out txt option should print the output expanded for each host, prefixed by the hostname."""
        params = ['-o', 'txt', self.all_nodes, 'cat /tmp/out']
        rc = cli.main(argv=self.default_params + params)
        out, err = capsys.readouterr()
        sys.stdout.write(out)
        sys.stderr.write(err)

        assert _EXPECTED_LINES['all_targeted'] in err, _EXPECTED_LINES['all_targeted']
        assert _EXPECTED_LINES['successfully'] in err, _EXPECTED_LINES['successfully']
        assert _EXPECTED_LINES['failed'] not in err, _EXPECTED_LINES['failed']
        assert rc == 0

        expected_out = '\n'.join(
            _TXT_EXPECTED_SINGLE_OUTPUT.format(prefix=self.nodes_prefix, node_id=i) for i in range(1, 6))

        assert out.split(cli.OUTPUT_SEPARATOR + '\n')[1] == expected_out + '\n'

    def test_out_json(self, capsys):
        """The -o/--out json option should print a JSON with hostnames as keys and output as values."""
        params = ['-o', 'json', self.all_nodes, 'cat /tmp/out']
        rc = cli.main(argv=self.default_params + params)
        out, err = capsys.readouterr()
        sys.stdout.write(out)
        sys.stderr.write(err)

        assert _EXPECTED_LINES['all_targeted'] in err, _EXPECTED_LINES['all_targeted']
        assert _EXPECTED_LINES['successfully'] in err, _EXPECTED_LINES['successfully']
        assert _EXPECTED_LINES['failed'] not in err, _EXPECTED_LINES['failed']
        assert rc == 0

        expected_out = {self.nodes_prefix + str(i): _JSON_EXPECTED_SINGLE_OUTPUT for i in range(1, 6)}

        assert json.loads(out.split(cli.OUTPUT_SEPARATOR + '\n')[1]) == expected_out
