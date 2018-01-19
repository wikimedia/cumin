"""Test external backend module with wrong inheritance of the query class."""


class WrongInheritance(object):
    """Test query class with wrong inheritance."""


GRAMMAR_PREFIX = '_Z'
""":py:class:`str`: the prefix associate to this grammar, to register this backend into the general grammar.
Required by the backend auto-loader in :py:meth:`cumin.grammar.get_registered_backends`."""
query_class = WrongInheritance  # pylint: disable=invalid-name
"""Required by the backend auto-loader in :py:meth:`cumin.grammar.get_registered_backends`."""
