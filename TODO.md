TODO
----

Tracking ideas to improve Cumin. They are in no particular order inside each section
and there is no guarantee that any item listed will be implemented in the nearby future.

## On the masters

##### Internal improvements / bug fixes
* global: add a man page [T159308](https://phabricator.wikimedia.org/T159308)
* CLI: fix progress bar interaction with ctrl+c and sigint_handler()
* CLI: suppress normal output when `-o/--output` is used
* clustershell transport: decouple the output handling from the event handlers
* clustershell transport: improve test coverage for partial/total failures and timeouts
* clustershell transport: improve and extend integration tests

##### Small improvements
* global: allow to log the whole output to a specific file, to allow multiple people follow the progress
* global: allow to randomize the list hosts before execution [T164587](https://phabricator.wikimedia.org/T164587)
* CLI: `--batch-size` allow to specify percentage too
* CLI: improve the dry-run mode to show what would have been done
* CLI: add a `--color` or a `--no-color` option to manage the output color
* CLI: read commands from a file, one per line
* CLI: add `--limit` to randomly select N hosts within a broader selection
* puppetdb backend: improve globbing support, check if fnmatch could be used without conflicting with ClusterShell NodeSet
* puppetdb backend: allow to specify boolean values for resource parameters [T161545](https://phabricator.wikimedia.org/T161545)

##### New Features
* global: connection timeout/failure should be treated differently than normal failures
  * don't consider them for the success threshold by default, add a `--fail-always` option for that
  * if the first command executed on a host fails with exit code 255, try to run `/bin/true`, if it fails too it should be considered a connection timeout/failure
* global: allow to notify the user who launched the execution on failure/termination trough IRC/email. Useful for long running jobs
* global: allow to differentiate the command to execute on a per-host basis, i.e. passing a different parameter for each host.
* global: allow to have an external audit log and/or announce commands execution on IRC
* transports: add an output-only transport to nicely print the matching hosts and some related count
* transports: allow to specify a rollback strategy to be executed in each host on failure
* transports: add parallel execution of local commands on the master for each targeted host with the host as a parameter. Needs a new local transport with ExecWorker to shell out in parallel.
* backends: generalize backends to allow to return other data too, not only the host certnames
* backends: add a new backend to support conftool
* backends: add a new backed to query the known hosts file format
* puppetdb backend: add support for API v4
* CLI: when `-i/--interactive` is used and no command or query is specified, drop into a REPL session allowing to easily setup them.


## On the targets

#### Future plans

* Create a single entry point to allow the execution of idempotent _modules_
* Create a safe and reliable sync up mechanism for the modules
* Allow to handle timeouts and failures locally within the module (local rollback and/or cleanup)
* Allow to drop privileges into a different user
