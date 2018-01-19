"""Test external backend module with missing GRAMMAR_PREFIX."""
from cumin.tests.unit.backends.external import ExternalBackendQuery


query_class = ExternalBackendQuery  # pylint: disable=invalid-name
"""Required by the backend auto-loader in :py:meth:`cumin.grammar.get_registered_backends`."""
