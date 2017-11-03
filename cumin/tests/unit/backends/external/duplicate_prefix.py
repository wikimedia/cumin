"""Test external backend module with a GRAMMAR_PREFIX that conflicts with an existing one."""
from cumin.tests.unit.backends.external import ExternalBackendQuery


GRAMMAR_PREFIX = 'D'
""":py:class:`str`: the prefix associate to this grammar, to register this backend into the general grammar.
Required by the backend auto-loader in :py:meth:`cumin.grammar.get_registered_backends`."""
query_class = ExternalBackendQuery  # pylint: disable=invalid-name
"""Required by the backend auto-loader in :py:meth:`cumin.grammar.get_registered_backends`."""
