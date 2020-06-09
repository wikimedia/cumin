Cumin Changelog
---------------


`v4.0.0rc1`_ (2020-06-09)
^^^^^^^^^^^^^^^^^^^^^^^^^

Dependency breaking changes
"""""""""""""""""""""""""""

* tqdm: limit the compatible versions of tqdm allowed to a small range of versions between ``4.19.4`` and ``4.24.0``)
  due to an upstream bug, see `tqdm issue #777`_. The ``4.23.4-1~wmf1`` version of tqdm is available as a Debian
  package for buster in the Wikimedia APT repository in the ``component/spicerack`` component.

New features
""""""""""""

* Replace colorama with custom module (`T217038`_).

  * In Debian stretch there is a regression in colorama in conjunction with tqdm that leads to a slow down of the
    progress of the script proportional to the amount of data printed to stdout/err. Colorama starts having very
    huge stacktraces and the process is stuck at 100% CPU for an increasingly amount of time while more data is
    printed.
  * Given the very simple usage of colors that is made in Cumin as of now, it seems much more feasible to replace
    the colorama library (as all that cross-OS support is not needed) and add a simple module with ANSI escape
    sequence support.
  * Use a type (metaclass) to be able to override ``__getattr__`` for the static methods of the classes that use it
    and to automatically define a method for each color in a DRY way without code duplication.
  * Define a ``Colored`` class that uses ``ColoredType`` as metaclass to inherit its type with the custom behaviour.
  * For each color defined in ``ColoredType.COLORS`` a method of ``Colored`` is defined, e.g. ``Colored.red()``.
  * The ``Colored`` class has a ``disabled`` property that can be set to ``True`` to globally disable coloring. This
    could for example be integrated later into the CLI as an option to disable colors or allow to add some code to the
    ``color.py`` module to autodetect when not in a TTY and automatically disable all colors.

* Allow running cumin as a regular user (`T218440`_).

* backends.puppetdb: make the PuppetDB backend process primitive types for queries (`T207037`_).

  * Modify the grammar to recognize primitive PuppetDB types, communicate quotedness to the final output as
    appropriate.

* backends.puppetdb: allow to override the URL scheme in the configuration (`T218441`_).

  * In some environments the PuppetDB hosts might listen only on HTTP on localhost and the Cumin host might connect
    to it via an SSH tunnel.
  * Allow to override the default HTTPS scheme of the PuppetDB URL in the configuration.

* backends.puppetdb: fix regex matching.

  * Fix regex matching in PuppetDB queries that requires that all backslashes are escaped according to the PuppetDB
    API. See PuppetDB documentation on `regexp-match`_.

* backends.openstack: add custom parameters for the client (`T201881`_).

  * The instantiation of the novaclient ``Client`` might require additional parameters based on the specific
    OpenStack installation, like for example a ``region_name``.
  * Add a generic ``client_params`` section to the configuration to allow to set arbitrary additional parameters
    that will be passed to the novalicent's ``Client``.

* CLI: improve help message (`T204680`_).

  * Specify that the ``--debug`` and ``--trace`` options affect the logs and not the output and where to find the logs.

Miscellanea
"""""""""""

* Add official support to Python 3.7, deprecate support for 3.4, 3.5 and 3.6.
* setup.py: make it compatible with Debian buster.

  * Add support for Debian Buster, using its versions as minimum required version for dependencies except tqdm.
  * For tqdm restrict the possible versions to a specific range, that is the only one that works fine with multiple
    progress bars and colors.
  * Remove support for Debian Stretch

* transports.clustershell: extract progress bars from clustershell event handling.
* tests: fix any newly reported issue by the various linters and static checkers.
* tests: refactor some tests taking advantage of pytest functionalities.
* tests: refactor tox configuration.
* Updated documentation according to external dependency changes.
* flake8: enforce import order and adopt ``W504``.

  * Add ``flake8-import-order`` to enforce the import order using the ``edited`` style that corresponds to our
    styleguide, see: `Python imports`_.
  * Fix all out of order imports.
  * For line breaks around binary operators, adopt ``W504`` (breaking before the operator) and ignore ``W503``,
    following PEP8 suggestion, see: `PEP8 binary operator`_.
  * Fix all line breaks around binary operators to follow ``W504``.

