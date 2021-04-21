Introduction
============


.. include:: ../../README.rst


Main components
---------------

Query language
^^^^^^^^^^^^^^

Cumin provides a user-friendly generic query language that allows to combine the results of subqueries from multiple
backends. The details of the main grammar are:

* Each query part can be composed with any other query part using boolean operators: ``and``, ``or``, ``and not``,
  ``xor``.
* Multiple query parts can be grouped together with parentheses: ``(``, ``)``.
* Each query part can be one of:

  * Specific backend query: ``I{backend-specific query syntax}`` (where ``I`` is an identifier for the specific
    backend).
  * Alias replacement, according to the aliases defined in the configuration: ``A:group1``.

* If a ``default_backend`` is set in the configuration, Cumin will try to first execute the query directly with the
  default backend and only if the query is not parsable with that backend it will parse it with the main grammar.

Backends
^^^^^^^^

The backends are the ones that allow to select the target hosts. Each backend is free to define its own grammar.
Those are the available backends:

* **PuppetDB**: allow to select hosts querying the PuppetDB API for Puppet facts or resources. See the
  :py:class:`cumin.backends.puppetdb.PuppetDBQuery` class documentation for the details.
* **OpenStack**: allow to select hosts querying the OpenStack APIs to select based on project, instance name and so on.
  See the :py:class:`cumin.backends.openstack.OpenStackQuery` class documentation for the details. This is an optional
  backend.
* **KnownHosts**: allow to select hosts listed in multiple SSH known hosts files that are not hashed. See the
  :py:class:`cumin.backends.knownhosts.KnownHostsQuery` class documentation for the details.
* **Direct**: a fallback backend without extenal dependecies with :py:class:`ClusterShell.NodeSet.NodeSet` group
  expansion capabilities. See the :py:class:`cumin.backends.direct.DirectQuery` class documentation for the details.
* **Custom**: is possible to plug-in custom backends developed externally from Cumin, as long as they:

  * are included in the Python ``PATH``.
  * define a ``GRAMMAR_PREFIX`` module constant that doesn't conflict with the other backend prefixes.
  * define a ``query_class`` module variable that points to a class that inherit from
    :py:class:`cumin.backends.BaseQuery`.
  * are listed in the configuration file in the ``plugins->backends`` section, see :ref:`config.yaml`.

  An example of external backend can be found in the source code as part of the tests in the
  ``cumin.tests.unit.backends.external.ok`` module.


Transports
^^^^^^^^^^

The transport layer is the one used to convey the commands to be executed into the selected hosts. The transport
abstraction allow to specify different execution strategies. Those are the available backends:

* **ClusterShell**: SSH transport using the `ClusterShell <https://github.com/cea-hpc/clustershell>`__ Python library.
  See the :py:class:`cumin.transports.clustershell.ClusterShellWorker` class documentation for the details. The root
  user must be able to SSH into the target hosts. It's possible to set SSH-related options in the configuration.

Examples
--------

CLI
^^^

Simple example without fine-tuning the options:

* Execute the single command ``systemctl is-active nginx`` in parallel on all the hosts matching the query for the
  alias ``cp-esams``, as defined in the ``aliases.yaml`` configuration file.

.. code-block:: none

    $ sudo cumin 'A:cp-esams' 'systemctl is-active nginx'
    23 hosts will be targeted:
    cp[3007-3008,3010,3030-3049].esams.wmnet
    Confirm to continue [y/n]? y
    ===== NODE GROUP =====
    (23) cp[3007-3008,3010,3030-3049].esams.wmnet
    ----- OUTPUT of 'systemctl is-active nginx' -----
    active
    ================
    PASS:  |████████████████████████████████████████████████| 100% (23/23) [00:01<00:00, 12.61hosts/s]
    FAIL:  |                                                             |   0% (0/23) [00:01<?, ?hosts/s]
    100.0% (23/23) success ratio (>= 100.0% threshold) for command: 'systemctl is-active nginx'.
    100.0% (23/23) success ratio (>= 100.0% threshold) of nodes successfully executed all commands.

More complex example fine-tuning many of the parameters using the long form of the options for clarity:

