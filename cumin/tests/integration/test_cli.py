"""CLI tests."""
from __future__ import print_function

import copy
import os
import re
import sys
import unittest

from functools import wraps
from StringIO import StringIO

from cumin import cli

# Set environment variables
_ENV = {'USER': 'root', 'SUDO_USER': 'user'}
for key, value in _ENV.iteritems():
    os.environ[key] = value

# Dictionary with expected strings to match in the execution stderr:
# {label: string_to_match}
_EXPECTED_LINES = {
    'all_targeted': '5 hosts will be targeted',
    'failed': 'failed',
    'timeout': 'timeout',
    'successfully': 'successfully',
    'dry_run': 'DRY-RUN mode enabled, aborting',
    'subfanout_targeted': '2 hosts will be targeted',
    'ls_success': "100.0% (5/5) success ratio (>= 100.0% threshold) for command: 'ls -la /tmp'.",
    'ls_success_threshold': "100.0% (5/5) success ratio (>= 50.0% threshold) for command: 'ls -la /tmp'.",
    'ls_partial_success': "/5) of nodes failed to execute command 'ls -la /tmp/maybe'",
    'ls_partial_success_ratio_re':
        r"[4-6]0.0% \([2-3]/5\) success ratio \(< 100.0% threshold\) for command: 'ls -la /tmp/maybe'. Aborting.",
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
    'timeout_executing_re': r'([2-6]|)0.0% \([0-3]/5\) of nodes were executing a command when the timeout occurred',
    'timeout_executing_threshold_re':
        r'([2-6]|)0.0% \([0-3]/5\) of nodes were executing a command when the timeout occurred',
    'timeout_pending_re': r'([2-6]|)0.0% \([0-3]/5\) of nodes were pending execution when the timeout occurred',
    'timeout_pending_threshold_re':
        r'([2-6]|)0.0% \([0-3]/5\) of nodes were pending execution when the timeout occurred',
    'sleep_total_failure': "0.0% (0/5) success ratio (< 100.0% threshold) for command: 'sleep 2'. Aborting.",
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
     'assert_false': ['failed', 'timeout']},
    {'rc': None, 'commands': ['ls -la /tmp/maybe', 'date']},
    {'rc': 2, 'commands': ['ls -la /tmp/non_existing', 'date'], 'assert_true': ['all_failure'],
     'assert_false': ['timeout']},
    {'rc': 0, 'commands': ['date', 'date', 'date'], 'assert_true': ['all_success'],
     'assert_false': ['failed', 'timeout']},
    {'rc': 2, 'additional_params': ['-t', '1'], 'commands': ['date', 'sleep 2']},
    {'rc': None, 'additional_params': ['-t', '1'], 'commands': ['sleep 0.99', 'date']},
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


def capture_output(func):
    """Decorator to capture stdout and stderr of a test run and pass it to the test method.

    Arguments
    func -- the function to be decorated
    """
    @wraps(func)
    def func_wrapper(self, *args, **kwargs):
        """The actual sdtout/stderr capturer.

        Arguments
        self -- the 'self' of the decorated method.
        """
        try:
            stdout = sys.stdout
            stderr = sys.stderr
            out = StringIO()
            err = StringIO()
            sys.stdout = out
            sys.stderr = err
            args += (out, err)
            func(self, *args, **kwargs)
        except AssertionError:
            # Print both stderr and stdout to the original stdout captured by nose
            print(err.getvalue(), file=stdout)
            print(out.getvalue(), file=stdout)
            raise
        finally:
            # Restore original stdout/stderr
            sys.stdout = stdout
            sys.stderr = stderr

    return func_wrapper


