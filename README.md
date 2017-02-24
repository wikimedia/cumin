Cumin - An automation and orchestration framework
=======================

[![Build Status](https://travis-ci.org/wikimedia/cumin.svg?branch=master)](https://travis-ci.org/wikimedia/cumin)
[![Coveralls Coverage](https://coveralls.io/repos/github/wikimedia/cumin/badge.svg?branch=master)](https://coveralls.io/github/wikimedia/cumin)
[![Codcov Coverage](https://codecov.io/github/wikimedia/cumin/coverage.svg?branch=master)](https://codecov.io/github/wikimedia/cumin)
[![Codacy](https://api.codacy.com/project/badge/Grade/73d9a429dc7343eb935471bf05826fc0)](https://www.codacy.com/app/volans-/cumin)
[![Licence](https://img.shields.io/badge/license-GPLv3%2B-blue.svg)](https://github.com/wikimedia/cumin/blob/master/LICENSE)

Summary
-------

Cumin provides a flexible and scalable automation framework to execute multiple commands on multiple hosts in parallel.
It allows to easily perform complex selections of hosts through a user-friendly query language which can interface
with different backend modules.
The transport layer can also be selected, also providing multiple execution strategies.
It can be used both via its command line interface (CLI) and as a Python library.

More details of `cumin` usage in the Wikimedia Foundation are available on
[Cumin's Wikitech page]( https://wikitech.wikimedia.org/wiki/Cumin).


Main components
---------------

#### Query language

Cumin provides a user-friendly and unified query language to select hosts using different backends with the following
features:

- Each query part can be composed with the others using boolean operators (`and`, `or`, `not`)
- Multiple query parts can be grouped together with parentheses (`(`, `)`).
- A query part can be of two different types:
  - `Hostname matching`: this is a simple string that be used to match directly the hostname of the hosts in the
    selected backend. It allows for glob expansion (`*`) and the use of the powerful
    [ClusterShell NodeSet syntax](http://clustershell.readthedocs.io/en/latest/api/NodeSet.html#ClusterShell.NodeSet.NodeSet).
  - `Category matching`: an identifier composed by a category, a colon and a key, followed by a comparison operator and
    a value, as in `F:key = value`.

The available categories are:

- `F`: for querying facts
- `R`: for querying resources

The available operators are:

- `=`: equality
- `!=`: inequality
- `>=`: greater than or equal to
- `<=`: less than or equal to
- `<`: less than
- `>`: greater than
- `~`: regexp match

The actual capabilities varies with the chosen backend. Such as the meaning of the key and values in facts and
resources queries.

Some query examples:

- All hosts: `*`
- Hosts globbing: `host10*`
- [ClusterShell NodeSet syntax](http://clustershell.readthedocs.io/en/latest/api/NodeSet.html#ClusterShell.NodeSet.NodeSet)
  for hosts expansion: `host10[10-42].domain`
- Category based key-value selection: `R:ResourceName = ResourceValue`
- A complex selection for facts:
  `host10[10-42].*.domain or (not F:key1 = value1 and host10*) or (F:key2 > value2 and F:key3 ~ '^value[0-9]+')`

Backus-Naur form (BNF) of the grammar:

          <query> ::= <item> | <item> <and_or> <query>
           <item> ::= [<neg>] <query-token> | [<neg>] "(" <query> ")"
    <query-token> ::= <token> | <hosts>
          <token> ::= <category>:<key> [<operator> <value>]

Given that the `pyparsing` library used to defines the grammar uses a BNF-like style, for the details of the tokens not
specified above see directly the code in `cumin/grammar.py`.

The `QueryBuilder` class defined in `cumin/query.py` is the one taking care of creating an instance of the chosen
backend, parse the given query and calling the respective methods of the backend instance.
Once a query is executed, it returns the list of hostnames that matches the selection.

#### Backends

All the backends share a common interface that is defined in the `BaseQuery` class defined in
`cumin/backends/__init__.py` and they are instantiated through the `Query` factory class defined in `cumin/query.py`
that is called by the `QueryBuilder` class. Each backend module need to define a `query_class` module variable that
is a pointer to the backend class for dynamic instantiation.

##### PuppetDB

This backend uses the PuppetDB API to perform the query. The specific features/limitations of this backend are:
- `R:Resource::Name`: query all the hosts that have a resource of type `Resource::Name`.
- `R:Resource::Name = 'resource-title'`: query all the hosts that have a resource of type `Resource::Name` whose
title is `resource-title`. For example `R:Class = MyModule::MyClass`.
- `R:Resource::Name@field = 'some-value'`: query all the hosts that have a resource of type `Resource::Name` whose
field `field` has the value `some-value`. The valid fields are: `tag`, `certname`, `type`, `title`, `exported`, `file`,
`line`. The previous syntax is a shortcut for this one with the field `title`.
- `R:Resource::Name%param = 'some-value'`: query all the hosts that have a resource of type `Resource::Name` whose
parameter `param` has the value `some-value`.
- Available operators: all but `!=`.
- Available categories: all, but mixed facts/resources queries are not supported yet.

##### Direct

This is the simplest backend, it just performs the
[ClusterShell syntax](http://clustershell.readthedocs.io/en/latest/api/NodeSet.html#ClusterShell.NodeSet.NodeSet)
expansion and doesn't support facts or resources queries. It has no dependencies, and is meant to be used as a fallback
backend in case the default one is not available or in installations where there is no centralized hosts catalog.


#### Transports

The transport layer is the one used to convey the commands to be executed into the selected hosts.
The transport abstraction allow to specify a mode to choose the execution plan, an event handler class and a success
threshold. Those can be used by the chosen transport to customize the behavior of the execution plan.

All the transports share a common interface that is defined in the `BaseWorker` class defined in
`cumin/transports/__init__.py` and they are instantiated through the `Transport` factory class defined in
`cumin/transport.py`. Each backend module need to define a `worker_class` module variable that is a pointer to the
transport class for dynamic instantiation.

##### ClusterShell

This transport uses the [ClusterShell](https://github.com/cea-hpc/clustershell) Python library to connect to the
selected hosts and execute a list of commands. This transport accept the following customizations:
- `sync` execution mode: given a list of commands, the first one will be executed on all the hosts, then, if the
  success ratio is reached, the second one will be executed on all hosts where the first one was successful, and so on
- `async` execution mode: given a list of commands, on each hosts the commands will be executed sequentially,
  interrupting the execution on any single host at the first command that fails. The execution on the hosts is
  independent between each other.
- custom execution mode: can be achieved creating a custom event handler class that extends the `BaseEventHandler`
  class defined in `cumin/transports/clustershell.py`, implementing its abstract methods and setting to this class
  object the handler to the transport.

Installation
------------

    python setup.py install


CLI
===

Configuration
-------------

The default configuration file for `cumin` CLI is expected to be found at `/etc/cumin/config.yaml`; the path can be
changed via a command-line switch, `--config`. A commented example configuration is available in
`cumin/config.yaml`.

Usage
-----

    cumin [OPTIONS] HOSTS COMMAND [COMMAND ...]

#### OPTIONS

For the full list of available optional arguments see `cumin --help`.

##### Mode

The `-m/--mode` argument is required when multiple COMMANDS are specified and defines the mode of execution:

* `sync`: execute the first command on all hosts, then proceed with the next one only if `-s/--success-percentage` is
reached.
* `async`: execute on each host, independently from each other, the list of commands, aborting the execution on any given
host at the first command that fails.

#### Positional arguments

##### HOSTS

A host selection query according to a custom grammar. The hosts selection query is executed against the configured
backend to extract the list of hosts to use as target.


##### COMMAND
A command to be executed on all the target hosts in parallel, according to the configuration and options selected.

Multiple commands will be executed sequentially.


Running tests
-------------

We use the `tox` utility, a wrapper around virtualenv. To list available
environements:

    tox -l

To run one:

    tox -e flake8

You can pass extra arguments to the underlying command, for example to only run
the unit tests:

    tox -e py27 -- --test-suite cumin.tests.unit
