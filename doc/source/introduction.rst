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
  See the :py:class:`cumin.transports.clustershell.ClusterShellWorker` class documentation for the details. It's
  possible to set all SSH-related options in the configuration file, also passing directly an existing ssh_config file.

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
    OK to proceed on 23 hosts? Enter the number of affected hosts to confirm or "q" to quit: 23
    ===== NODE GROUP =====
    (23) cp[3007-3008,3010,3030-3049].esams.wmnet
    ----- OUTPUT for command #1: 'systemctl is-active nginx' -----
    active
    ================
    PASS:  |████████████████████████████████████████████████| 100% (23/23) [00:01<00:00, 12.61hosts/s]
    FAIL:  |                                                             |   0% (0/23) [00:01<?, ?hosts/s]
    100.0% (23/23) success ratio (>= 100.0% threshold) for command #1: 'systemctl is-active nginx'.
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
    OK to proceed on 4 hosts? Enter the number of affected hosts to confirm or "q" to quit: 4
    ===== NODE GROUP =====
    (2) puppetmaster[2001-2002].codfw.wmnet
    ----- OUTPUT for command #1: 'date'-----
    Thu Nov  2 18:45:18 UTC 2017
    ================
    ===== NODE GROUP =====
    (1) puppetmaster2002.codfw.wmnet
    ----- OUTPUT for command #2: 'ls -la /tmp/foo' -----
    ls: cannot access /tmp/foo: No such file or directory
    ===== NODE GROUP =====
    (1) puppetmaster2001.codfw.wmnet
    ----- OUTPUT for command #2: 'ls -la /tmp/foo' -----
    -rw-r--r-- 1 root root 0 Nov  2 18:44 /tmp/foo
    ================
    PASS:  |████████████▌                                      |  25% (1/4) [00:05<00:01,  2.10hosts/s]
    FAIL:  |████████████▌                                      |  25% (1/4) [00:05<00:01,  2.45hosts/s]
    25.0% (1/4) of nodes failed to execute command #2: 'ls -la /tmp/foo': puppetmaster2002.codfw.wmnet
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
    worker.commands = ['ls /tmp/out']
    worker.handler = 'sync'

    results = worker.run()  # Execute the command on all hosts in parallel

The results object is an instance of :py:class:`cumin.transports.ExecutionResults` and allows to retrieve all
the information of the execution run::

    >>> results.return_code
    0
    >>> results.status
    <ExecutionStatus.SUCCEEDED: 0>
    >>> results.last_executed_command_index
    0
    >>> results.has_no_outputs
    False
    >>> command_results = results.commands_results[0]
    >>> command_results.command_index
    0
    >>> command_results.has_no_outputs
    False
    >>> command_results.has_single_output
    True
    >>> output = command_results.get_single_output()
    >>> output.stdout()
    '/tmp/out'
    >>> command_results.get_host_output('host1').stdout()
    '/tmp/out'
    >>> for group_output in command_results.outputs:
    ...     print(f'Hosts: {group_output.hosts}, Output: {group_output.output.stdout()}')
    ...
    Hosts: host[1-5], Output: /tmp/out
    >>> command_targets = command_results.targets
    >>> command_targets.counters.total
    5
    >>> dict(command_targets.counters.by_return_code)
    {0: 5}
    >>> dict(command_targets.counters.by_state)
    {<HostState.SUCCESS: 'success'>: 5}
    >>> str(command_targets.hosts.all)
    'host[1-5]'
    >>> {return_code: str(hosts) for return_code, hosts in command_targets.hosts.by_return_code.items()}
    {0: 'host[1-5]'}
    >>> {return_code: str(hosts) for return_code, hosts in command_targets.hosts.by_state.items()}
    {<HostState.SUCCESS: 'success'>: 'host[1-5]'}
    >>> host1_results = results.hosts_results['host1']
    >>> host1_results.commands
    (cumin.transports.Command('ls /tmp/out'),)
    >>> host1_results.completed
    True
    >>> host1_results.last_executed_command_index
    0
    >>> host1_results.name
    'host1'
    >>> host1_results.outputs[0].stdout()
    '/tmp/out'
    >>> host1_results.return_codes
    (0,)
    >>> host1_results.state
    <HostState.SUCCESS: 'success'>

More complex example fine-tuning many of the parameters for the execution::

    import cumin

    from cumin import query, transport, transports
    from cumin.transports.clustershell import NullReporter


    config = cumin.Config(config='/path/to/custom/cumin/config.yaml')
    hosts = query.Query(config).execute('A:nginx')  # Match hosts defined by the query alias named 'nginx'.
    # Needed only if SSH is authenticated via Kerberos and the related configuration flags are set
    # (see also the example configuration).
    cumin.ensure_kerberos_ticket(config)
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
    results = worker.run()

Old API to execute commands and retrieve their output, currently soft-deprecated (without raising warnings), it will
be officially deprecated raising a ``DeprecationWarning`` in a subsequent release and removed completely in a future
release::

    exit_code = worker.execute()
    for nodes, output in worker.get_results():
        print(nodes)
        print(output.message().decode())
        print('-----')
