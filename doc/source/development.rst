Development
===========


Code Structure
--------------

Query and global grammar
^^^^^^^^^^^^^^^^^^^^^^^^

The :py:class:`cumin.query.Query` class is the one taking care of replacing the aliases, building and executing the
query parts with their respective backends and aggregating the results using the global grammar defined in
:py:func:`cumin.grammar.grammar`. Once a query is executed, it returns a :py:class:`ClusterShell.NodeSet.NodeSet` with
the FQDN of all the hosts that matches the selection.

Backends
^^^^^^^^

All the backends share a minimal common interface that is defined in the :py:class:`cumin.backends.BaseQuery` class
and they are instantiated by the :py:class:`Query` class when building and executing the query. Each backend module
need to define a ``query_class`` module variable that is a pointer to the backend class for dynamic instantiation and
a ``GRAMMAR_PREFIX`` constant string that is the identifier to be used in the main query syntax to identify the
backend. ``A`` is a reserved ``GRAMMAR_PREFIX`` used in the main grammar for aliases. Some backends are optional, in
the sense that their dependencies are not installed automatically, they are available as an ``extras_require`` when
installing from ``pip`` or as ``Suggested`` in the Debian package.

Given that the ``pyparsing`` library used to define the backend grammars uses a BNF-like style, for the details of the
tokens not specified in each backend BNF, see directly the code in the ``grammar`` function in the backend module.


Running tests
-------------

The ``tox`` utility, a wrapper around virtualenv, is used to run the tests. To list the default environments that
will be executed when running ``tox`` without parameters, run:

.. code-block:: bash

    tox -lv

To list all the available environments:

.. code-block:: bash

    tox -av

To run one specific environment only:

.. code-block:: bash

    tox -e py311-flake8

It's possible to pass extra arguments to the underlying environment:

.. code-block:: bash

    # Run only tests in a specific file:
    tox -e py311-unit -- -k test_puppetdb.py

    # Run only one specific test:
    tox -e py311-unit -- -k test_invalid_grammars

Integration tests are also available, but are not run by default by tox. They depends on a running Docker instance.
To run them:

.. code-block:: bash

    tox -e py311-integration
    tox -e py311-integration-min