* test: improve integration tests

  * Don't hide the output of the setup commands, it's useful to both see that the output is visually correct and
    allow to debug any error in setting up the integration tests.
  * Allow to pass arguments to the integrations tests so that the deletion of the test instances and temporarily
    generated files can be accessed for debugging.

* doc: fix and improve documentation.

  * Adapt Sphinx settings according to the newer version used.
  * Fix links to the documentation of external libraries.
  * Add and include the diagram image for the available transitions for the ``cumin.transports.State`` class.
  * Improve docstrings for a better generated documentation result.
  * Remove unnecessary Sphinx helper functions, now correctly handled by Sphinx natively.

* doc: split HTML and manpage generation.

  * Add a ``man`` tox environment to build only the manpage.
  * Add a dedicated ``man-min`` environment to build the manpage with the minimum version of Sphinx, that is the one
    of Debian Buster and that will be used to generate the manpage when building the Debian package.
  * Let the sphinx tox environment just build the HTML documentation.

`v3.0.2`_ (2018-07-30)
^^^^^^^^^^^^^^^^^^^^^^

Bug Fixes
"""""""""

* Fix the ``-o/--output`` option (bytes->str conversion) (`T200622`_):

  * The migration to Python3 left the ``-o/--output`` option of the CLI with some decoding issue from bytes to string.
  * Uniforming all calls to ``bytes.decode()`` not specifying the encoding as ``utf-8`` is the default in Python 3.
  * Add integration tests for the ``-o/--output`` option.

* CLI: fix ``setup_logging()`` when called without path (`T188627`_):

  * Fix the ``setup_logging()`` function when it's called with a filename without a path, in order to log directly
    into the current directory. Thanks goes to aggro for reporting it.

* Fix debugging log message conversion. The Command.timeout can also be None in case is not set, converting it to
  string instead of integer for the debug messages.

Miscellanea
"""""""""""

* Updated PyPI URLs to the new PyPI website

`v3.0.1`_ (2018-02-19)
^^^^^^^^^^^^^^^^^^^^^^

