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

CLI output tests
^^^^^^^^^^^^^^^^

In order to be able to compare the CLI output between different Cumin versions, there is a suite of tests available for
that. It requires to have either two separate checkouts of Cumin's code at two different versions, or to switch between
versions/branches each time the tests are run. In both checkouts run the basic unit tests to create the virtual
environment that will be used later:

.. code-block:: bash

    tox -e py313-unit

In the checkout of the new code, run the integration tests with the flag for leaving the target instances around:

.. code-block:: bash

    tox -e py313-integration -- 1

While the integration tests run, look at its output to locate the line with  ``Temporary directory is`` and annotate
it. It should look like this one:

.. code-block:: bash

    Temporary directory is: /tmp/cumin-euePpW

Once the integration tests are done, the target instances will still be around and will now be possible to run the
comparison tests.

Open two terminal prompts, one in the old checkout and the other with the new development code. In both source the
local virtual environment of the unit tests run before:

.. code-block:: bash

    . .tox/py313-unit/bin/activate

In both terminals cd into the temporary directory created by the integration tests that was annotated earlier:

.. code-block:: bash

    cd /tmp/cumin-euePpW

Now run the comparison tests from the new checkout (to run the same tests in both cases) in both environments,
redirecting the output to two separate files. The tests take few minutes to run. Best results are obtained when
running them one environment at a time:

.. code-block:: bash

    # in the new venv
    CUMIN_IDENTIFIER="${PWD##*/}" pytest -q --capture=no /path-to-new-checkout/cumin/tests/integration/compare_cli.py &> new.out
    # in the old venv
    CUMIN_IDENTIFIER="${PWD##*/}" pytest -q --capture=no /path-to-new-checkout/cumin/tests/integration/compare_cli.py &> old.out

The environment variable ``CUMIN_PROGRESS_BARS`` is also read as a boolean and allows to make Cumin print the progress
bars during the execution. By default it's off to make the output file and the diff easier to read.

Finally compare the results with some diff tool. Be aware that some tests commands expect different outputs from
different target hosts, and it's possible that there will be ordering differences in the output due to the timing
of the response from different hosts. This is normal and should not be considered a regression. An helper script is
provided to simplify the diff operation. It splits the output of the old and new runs into one file per test two given
directories and then compares them one by one. For each file it compares also the sorted version of the files and
considers identical files in which just the ordering changed. When a file differs it prints out both the normal diff
and the diff of the files sorted, to make it easier for the operator to understand the actual differences.
The helper script can be run, from within the temporary directory where the above commands were run, with:

.. code-block:: bash

    /path-to-new-checkout/cumin/tests/integration/compare_cli.sh

At this point the running docker containers can be terminated and the temporary directory deleted.
