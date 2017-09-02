"""Direct backend tests."""

from cumin import nodeset
from cumin.backends import BaseQuery, direct


def test_direct_query_class():
    """An instance of query_class should be an instance of BaseQuery."""
    query = direct.query_class({})
    assert isinstance(query, BaseQuery)


class TestDirectQuery(object):
    """Direct backend query test class."""

    def setup_method(self, _):
        """Setup an instance of DirectQuery for each test."""
        self.query = direct.DirectQuery({})  # pylint: disable=attribute-defined-outside-init

    def test_instantiation(self):
        """An instance of DirectQuery should be an instance of BaseQuery."""
        assert isinstance(self.query, BaseQuery)
        assert self.query.config == {}

    def test_execute(self):
        """Calling execute() should return the list of hosts."""
        assert self.query.execute('host1 or host2') == nodeset('host[1-2]')
        assert self.query.execute('host1 and host2') == nodeset()
        assert self.query.execute('host1 and not host2') == nodeset('host1')
        assert self.query.execute('host[1-5] xor host[3-7]') == nodeset('host[1-2,6-7]')
        assert self.query.execute('host1 or (host[10-20] and not host15)') == nodeset('host[1,10-14,16-20]')
        assert self.query.execute('(host1 or host[2-3]) and not (host[3-9] or host2)') == nodeset('host1')