Bug Fixes
"""""""""

* CLI: fix help message

`v3.0.0`_ (2018-02-19)
^^^^^^^^^^^^^^^^^^^^^^

API breaking changes
""""""""""""""""""""

* Migration to Python 3, dropping support of Python 2. Besides the usual Py2 -> Py3 conversions, the main changes are:

  * Add ``nodeset()`` and ``nodeset_fromlist()`` functions in the ``cumin`` module to instantiate ClusterShell's
    NodeSet objects with the resolver set to ``RESOLVER_NOGROUP``, due to `ClusterShell issue #368`_.
  * Bump dependency on ClusterShell library to 1.8.
  * Adapt callbacks in ClusterShell backend to the new ClusterShell's API signatures of version 1.8.
  * Use ``threading.Lock()`` calls as context managers for the ``with`` statement.
  * Use Colorama autoreset feature, simplifying its related calls.

New features
""""""""""""

* Backends: add known hosts files backend:

  * The ``knownhosts`` backend allow to use Cumin taking advantage of existing SSH known hosts files that are not
    hashed. It allow to write arbitrarily complex queries with subgroups and boolean operators, but each item must be
    either the hostname itself, or using host expansion with the powerful ClusterShell's ``NodeSet`` syntax.

  * See the example configuration on how to configure this backend with the list of known hosts files to be parsed.

  * The typical use case for the ``knownhosts`` backend is when the known hosts file(s) are generated and kept updated
    by some external configuration manager or tool that is not yet supported as a backend for Cumin. It can also work
    as a fallback backend in case the primary backend is unavailable but the known hosts file(s) are still up to date.

* Batch size: allow to specify it in percentage (`T187185`_):

  * Transports: allow to specify a ``batch_size_ratio`` as a float number in the Target constructor to set the
    ``batch_size`` as a percentage of the hosts list.
  * CLI: make the ``--batch-size`` option to accept both integers and percentage (i.e. ``50%``) values.

`v2.0.0`_ (2018-01-19)
^^^^^^^^^^^^^^^^^^^^^^

API breaking changes
""""""""""""""""""""

* Logging: uniform loggers (`T179002`_):

  * Remove optional parameter logger from all classes where it was accepted, the classes instantiate the proper logger
    based on the current module and class name.

* ClusterShell backend: fix ``execute()`` return code:

  * The return code of the ``execute()`` method was not respecting the parent class contract for its return code when
    there are no commands set or no hosts to target.
  * Make the ``Target`` class raise a ``WorkerError`` exception on instantiation if there are no target hosts.
  * Make the ``execute()`` method raise a ``WorkerError`` exception if there are no commands to execute.

New features
""""""""""""

* Backends: add support to external backends plugins (`T178342`_):

  * Custom external backends can be developed outside of Cumin and used by Cumin as any other backend.
  * The external backends must:

    * Be present in Python ``PATH``.
    * Define a ``GRAMMAR_PREFIX`` attribute that doesn't conflict with built-in backends prefixes.
    * Define a ``query_class`` attribute pointing to a class that inherit from ``cumin.backends.BaseQuery``.

  * The CLI is not anymore able to enforce that the ``--backend`` parameter is valid when parsing the command line
    arguments, but will fail later on with a clear message.

* PuppetDB backend: add support for PuppetDB API v4 (`T182575`_):

  * Allow to set the API version via configuration.
  * Default to API v4 as v3 is obsolete.
  * Use POST for API v4 to overcome GET limits on large queries, fixes `T166397`_.
  * Bumped minimum version for ``requests-mock`` to ``1.3.0``.

Minor improvements
""""""""""""""""""

* Logging: uniform loggers (`T179002`_):

  * Use proper hierarchical loggers across the project.
  * For classes inherited from a base abstract class, the logger is defined only in the base abstract class, with the
    name of the concrete class that is calling it.
  * Changed CLI logging format to take advantage of the hirarchical logging.

* Logging: use ``%`` syntax for parameters (`T179002`_):

  * For optimization purposes and to adhere to Python best practices, use ``%s`` syntax in logging messages and pass
    the replacement parameters to the logging function. Some messages are still pre-formatted before the call to the
    logging function because used also for other purposes.
  * pylint: re-enable the check for logging-format-interpolation.

`v1.3.0`_ (2017-11-03)
^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* PuppetDB backend: Class, Roles and Profiles shortcuts (`T178279`_):

  * It is becoming common practice to use the role/profile paradigm in Puppet, where each host has only one role named
    ``Role::Module::Name`` that includes multiple profiles of the type ``Profile::Module::Name``. If this practice is
    used, queries for those resources in Cumin will be very common and not user-friendly, requiring to write queries of
    the type ``R:Class = Role::Module::Name``. Add support to Roles and Profiles so that they can be queried via
    shortcuts with ``O:Module::Name`` for roles and ``P:Module::Name`` for profiles.
  * Add also a generic class shortcut to quickly query a class resource with ``C:class_name`` or ``C:path::to::class``.
  * The special syntax for fields ``@field`` and parameters ``%param`` are also supported. When querying for any of the
    above shortcuts, like ``P:Module::Name%param = value``. The generated query will include two subqueries in ``AND``
    between them, one for the class title and the other for the class parameter.

Minor improvements
""""""""""""""""""

* Refactor documentation:

  * Moved most of the content from the README to the classes, function and documentation pages where it really belongs.
  * Add documentation files for an introduction to cumin, how to install it, how to develop it and with the release
    notes.
  * Add animated GIF to the README and documentation introduction.

Bug Fixes
"""""""""

