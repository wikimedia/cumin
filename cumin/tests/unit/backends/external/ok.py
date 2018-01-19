"""Test working external backend module."""
from cumin.tests.unit.backends.external import ExternalBackendQuery


GRAMMAR_PREFIX = '_Z'
""":py:class:`str`: the prefix associate to this grammar, to register this backend into the general grammar.
Required by the backend auto-loader in :py:meth:`cumin.grammar.get_registered_backends`."""
query_class = ExternalBackendQuery  # pylint: disable=invalid-name
"""Required by the backend auto-loader in :py:meth:`cumin.grammar.get_registered_backends`."""
