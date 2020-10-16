"""Clustershell module integration tests."""
import os
import sys

from pathlib import Path

import cumin
from cumin import query, transport, transports
from cumin.transports.clustershell import NullReporter


# Expected block output for a single hostname command
_HOSTNAME_BLOCK_OUTPUT = """\x1b[34m===== NODE GROUP =====\x1b[39m
\x1b[36m(1) {hostname}\x1b[39m
\x1b[34m----- OUTPUT of 'hostname' -----\x1b[39m
{hostname}
"""


class TestClustershellTransport:
    """Clustershell transport class tests."""

    def setup_method(self, _):
        """Set default properties."""
        # pylint: disable=attribute-defined-outside-init
        self.identifier = os.getenv('CUMIN_IDENTIFIER')
        assert self.identifier is not None, 'Unable to find CUMIN_IDENTIFIER environmental variable'
        self.nodes_prefix = '{identifier}-'.format(identifier=self.identifier)
        self.all_nodes = '{prefix}[1-5]'.format(prefix=self.nodes_prefix)
        self.config = cumin.Config(config=Path(os.getenv('CUMIN_TMPDIR', '')) / 'config.yaml')
        self.hosts = query.Query(self.config).execute('D{{{nodes}}}'.format(nodes=self.all_nodes))
        self.target = transports.Target(self.hosts)
        self.worker = transport.Transport.new(self.config, self.target)
        self.worker.commands = ['hostname']

    def test_execute_tqdm_reporter(self, capsys):
        """It should execute the command on the target hosts and print to stdout the stdout/err of the command."""
        self.worker.handler = 'sync'
        exit_code = self.worker.execute()

        assert exit_code == 0
        for nodes, output in self.worker.get_results():
            assert str(nodes) == output.message().decode()

        out, err = capsys.readouterr()
        sys.stdout.write(out)
        sys.stderr.write(err)
        for host in self.hosts:
            assert _HOSTNAME_BLOCK_OUTPUT.format(hostname=host) in out

    def test_execute_null_reporter(self, capsys):
        """It should execute the command on the target hosts and not print to stdout the stdout/err of the command."""
        self.worker.handler = 'sync'
        self.worker.reporter = NullReporter
        exit_code = self.worker.execute()

        assert exit_code == 0
        for nodes, output in self.worker.get_results():
            assert str(nodes) == output.message().decode()

        out, err = capsys.readouterr()
        sys.stdout.write(out)
        sys.stderr.write(err)
        for host in self.hosts:
            assert _HOSTNAME_BLOCK_OUTPUT.format(hostname=host) not in out