* Documentation: amend CHANGELOG and TODO for the addition of the manpage in `v1.2.2`_ (`T159308`_).
* Documentation: add ReadTheDocs specific configuration.
* Documentation: fix ReadTheDocs CSS override

`v1.2.2`_ (2017-10-11)
^^^^^^^^^^^^^^^^^^^^^^

Minor improvements
""""""""""""""""""
* Dependencies: split the OpenStack dependencies into a separate ``extras_require`` in ``setup.py``. This allows to
  install Cumin without all the dependencies needed for the OpenStack backend, if that is not needed.
* Docstrings: use Google Style Python Docstrings to allow to automatically generate documentation with Sphinx.
* Documentation: converted ``README``, ``CHANGELOG`` and ``TODO`` from Markdown to reStructuredText. PyPI renders only
  reStructuredText while GitHub renders both. Moving to reStructuredText to be PyPI friendly and allow to write more
  powerful documentation.
* CLI: extract the ``ArgumentParser`` definition from ``parse_args()`` into a ``get_parser()`` function for easier
  testability and documentation generation. Uniform help messages in ``ArgumentParser`` options.
* setup.py: prepare for PyPi submission. Include the full ``README.rst`` as long description.
* Documentation: setup Sphinx to generate the documentation and to auto-document the API and CLI.
* Testing: refactored ``tox.ini`` to reduce the number of virtualenv while expanding the available environments for
  static analysis and tests performed, including running unit tests with the minimum supported versions of all the
  dependencies.
* CLI: add manpage (`T159308`_)

`v1.2.1`_ (2017-09-27)
^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* OpenStack backend: allow to set default query params in the configuration (`T176314`_):
  Allow to set arbitrary default query params in the configuration for the OpenStack backend. This is useful for
  example if Cumin is installed inside an OpenStack project to automatically search only within the instances of the
  current project. See the example in the provided ``doc/examples/config.yaml`` file.

Bug Fixes
"""""""""

* Configuration: do not raise on empty configuration or aliases. Moved the check of required parameters where needed,
  in order to raise explicit exceptions with a more meaningful message for the user.
* Exceptions: convert remaining spurious exceptions to CuminError or improve their error message.

`v1.1.1`_ (2017-09-26)
^^^^^^^^^^^^^^^^^^^^^^

Bug Fixes
"""""""""

* OpenStack: limit grammar to not overlap with the global one.

`v1.1.0`_ (2017-09-21)
^^^^^^^^^^^^^^^^^^^^^^

New features
""""""""""""

* Backends: add OpenStack backend (`T175711`_).