def make_method(name, commands_set):
    """Method generator with a dynamic name and docstring."""
    params = copy.deepcopy(commands_set)  # Needed to have a different one for each method

    @capture_output
    def test_variant(self, stdout, stderr):
        """Test variant generated function"""
        argv = self.default_params + params['params'] + [self.all_nodes] + params['commands']
        rc = cli.main(argv=argv)
        err = stderr.getvalue()

        if params['rc'] is None:
            params['rc'] = self._get_rc(params)

        self.assertEqual(rc, params['rc'])
        self.assertIn(_EXPECTED_LINES['all_targeted'], err, msg=_EXPECTED_LINES['all_targeted'])

        labels = params.get('assert_true', [])
        labels += self._get_timeout_expected_lines(params)

        if 'async' in params['params']:
            mode = 'async'
        else:
            mode = 'sync'
            labels += self._get_ls_expected_lines(params) + self._get_date_expected_lines(params)

        for label in labels:
            if label in ('all_success', 'all_failure') and '-p' in params['params']:
                label = '{label}_threshold'.format(label=label)

            if label in _EXPECTED_LINES[mode]:
                string = _EXPECTED_LINES[mode][label]
            else:
                string = _EXPECTED_LINES[label]

            if label.endswith('_re'):
                self.assertIsNotNone(re.search(string, err), msg=string)
            else:
                self.assertIn(string, err, msg=string)

        for label in params.get('assert_false', []):
            self.assertNotIn(_EXPECTED_LINES[label], err, msg=_EXPECTED_LINES[label])

    # Dynamically set the name and docstring of the generated function to distinguish them
    test_variant.__name__ = 'test_variant_{name}'.format(name=name)
    test_variant.__doc__ = 'variant_function called with params: {params}'.format(params=params)

    return test_variant


def add_variants_methods(indexes):
    """Decorator to add generated tests to a TestClass subclass."""
    def func_wrapper(cls):
        for i in indexes:
            for j, commands_set in enumerate(_VARIANTS_COMMANDS):
                commands_set['params'] = _VARIANTS_PARAMETERS[i] + commands_set.get('additional_params', [])
                test_input = make_method('params{i:02d}_commands{j:02d}'.format(i=i, j=j), commands_set)
                setattr(cls, test_input.__name__, test_input)
        return cls

    return func_wrapper