* Execute two commands in each host in sequence in a moving window of 2 hosts at a time, moving to the next host 5
  seconds after the previous one has finished.
* Each command will be considered timed out if it takes more than 30 seconds to complete.
* If the percentage of successful hosts goes below 95% at any point it will not schedule any more hosts for execution.

.. code-block:: none

    $ sudo cumin --batch-size 2 --batch-sleep 5 --success-percentage 95 --timeout 30 --mode async \
      '(P{R:class = role::puppetmaster::backend} or P{R:class = role::puppetmaster::frontend}) and not D{rhodium.eqiad.wmnet}' \
      'date' 'ls -la /tmp/foo'
    4 hosts will be targeted:
    puppetmaster[2001-2002].codfw.wmnet,puppetmaster[1001-1002].eqiad.wmnet
    Confirm to continue [y/n]? y
    ===== NODE GROUP =====
    (2) puppetmaster[2001-2002].codfw.wmnet
    ----- OUTPUT -----
    Thu Nov  2 18:45:18 UTC 2017
    ===== NODE GROUP =====
    (1) puppetmaster2002.codfw.wmnet
    ----- OUTPUT -----
    ls: cannot access /tmp/foo: No such file or directory
    ===== NODE GROUP =====
    (1) puppetmaster2001.codfw.wmnet
    ----- OUTPUT -----
    -rw-r--r-- 1 root root 0 Nov  2 18:44 /tmp/foo
    ================
    PASS:  |████████████▌                                      |  25% (1/4) [00:05<00:01,  2.10hosts/s]
    FAIL:  |████████████▌                                      |  25% (1/4) [00:05<00:01,  2.45hosts/s]
    25.0% (1/4) of nodes failed to execute command 'ls -la /tmp/foo': puppetmaster2002.codfw.wmnet
    25.0% (1/4) success ratio (< 95.0% threshold) of nodes successfully executed all commands. Aborting.: puppetmaster2001.codfw.wmnet

Library
^^^^^^^

Simple example without fine-tuning of optional parameters::

    import cumin

    from cumin import query, transport, transports


    # Load configuration files /etc/cumin/config.yaml and /etc/cumin/aliases.yaml (if present).
    config = cumin.Config()
    # Assuming default_backend: direct is set in config.yaml, select with the direct backend 5 hosts.
    hosts = query.Query(config).execute('host[1-5]')
    target = transports.Target(hosts)
    worker = transport.Transport.new(config, target)
    worker.commands = ['systemctl is-active nginx']
    worker.handler = 'sync'
    exit_code = worker.execute()  # Execute the command on all hosts in parallel
    for nodes, output in worker.get_results():  # Cycle over the results
        print(nodes)
        print(output.message().decode())
        print('-----')


More complex example fine-tuning many of the parameters::

    import cumin

    from cumin import query, transport, transports
    from cumin.transports.clustershell import NullReporter


    config = cumin.Config(config='/path/to/custom/cumin/config.yaml')
    hosts = query.Query(config).execute('A:nginx')  # Match hosts defined by the query alias named 'nginx'.
    # Moving window of 5 hosts a time with 30s sleep before adding a new host once the previous one has finished.
    target = transports.Target(hosts, batch_size=5, batch_sleep=30.0)
    worker = transport.Transport.new(config, target)
    worker.commands = [
        transports.Command('systemctl is-active nginx'),
        # In each host, for this command apply a timeout of 30 seconds and consider successful an exit code of 0 or 42.
        transports.Command('depool_command', timeout=30, ok_codes=[0, 42]),
        transports.Command('systemctl restart nginx'),
        transports.Command('systemctl is-active nginx'),
        transports.Command('repool_command', ok_codes=[0, 42]),
        ]
    # On each host perform the above commands in a sequence, only if the previous command was successful.
    worker.handler = 'async'
    # Change the worker's default reporter from the current default that outputs to stdout all commands stdout/err
    # outputs to the empty reporter that does nothing.
    worker.reporter = NullReporter
    # Suppress the progress bars during execution
    worker.progress_bars = False
    exit_code = worker.execute()
    for nodes, output in worker.get_results():
        print(nodes)
        print(output.message().decode())
        print('-----')