Bug Fixes
"""""""""

* CLI: fix --version option.
* Installation: fix ``data_files`` installation directory (`T174008`_)
* Transports: better handling of empty list (`T174911`_):

  * BaseWorker: accept an empty list in the command setter. It's its default value, there is no point in forbidding a
    client to set it to the same value.
  * ClusterShellWorker: return immediately if there are no target hosts.

* Clustershell: make call to tqdm.write() explicit where to send the output, not relying on its default.

`v1.0.0`_ (2017-08-23)
^^^^^^^^^^^^^^^^^^^^^^

CLI breaking changes
""""""""""""""""""""

* CLI: migrate to timeout per command (`T164838`_):

  * the global timeout command line options changes from ``-t/--timeout`` to ``--global-timeout``.
  * the ``-t/--timeout`` option is now used to set the timeout for each command in each host independently.

Configuration breaking changes
""""""""""""""""""""""""""""""

* Query: add multi-query support (`T170394`_):

  * Remove the ``backend`` configuration key as it is not anymore used.
  * Add a new optional ``default_backend`` configuration key. If set the query will be first executed with the default
    backend, and if failing the parsing it will be executed with the global multi-query grammar. This allow to keep
    backward compatibility with the query that were executed with previous versions of Cumin.

API breaking changes
""""""""""""""""""""

* PuppetDB backend: consistently use ``InvalidQueryError`` (`T162151`_).
* Transports: refactor command handling to support new features (`T164838`_), (`T164833`_) and (`T171679`_):

  * Transports: move ``BaseWorker`` helper methods to module functions.
  * Transports: add ``Command`` class.
  * Transports: use the new ``Command`` class in ``BaseWorker``, moving from a list of strings to a list of ``Command``
    objects.
  * Transports: maintain backward compatibility and easy of usage automatically converting a list of strings to a list
    of ``Command`` objects when setting the commands property.
  * Allow to set the ``ok_codes`` property of the ``transports.Command`` class to an empty list to consider any return
    code as successful. The case in which no return code should be treated successful has no practical use.
  * ClusterShell: adapt the calls to commands for the new ``Command`` objects.

* Configuration: move configuration loader from the ``cli`` module to the main ``cumin`` module (`T169640`_):

  * add a ``cumin.Config`` class.
  * move the ``parse_config`` helper to cumin's main module from the ``cli`` one, to allow to easily load the
    configuration also when it's used as a Python library.

* ``QueryBuilder``: move query string to ``build()`` method. The constructor of the ``QueryBuilder`` was changed to not
  accept anymore a query string directly, but just the configuration and the optional logger. The query string is now a
  required parameter of the ``build()`` method. This properly split configuration and parameters, allowing to easily
  ``build()`` multiple queries with the same ``QueryBuilder`` instance.
* Transports: convert hosts to ClusterShell's ``NodeSet`` (`T170394`_):

* in preparation for the multi-query support, start moving the transports to accept a ClusterShell's ``NodeSet``
  instead of a list of nodes. With the new multi-query support the backends too will return only NodeSets.

* Query: add multi-query support (`T170394`_):

  * Aliases are now global and must use the global grammar syntax.
  * ``Query`` class: the public ``build()`` method has become private and now is sufficient to call the
    ``execute(query_string)`` method. Example usage::

        config = cumin.Config(args.config)
        hosts = query.Query(config, logger=logger).execute(query_string)

  * ``Query`` class: the public methods ``open_subgroup()`` and ``close_subgroup()`` have become private,
    ``_open_subgroup()`` and ``_close_subgroup()`` respectively.

* Transports: improve target management (`T171684`_):

  * Add a ``Target`` class to handle all the target-related configuration.
  * Let the ``BaseWorker`` require an instance of the ``Target`` class and delegate to it for all the target-related
    configuration.
  * This changes the ``BaseWorker`` constructor signature and removes the ``hosts``, ``batch_size`` and ``batch_sleep``
    setters/getters.

New features
""""""""""""

* CLI: automatically set dry-run mode when no commands are specified (`T161887`_).
* ClusterShell transport: output directly when only a single host is targeted. When the commands are executed against
  only one host, print the output directly as it comes, to give the user an immediate feedback. There is no advantage
  to collect the output for de-duplication in this case (`T164827`_).
* Transports: allow to specify a timeout per ``Command`` (`T164838`_).
* Transports: allow to specify exit codes per ``Command`` (`T164833`_). Allow to specify for each ``Command`` object a
  list of exit codes to be considered successful when executing its specific command.
* ClusterShell backend: allow to specify exit codes per ``Command`` (`T164833`_).
* ClusterShell backend: allow to set a timeout per ``Command`` (`T164838`_).
* CLI: add ``-i/--interactive`` option (`T165838`_). When set, this option drops into a Python shell (REPL) after the
  execution, allowing the user to manipulate the results with the full power of Python. In this first iteration it can
  be used only when one command is specified.
* CLI: add ``-o/--output`` to get the output in different formats (`T165842`_). Allow to have ``txt`` and ``json``
  output when only one command is specified. In this first iteration the formatted output will be printed after the
  standard output with a separator, in a next iteration the standard output will be suppressed.
* Query and grammar: add support for aliases (`T169640`_):

  * Allow aliases of the form ``A:alias_name`` into the grammar.
  * Automatically replace recursively all the aliases directly in the ``QueryBuilder``, to make it completely
    transparent for the backends.

* Configuration: automatically load aliases from file (`T169640`_). When loading the configuration, automatically load
  also any aliases present in the ``aliases.yaml`` file in the same directory of the configuration file, if present.
* Query: add multi-query support (`T170394`_):

  * Each backend has now its own grammar and parsing rules as they are completely independent from each other.
  * Add a new global grammar that allows to execute blocks of queries with different backends and aggregate the
    results.

* CLI: add an option to ignore exit codes of commands (`T171679`_). Add the ``-x/--ignore-exit-codes`` option to
  consider any executed command as successful, ignoring the returned exit codes. This can be useful for a cleaner
  output and the usage of batches when running troubleshooting commands for which the return code might be ignored
  (i.e. grep).

Minor improvements
""""""""""""""""""

* CLI: improve configuration error handling (`T158747`_).
* Fix Pylint and other validation tools reported errors (`T154588`_).
* Package metadata and testing tools improvements (`T154588`_):

  * Fill ``setup.py`` with all the parameters, suitable for a future submission to PyPI.
  * Autodetect the version from Git tags and expose it in the module using ``setuptools_scm``.
  * CLI: add a ``--version`` option to print the current version and exit.
  * Tests: use ``pytest`` to run the tests.
  * Tests: convert tests from ``unittest`` to ``pytest``.
  * Tests: make ``tox`` use the dependencies in ``setup.py``, removing the now unnecessary requirements files.
  * Tests: add security analyzer ``Bandit`` to ``tox``.
  * Tests: add ``Prospector`` to ``tox``, that in turns runs multiple additional tools: ``dodgy``, ``mccabe``,
    ``pep257``, ``pep8``, ``profile-validator``, ``pyflakes``, ``pylint``, ``pyroma``, ``vulture``.

* Tests: simplify and improve parametrized tests. Take advantage of ``pytest.mark.parametrize`` to run the same test
  multiple times with different parameters instead of looping inside the same test. This not only simplifies the code
  but also will make each parametrized test fail independently allowing an easier debugging.
* CLI: simplify imports and introspection.
* Logging: add a custom ``trace()`` logging level:

  * Add an additional custom logging level after ``DEBUG`` called ``TRACE`` mainly for development debugging.
  * Fail in case the same log level is already set with a different name. This could happen when used as a library.
  * CLI: add the ``--trace`` option to enable said logging level.

* Tests: improved tests fixture usage and removed usage of the example configuration present in the documentation from
  the tests.
* Transports: improve command list validation of the ``transports.Command`` class to not allow an empty list for the
  commands property (`T171679`_).

Bug Fixes
"""""""""

