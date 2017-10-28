"""Known hosts backend tests."""
import os

import pytest

from ClusterShell.NodeSet import NodeSet, RESOLVER_NOGROUP

from cumin.backends import BaseQuery
from cumin.backends.knownhosts import KnownHostsLineError, KnownHostsQuery, KnownHostsSkippedLineError, query_class
from cumin.tests import get_fixture_path


def test_knownhosts_query_class():
    """An instance of query_class should be an instance of BaseQuery."""
    query = query_class({})
    assert isinstance(query, BaseQuery)


class TestKnownhostsQuery(object):
    """Knownhosts backend query test class."""

    def setup_method(self, _):
        """Set up an instance of KnownHostsQuery for each test."""
        # pylint: disable=attribute-defined-outside-init
        self.query = KnownHostsQuery({
            'knownhosts': {'files': [
                get_fixture_path(os.path.join('backends', 'knownhosts.txt')),
                get_fixture_path(os.path.join('backends', 'knownhosts_man.txt')),
            ]}})
        self.no_query = KnownHostsQuery({})
        self.no_hosts = NodeSet(resolver=RESOLVER_NOGROUP)
        self.domain_hosts = NodeSet('host[1,4-5,7-8,13-14].domain', resolver=RESOLVER_NOGROUP)
        self.all_hosts = self.domain_hosts | NodeSet('closenet,cvs.example.net', resolver=RESOLVER_NOGROUP)

    def test_instantiation(self):
        """An instance of KnownHostsQuery should be an instance of BaseQuery."""
        assert isinstance(self.query, BaseQuery)
        assert 'knownhosts' in self.query.config

    def test_execute(self):
        """Calling execute() with one host should return it."""
        assert self.query.execute('host1.domain') == NodeSet('host1.domain', resolver=RESOLVER_NOGROUP)

    def test_execute_non_existent(self):
        """Calling execute() with one host that doens't exists should return no hosts."""
        assert self.query.execute('nohost1.domain') == self.no_hosts

    def test_execute_or(self):
        """Calling execute() with two hosts in 'or' should return both hosts."""
        expected = NodeSet('host[1,4].domain', resolver=RESOLVER_NOGROUP)
        assert self.query.execute('host1.domain or host4.domain') == expected

    def test_execute_and(self):
        """Calling execute() with two hosts in 'and' should return no hosts."""
        assert self.query.execute('host1.domain and host2.domain') == self.no_hosts

    def test_execute_and_not(self):
        """Calling execute() with two hosts with 'and not' should return the first host."""
        expected = NodeSet('host1.domain', resolver=RESOLVER_NOGROUP)
        assert self.query.execute('host1.domain and not host2.domain') == expected

    def test_execute_xor(self):
        """Calling execute() with two host groups with 'xor' should return the hosts that are not in both groups."""
        expected = NodeSet('host[1,7-8].domain', resolver=RESOLVER_NOGROUP)
        assert self.query.execute('host[1-8].domain xor host[4-6].domain') == expected

    def test_execute_complex(self):
        """Calling execute() with a complex query should return the matching hosts."""
        expected = NodeSet('host[1,5,8].domain', resolver=RESOLVER_NOGROUP)
        assert self.query.execute('host1.domain or (host[5-9].domain and not host7.domain)') == expected

        expected = NodeSet('host1.domain', resolver=RESOLVER_NOGROUP)
        assert self.query.execute(
            '(host1.domain or host[2-5].domain) and not (host[3-9].domain or host2.domain)') == expected

    def test_execute_all(self):
        """Calling execute() with broader matching should return all hosts."""
        assert self.query.execute('*') == self.all_hosts
        assert self.query.execute('host[1-100].domain') == self.domain_hosts
        assert self.query.execute('host[1-100].domai?') == self.domain_hosts
        assert self.query.execute('host[1-100].*') == self.domain_hosts

    def test_execute_no_hosts(self):
        """Calling execute() without any known hosts to load should return no hosts."""
        assert self.no_query.execute('host1.domain') == self.no_hosts
        assert self.no_query.execute('*') == self.no_hosts


def test_parse_line_empty():
    """Empty lines should raise KnownHostsSkippedLineError."""
    with pytest.raises(KnownHostsSkippedLineError, match='empty line'):
        KnownHostsQuery.parse_known_hosts_line('')
    with pytest.raises(KnownHostsSkippedLineError, match='empty line'):
        KnownHostsQuery.parse_known_hosts_line('\n')


def test_parse_line_comment():
    """Comment lines should raise KnownHostsSkippedLineError."""
    with pytest.raises(KnownHostsSkippedLineError, match='comment'):
        KnownHostsQuery.parse_known_hosts_line('# comment')


def test_parse_line_hashed():
    """Hashed lines should raise KnownHostsSkippedLineError."""
    with pytest.raises(KnownHostsSkippedLineError, match='hashed'):
        KnownHostsQuery.parse_known_hosts_line('|1|HaSh=|HaSh= ecdsa-sha2-nistp256 AAAA...=')


