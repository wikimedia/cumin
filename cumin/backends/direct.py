"""Direct backend."""

from ClusterShell.NodeSet import NodeSet

from cumin.backends import BaseQuery, InvalidQueryError


class DirectQuery(BaseQuery):
    """DirectQuery query builder.

    The 'direct' backend allow to use Cumin without any external dependency for the hosts selection.
    It implements only the add_hosts() method and allow only for hosts expansion based on the powerful ClusterShell
    NodeSet syntax, see https://clustershell.readthedocs.io/en/latest/api/NodeSet.html

    The typical usage for the 'direct' backend is as a reliable alternative in cases in which the primary host
    selection mechanism is not working and for testing the transports without any external backend dependency.
    """

    def __init__(self, config, logger=None):
        """Query Builder constructor.

        Arguments: according to BaseQuery interface
        """
        super(DirectQuery, self).__init__(config, logger)
        self.hosts = NodeSet()

    def add_category(self, category, key, value=None, operator='=', neg=False):
        """Required by BaseQuery."""
        raise InvalidQueryError("Category tokens are not supported by the DirectQuery backend")

    def add_hosts(self, hosts, neg=False):
        """Required by BaseQuery."""
        if any(host for host in hosts if '*' in host):
            raise InvalidQueryError("Hosts globbing is not supported by the DirectQuery backend")

        if neg:
            self.hosts.difference_update(hosts)
        else:
            self.hosts.update(hosts)

    def open_subgroup(self):
        """Required by BaseQuery."""
        raise InvalidQueryError("Subgroups are not supported by the DirectQuery backend")

    def close_subgroup(self):
        """Required by BaseQuery."""
        raise InvalidQueryError("Subgroups are not supported by the DirectQuery backend")

    def add_and(self):
        """Required by BaseQuery."""
        raise InvalidQueryError("Boolean AND operator is not supported by the DirectQuery backend")

    def add_or(self):
        """Required by BaseQuery."""
        pass  # Nothing to do, all hosts are added to the same NodeSet

    def execute(self):
        """Required by BaseQuery."""
        self.logger.debug("Direct backend matches '{num}' hosts.".format(num=len(self.hosts)))
        return list(self.hosts)


query_class = DirectQuery  # Required by the auto-loader in the cumin.query.Query factory