* PuppetDB backend: do not auto upper case the first character when the query is a regex (`T161730`_).
* PuppetDB backend: forbid resource's parameters regex as PuppetDB API v3 do not support regex match for resource's
  parameters (`T162151`_).
* ClusterShell transport: fix set of list options (`T164824`_).
* Transports: fix ``success_threshold`` getter when set to ``0`` (`T167392`_).
* Transports: fix ``ok_codes`` getter for empty list (`T167394`_).
* ``QueryBuilder``: fix subgroup close at the end of query. When a query was having subgroups that were closed at the
  end of the query, QueryBuilder was not calling the ``close_subgroup()`` method of the related backend as it should
  have. For example in a query like ``host1* and (R:Class = Foo or R:Class = Bar)``.
* Fix test dependency issue. Due to a braking API change in the latest version of ``Vulture``, ``Prospector`` is not
  working anymore with the installed version of ``Vulture`` due to missing constraint in their ``setup.py``. See
  `Prospector issue #230`_ for more details.

`v0.0.2`_ (2017-03-15)
^^^^^^^^^^^^^^^^^^^^^^

Configuration breaking changes
""""""""""""""""""""""""""""""

* Add support for batch processing (`T159968`_):

  * Moved the ``environment`` block in the configuration file to the top level from within a specific transport.