@add_variants_methods(xrange(len(_VARIANTS_PARAMETERS)))
class TestCLI(unittest.TestCase):
    """CLI module tests."""

    _multiprocess_can_split_ = True

    def setUp(self):
        """Set default properties."""
        self.identifier = os.environ.get('CUMIN_IDENTIFIER')
        self.config = os.path.join(os.environ.get('CUMIN_TMPDIR'), 'config.yaml')
        self.default_params = ['--force', '-d', '-c', self.config]
        self.nodes_prefix = '{identifier}-'.format(identifier=self.identifier)
        self.all_nodes = '{prefix}[1-5]'.format(prefix=self.nodes_prefix)

    def _get_nodes(self, nodes):
        """Return the query for the nodes selection.

        Arguments:
        nodes - a string with the ClusterShell NodeSet nodes selection
        """
        if nodes is None:
            return self.all_nodes
        else:
            return '{prefix}[{nodes}]'.format(prefix=self.nodes_prefix, nodes=nodes)

    def _get_rc(self, params):
        """Return the expected return code based on the parameters.

        Arguments:
        params -- a dictionary with all the parameters passed to the variant_function
        """
        return_value = 2
        if '-p' in params['params'] and '-t' not in params['params']:
            return_value = 1

        return return_value

    def _get_timeout_expected_lines(self, params):
        """Return a list of expected lines labels for timeout-based tests.

        Arguments:
        params -- a dictionary with all the parameters passed to the variant_function
        """
        expected = []
        if '-t' not in params['params']:
            return expected

        if '-p' in params['params']:
            expected = ['timeout_executing_threshold_re', 'timeout_pending_threshold_re']
        else:
            expected = ['timeout_executing_re', 'timeout_pending_re']

        return expected

    def _get_date_expected_lines(self, params):
        """Return a list of expected lines labels for the date command based on parameters.

        Arguments:
        params -- a dictionary with all the parameters passed to the variant_function
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

    def _get_ls_expected_lines(self, params):
        """Return a list of expected lines labels for the ls command based on the parameters.

        Arguments:
        params -- a dictionary with all the parameters passed to the variant_function
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

    @capture_output
    def test_single_command_subfanout(self, stdout, stderr):
        """Executing one command on a subset of nodes smaller than the ClusterShell fanout."""
        params = [self._get_nodes('1-2'), 'date']
        rc = cli.main(argv=self.default_params + params)
        err = stderr.getvalue()
        self.assertIn(_EXPECTED_LINES['subfanout_targeted'], err, msg=_EXPECTED_LINES['subfanout_targeted'])
        self.assertIn(_EXPECTED_LINES['date_success_subfanout'], err, msg=_EXPECTED_LINES['date_success_subfanout'])
        self.assertIn(_EXPECTED_LINES['all_success_subfanout'], err, msg=_EXPECTED_LINES['all_success_subfanout'])
        self.assertNotIn(_EXPECTED_LINES['failed'], err, msg=_EXPECTED_LINES['failed'])
        self.assertNotIn(_EXPECTED_LINES['timeout'], err, msg=_EXPECTED_LINES['timeout'])
        self.assertEqual(rc, 0)

    @capture_output
    def test_single_command_supfanout(self, stdout, stderr):
        """Executing one command on a subset of nodes greater than the ClusterShell fanout."""
        params = [self.all_nodes, 'date']
        rc = cli.main(argv=self.default_params + params)
        err = stderr.getvalue()
        self.assertIn(_EXPECTED_LINES['all_targeted'], err, msg=_EXPECTED_LINES['all_targeted'])
        self.assertIn(_EXPECTED_LINES['date_success'], err, msg=_EXPECTED_LINES['date_success'])
        self.assertIn(_EXPECTED_LINES['all_success'], err, msg=_EXPECTED_LINES['all_success'])
        self.assertNotIn(_EXPECTED_LINES['failed'], err, msg=_EXPECTED_LINES['failed'])
        self.assertNotIn(_EXPECTED_LINES['timeout'], err, msg=_EXPECTED_LINES['timeout'])
        self.assertEqual(rc, 0)

    @capture_output
    def test_dry_run(self, stdout, stderr):
        """With --dry-run only the matching hosts are printed."""
        params = ['--dry-run', self.all_nodes, 'date']
        rc = cli.main(argv=self.default_params + params)
        err = stderr.getvalue()
        self.assertIn(_EXPECTED_LINES['all_targeted'], err, msg=_EXPECTED_LINES['all_targeted'])
        self.assertIn(_EXPECTED_LINES['dry_run'], err, msg=_EXPECTED_LINES['dry_run'])
        self.assertNotIn(_EXPECTED_LINES['successfully'], err, msg=_EXPECTED_LINES['successfully'])
        self.assertNotIn(_EXPECTED_LINES['failed'], err, msg=_EXPECTED_LINES['failed'])
        self.assertNotIn(_EXPECTED_LINES['timeout'], err, msg=_EXPECTED_LINES['timeout'])
        self.assertEqual(rc, 0)

    @capture_output
    def test_timeout(self, stdout, stderr):
        """With a timeout shorter than a command it should fail."""
        params = ['-t', '1', self.all_nodes, 'sleep 2']
        rc = cli.main(argv=self.default_params + params)
        err = stderr.getvalue()
        self.assertIn(_EXPECTED_LINES['all_targeted'], err, msg=_EXPECTED_LINES['all_targeted'])
        self.assertIsNotNone(
            re.search(_EXPECTED_LINES['timeout_executing_re'], err), msg=_EXPECTED_LINES['timeout_executing_re'])
        self.assertIsNotNone(
            re.search(_EXPECTED_LINES['timeout_pending_re'], err), msg=_EXPECTED_LINES['timeout_pending_re'])
        self.assertIn(_EXPECTED_LINES['sleep_total_failure'], err, msg=_EXPECTED_LINES['sleep_total_failure'])
        self.assertIn(_EXPECTED_LINES['all_failure'], err, msg=_EXPECTED_LINES['all_failure'])
        self.assertNotIn(_EXPECTED_LINES['failed'], err, msg=_EXPECTED_LINES['failed'])
        self.assertEqual(rc, 2)