def test_parse_line_no_fields():
    """Lines without enough fields should raise KnownHostsLineError."""
    with pytest.raises(KnownHostsLineError, match='not enough fields'):
        KnownHostsQuery.parse_known_hosts_line('host1 ssh-rsa')


def test_parse_line_no_fields_mark():
    """Lines with a marker but without enough fields should raise KnownHostsLineError."""
    with pytest.raises(KnownHostsLineError, match='not enough fields'):
        KnownHostsQuery.parse_known_hosts_line('@marker host1 ssh-rsa')


def test_parse_line_revoked():
    """Lines with a revoked marker should raise KnownHostsSkippedLineError."""
    with pytest.raises(KnownHostsSkippedLineError, match='revoked'):
        KnownHostsQuery.parse_known_hosts_line('@revoked host1 ecdsa-sha2-nistp256 AAAA...=')


def test_parse_line_unknown_marker():
    """Lines with an unknown marker should raise KnownHostsLineError."""
    with pytest.raises(KnownHostsLineError, match='unknown marker'):
        KnownHostsQuery.parse_known_hosts_line('@marker host1 ecdsa-sha2-nistp256 AAAA...=')


def test_parse_line_ca():
    """Lines with a cert-authority marker should parse the hostnames."""
    expected = ({'host1'}, set())
    assert KnownHostsQuery.parse_known_hosts_line('@cert-authority host1 ecdsa-sha2-nistp256 AAAA...=') == expected


def test_parse_line():
    """With a standard line should parse the hostnames."""
    assert KnownHostsQuery.parse_known_hosts_line('host1 ecdsa-sha2-nistp256 AAAA...=') == ({'host1'}, set())


def test_parse_line_hosts_empty():
    """Empty line hosts should be skipped."""
    assert KnownHostsQuery.parse_line_hosts(',') == (set(), set())
    assert KnownHostsQuery.parse_line_hosts('host1,,') == ({'host1'}, set())


def test_parse_line_hosts_negated():
    """Negated line hosts should remove the negation."""
    assert KnownHostsQuery.parse_line_hosts('!host1') == ({'host1'}, set())
    expected = ({'host1', 'host2'}, set())
    assert KnownHostsQuery.parse_line_hosts('!host1,host2') == expected
    assert KnownHostsQuery.parse_line_hosts('host1,!host2') == expected
    assert KnownHostsQuery.parse_line_hosts('!host1,!host2') == expected


def test_parse_line_hosts_port():
    """Line hosts with custom ports should remove the additional syntax."""
    assert KnownHostsQuery.parse_line_hosts('[host1]:2222') == ({'host1'}, set())
    expected = ({'host1', 'host2'}, set())
    assert KnownHostsQuery.parse_line_hosts('[host1]:2222,host2') == expected
    assert KnownHostsQuery.parse_line_hosts('host1,[host2]:2222') == expected
    assert KnownHostsQuery.parse_line_hosts('[host1]:2222,[host2]:2222') == expected


def test_parse_line_hosts_neg_port():
    """Line hosts with custom ports and negated entries should remove the additional syntax."""
    assert KnownHostsQuery.parse_line_hosts('![host1]:2222') == ({'host1'}, set())
    expected = ({'host1', 'host2'}, set())
    assert KnownHostsQuery.parse_line_hosts('![host1]:2222,!host2') == expected
    assert KnownHostsQuery.parse_line_hosts('!host1,![host2]:2222') == expected
    assert KnownHostsQuery.parse_line_hosts('![host1]:2222,![host2]:2222') == expected


def test_parse_line_hosts_patterns():
    """Line hosts with patterns should skip the patterns entries."""
    assert KnownHostsQuery.parse_line_hosts('host?') == (set(), {'host?'})
    assert KnownHostsQuery.parse_line_hosts('host*') == (set(), {'host*'})
    assert KnownHostsQuery.parse_line_hosts('host?,host2') == ({'host2'}, {'host?'})
    assert KnownHostsQuery.parse_line_hosts('host*,host2') == ({'host2'}, {'host*'})
    assert KnownHostsQuery.parse_line_hosts('host*,host2,host?') == ({'host2'}, {'host?', 'host*'})


def test_parse_line_hosts_ips():
    """Line hosts with IPs should skip the IP entries."""
    assert KnownHostsQuery.parse_line_hosts('127.0.1.1') == (set(), {'127.0.1.1'})
    assert KnownHostsQuery.parse_line_hosts('fe80::1') == (set(), {'fe80::1'})
    assert KnownHostsQuery.parse_line_hosts('host1,127.0.1.1') == ({'host1'}, {'127.0.1.1'})
    assert KnownHostsQuery.parse_line_hosts('host1,fe80::1') == ({'host1'}, {'fe80::1'})
    assert KnownHostsQuery.parse_line_hosts('host1,127.0.1.1,fe80::1') == ({'host1'}, {'127.0.1.1', 'fe80::1'})