API breaking changes
""""""""""""""""""""

* Add support for batch processing (`T159968`_):

  * Refactored the ``BaseWorker`` class (and the ``ClusterShellWorker`` accordingly) to avoid passing a lot of
    parameters to the execute() method, moving them to setters and getters with validation and default values,
    respectively.
  * Add state machine for a transport's node state.
  * Add CuminError exception and make all custom exceptions inherit from it to allow to easily catch only Cumin's
    exceptions.

* ClusterShell transport: always require an event handler (`T159968`_):

  * Since the addition of the batch capability running without an event handler doesn't really work because only the
    first batch will be scheduled.
  * Updated the CLI to work transparently and set the mode to ``sync`` when there is only one command.
  * Unify the reporting lines format and logic between ``sync`` and ``async`` modes for coherence.

New features
""""""""""""

* Add support for ``not`` in simple hosts selection queries (`T158748`_).
* Add support for batch processing (`T159968`_):

  * It's now possible to specify a ``batch_size`` and a ``batch_sleep`` parameters to define the size of a sliding
    batch and an optional sleep between hosts executions.
  * ClusterShell transport: the batches behaves accordingly to the specified mode when multiple commands are specified:

    * ``sync``: the first command is executed in a sliding batch until executed on all hosts or aborted due unmet
      success ratio. Then the execution of the second command will start if the success ratio is reached.
    * ``async``: all the commands are executed in series in the first batch, and then will proceed with the next hosts
      with a sliding batch, if the success ratio is met.

  * Improves logging for backends and transport.
  * CLI: updated to use the batch functionality, use the transport return value as return code on exit.
  * Improves test coverage.

* PuppetDB backend: automatically upper case the first character in resource names (`T159970`_).

Minor improvements
""""""""""""""""""

* Moved ``config.yaml`` to a ``doc/examples/`` directory. It simplify the ship of the example file when packaging.
* Allow to ignore selected ``urllib3`` warnings (`T158758`_).
* Add codecov and codacy config and badges.
* Fixing minor issues reported by codacy (`T158967`_).
* Add integration tests for ClusterShell transport using Docker (`T159969`_).

