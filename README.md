# Cumin - An automation and orchestration framework

[![Build Status](https://travis-ci.org/wikimedia/cumin.svg?branch=master)](https://travis-ci.org/wikimedia/cumin)
[![Coveralls Coverage](https://coveralls.io/repos/github/wikimedia/cumin/badge.svg?branch=master)](https://coveralls.io/github/wikimedia/cumin)
[![Codcov Coverage](https://codecov.io/github/wikimedia/cumin/coverage.svg?branch=master)](https://codecov.io/github/wikimedia/cumin)
[![Codacy](https://api.codacy.com/project/badge/Grade/73d9a429dc7343eb935471bf05826fc0)](https://www.codacy.com/app/volans-/cumin)
[![Licence](https://img.shields.io/badge/license-GPLv3%2B-blue.svg)](https://github.com/wikimedia/cumin/blob/master/LICENSE)

## Summary

Cumin provides a flexible and scalable automation framework to execute multiple commands on multiple hosts in parallel.
It allows to easily perform complex selections of hosts through a user-friendly query language which can interface
with different backend modules and combine their results for a fine grained selection.
The transport layer can also be selected, and can provide multiple execution strategies.
It can be used both via its command line interface (CLI) and as a Python library.

More details of `cumin` usage in the Wikimedia Foundation are available on
[Cumin's Wikitech page]( https://wikitech.wikimedia.org/wiki/Cumin).


## Main components

#### Query language

Cumin provides a user-friendly generic query language that allows to combine the results of subqueries for multiple
backends.

- Each query part can be composed with the others using boolean operators (`and`, `or`, `and not`, `xor`).
- Multiple query parts can be grouped together with parentheses (`(`, `)`).
- Specific backend query (`I{backend-specific query syntax}`, where `I` is an identifier for the specific backend).
- Alias replacement, according to aliases defined in the configuration file (`A:group1`).
- The identifier `A` is reserved for the aliases replacement and cannot be used to identify a backend.
- If a default_backend is set in the configuration, it will try to execute the query first directly with the default
  backend and only if the query is not parsable with that backend it will try to execute it with the main grammar.
- A complex query example: `(D{host1 or host2} and (P{R:Class = Role::MyClass} and not A:group1)) or D{host3}`

```
Backus-Naur form (BNF) of the grammar:
        <grammar> ::= <item> | <item> <boolean> <grammar>
           <item> ::= <backend_query> | <alias> | "(" <grammar> ")"
  <backend_query> ::= <backend> "{" <query> "}"
          <alias> ::= A:<alias_name>
        <boolean> ::= "and not" | "and" | "xor" | "or"
```

Given that the `pyparsing` library defines the grammar in a BNF-like style, for the details of the tokens not
specified above check directly the code in `cumin/grammar.py`.

The `Query` class defined in `cumin/query.py` is the one taking care of replacing the aliases, building and executing
the query parts with their respective backends and aggregating the results. Once a query is executed, it returns a
[ClusterShell NodeSet object](http://clustershell.readthedocs.io/en/latest/api/NodeSet.html#ClusterShell.NodeSet.NodeSet).
with the FQDN of the hosts that matches the selection.

#### Backends

All the backends share a minimal common interface that is defined in the `BaseQuery` class defined in
`cumin/backends/__init__.py` and they are instantiated by the `Query` class defined in `cumin/query.py` when building
and executing the query. Each backend module need to define a `query_class` module variable that
is a pointer to the backend class for dynamic instantiation and a `GRAMMAR_PREFIX` constant string that is the
identifier to be used in the main query syntax to identify the backend. The `GRAMMAR_PREFIX` `A` is reserved by the
main grammar for aliases.

##### PuppetDB

This backend uses the PuppetDB API to perform the query. The specific query language has this features:

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
- `>=`: greater than or equal to
- `<=`: less than or equal to
- `<`: less than
- `>`: greater than
- `~`: regexp match

Some query examples:

- All hosts: `*`
- Hosts globbing: `host10*`
- [ClusterShell NodeSet syntax](http://clustershell.readthedocs.io/en/latest/api/NodeSet.html#ClusterShell.NodeSet.NodeSet)
  for hosts expansion: `host10[10-42].domain`
- Category based key-value selection:
  - `R:Resource::Name`: query all the hosts that have a resource of type `Resource::Name`.
  - `R:Resource::Name = 'resource-title'`: query all the hosts that have a resource of type `Resource::Name` whose
    title is `resource-title`. For example `R:Class = MyModule::MyClass`.
  - `R:Resource::Name@field = 'some-value'`: query all the hosts that have a resource of type `Resource::Name` whose
    field `field` has the value `some-value`. The valid fields are: `tag`, `certname`, `type`, `title`, `exported`,
    `file`, `line`. The previous syntax is a shortcut for this one with the field `title`.
  - `R:Resource::Name%param = 'some-value'`: query all the hosts that have a resource of type `Resource::Name` whose
    parameter `param` has the value `some-value`.
  - Mixed facts/resources queries are not supported, but the same result can be achieved by the main grammar using
    multiple subqueries.
- A complex selection for facts:
  `host10[10-42].*.domain or (not F:key1 = value1 and host10*) or (F:key2 > value2 and F:key3 ~ '^value[0-9]+')`

```
Backus-Naur form (BNF) of the grammar:
      <grammar> ::= <item> | <item> <and_or> <grammar>
         <item> ::= [<neg>] <query-token> | [<neg>] "(" <grammar> ")"
  <query-token> ::= <token> | <hosts>
        <token> ::= <category>:<key> [<operator> <value>]
```

Given that the `pyparsing` library used to define the grammar uses a BNF-like style, for the details of the tokens not
specified above see directly the code in `cumin/backends/puppetdb.py`.


##### Direct

The `direct` backend allow to use Cumin without any external dependency for the hosts selection.
It allow to write arbitrarily complex queries with subgroups and boolean operators, but each item must be either the
hostname itself, or the using host expansion using the powerful ClusterShell NodeSet syntax, see:
    https://clustershell.readthedocs.io/en/latest/api/NodeSet.html

The typical usage for the `direct` backend is as a reliable alternative in cases in which the primary host
selection mechanism is not working and also for testing the transports without any external backend dependency.

Some query examples:

- Simple selection: `host1.domain`
- ClusterShell syntax for hosts expansion: `host10[10-42].domain,host2010.other-domain`
- A complex selection:
  `host100[1-5].domain or (host10[30-40].domain and (host10[10-42].domain and not host33.domain))`

```
Backus-Naur form (BNF) of the grammar:
        <grammar> ::= <item> | <item> <boolean> <grammar>
           <item> ::= <hosts> | "(" <grammar> ")"
        <boolean> ::= "and not" | "and" | "xor" | "or"
```

Given that the `pyparsing` library used to define the grammar usesa BNF-like style, for the details of the tokens not
specified above check directly the code in `cumin/backends/direct.py`.


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

## Installation

From the source code in the `master` branch:

    python setup.py install

Is it also possible to build a Debian package using the `debian` branch, for example with `git-buildpackage`.

## Configuration

The default configuration file for `cumin` CLI is expected to be found at `/etc/cumin/config.yaml`; the path can be
changed via a command-line switch, `--config`. A commented example configuration is available in
`doc/examples//config.yaml`.

Cumin will also automatically load any aliases defined in a `aliases.yaml` file, if present in the same directory of
the main configuration file. An aliases example file is available in `doc/examples/aliases.yaml`

## CLI

### Usage

    cumin [OPTIONS] HOSTS COMMAND [COMMAND ...]

### OPTIONS

For the full list of available optional arguments see `cumin --help`.

#### Mode

The `-m/--mode` argument is required when multiple COMMANDS are specified and defines the mode of execution:

* `sync`: execute the first command on all hosts, then proceed with the next one only if `-s/--success-percentage` is
reached.
* `async`: execute on each host, independently from each other, the list of commands, aborting the execution on any given
host at the first command that fails.

### Positional arguments

#### HOSTS

A host selection query according to a custom grammar. The hosts selection query is executed against the configured
backend to extract the list of hosts to use as target.


#### COMMAND
A command to be executed on all the target hosts in parallel, according to the configuration and options selected.

Multiple commands will be executed sequentially.


## Running tests

The `tox` utility, a wrapper around virtualenv, is used to run the test. To list the available environements:

    tox -l

To run one:

    tox -e flake8

You can pass extra arguments to the underlying command, for example to only run the tests in a specific file:

    tox -e unit -- -k test_puppetdb.py

Also integration tests are available, but not run by default by tox. They depends on a running Docker instance.
To run them:

    tox -e integration