Bug Fixes
"""""""""

* Match the whole string for hosts regex matching (`T158746`_).

`v0.0.1`_ (2017-02-17)
^^^^^^^^^^^^^^^^^^^^^^

* First released version (`T154588`_).


.. _`Prospector issue #230`: https://github.com/landscapeio/prospector/issues/230
.. _`ClusterShell issue #368`: https://github.com/cea-hpc/clustershell/issues/368
.. _`tqdm issue #777`: https://github.com/tqdm/tqdm/issues/777
.. _`regexp-match`: https://puppet.com/docs/puppetdb/4.4/api/query/v4/ast.html#regexp-match
.. _`Python imports`: https://www.mediawiki.org/wiki/Manual:Coding_conventions/Python#Imports
.. _`PEP8 binary operator`: https://www.python.org/dev/peps/pep-0008/#should-a-line-break-before-or-after-a-binary-operator

.. _`T154588`: https://phabricator.wikimedia.org/T154588
.. _`T158746`: https://phabricator.wikimedia.org/T158746
.. _`T158747`: https://phabricator.wikimedia.org/T158747
.. _`T158748`: https://phabricator.wikimedia.org/T158748
.. _`T158758`: https://phabricator.wikimedia.org/T158758
.. _`T158967`: https://phabricator.wikimedia.org/T158967
.. _`T159308`: https://phabricator.wikimedia.org/T159308
.. _`T159968`: https://phabricator.wikimedia.org/T159968
.. _`T159969`: https://phabricator.wikimedia.org/T159969
.. _`T159970`: https://phabricator.wikimedia.org/T159970
.. _`T161730`: https://phabricator.wikimedia.org/T161730
.. _`T161887`: https://phabricator.wikimedia.org/T161887
.. _`T162151`: https://phabricator.wikimedia.org/T162151
.. _`T164824`: https://phabricator.wikimedia.org/T164824
.. _`T164827`: https://phabricator.wikimedia.org/T164827
.. _`T164833`: https://phabricator.wikimedia.org/T164833
.. _`T164838`: https://phabricator.wikimedia.org/T164838
.. _`T165838`: https://phabricator.wikimedia.org/T165838
.. _`T165842`: https://phabricator.wikimedia.org/T165842
.. _`T166397`: https://phabricator.wikimedia.org/T166397
.. _`T167392`: https://phabricator.wikimedia.org/T167392
.. _`T167394`: https://phabricator.wikimedia.org/T167394
.. _`T169640`: https://phabricator.wikimedia.org/T169640
.. _`T170394`: https://phabricator.wikimedia.org/T170394
.. _`T171679`: https://phabricator.wikimedia.org/T171679
.. _`T171684`: https://phabricator.wikimedia.org/T171684
.. _`T174008`: https://phabricator.wikimedia.org/T174008
.. _`T174911`: https://phabricator.wikimedia.org/T174911
.. _`T175711`: https://phabricator.wikimedia.org/T175711
.. _`T176314`: https://phabricator.wikimedia.org/T176314
.. _`T178279`: https://phabricator.wikimedia.org/T178279
.. _`T178342`: https://phabricator.wikimedia.org/T178342
.. _`T179002`: https://phabricator.wikimedia.org/T179002
.. _`T182575`: https://phabricator.wikimedia.org/T182575
.. _`T187185`: https://phabricator.wikimedia.org/T187185
.. _`T188627`: https://phabricator.wikimedia.org/T188627
.. _`T200622`: https://phabricator.wikimedia.org/T200622
.. _`T201881`: https://phabricator.wikimedia.org/T201881
.. _`T204680`: https://phabricator.wikimedia.org/T204680
.. _`T207037`: https://phabricator.wikimedia.org/T207037
.. _`T217038`: https://phabricator.wikimedia.org/T217038
.. _`T218440`: https://phabricator.wikimedia.org/T218440
.. _`T218441`: https://phabricator.wikimedia.org/T218441

.. _`v0.0.1`: https://github.com/wikimedia/cumin/releases/tag/v0.0.1
.. _`v0.0.2`: https://github.com/wikimedia/cumin/releases/tag/v0.0.2
.. _`v1.0.0`: https://github.com/wikimedia/cumin/releases/tag/v1.0.0
.. _`v1.1.0`: https://github.com/wikimedia/cumin/releases/tag/v1.1.0
.. _`v1.1.1`: https://github.com/wikimedia/cumin/releases/tag/v1.1.1
.. _`v1.2.1`: https://github.com/wikimedia/cumin/releases/tag/v1.2.1
.. _`v1.2.2`: https://github.com/wikimedia/cumin/releases/tag/v1.2.2
.. _`v1.3.0`: https://github.com/wikimedia/cumin/releases/tag/v1.3.0
.. _`v2.0.0`: https://github.com/wikimedia/cumin/releases/tag/v2.0.0
.. _`v3.0.0`: https://github.com/wikimedia/cumin/releases/tag/v3.0.0
.. _`v3.0.1`: https://github.com/wikimedia/cumin/releases/tag/v3.0.1
.. _`v3.0.2`: https://github.com/wikimedia/cumin/releases/tag/v3.0.2
.. _`v4.0.0rc1`: https://github.com/wikimedia/cumin/releases/tag/v4.0.0rc1
