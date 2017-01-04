TODO
----

## On the masters

##### First improvements

* clustershell transport: add batch size/fanout support
* CLI: add an option to get raw output for easy post-processing by command line tools
* CLI: read commands from a file, one per line
* CLI: fix progress bar interaction with ctrl+c and sigint_handler()
* global: improve logging in modules
* clustershell transport: decouple the output handling from the event handlers (in progress)
* clustershell transport: improve test coverage for partial/total failures and timeouts
* CLI: add a --color option, don't use colors by default
* CLI: read default options also from CUMIN_OPTIONS environmental variable or a config file in the /home directory
* global: allow to log the whole output to a specific file, to allow multiple people to follow the progress
* puppetdb: improve globbing support, check if fnmatch could be used without conflicting with ClusterShell NodeSet

##### Next improvements

* transports: add an output-only transport to nicely print the matching hosts and some related count
* backends: generalize backends to allow to return other data too, not only the host certnames
* backends: add a new backed to query the known hosts file format
* puppetdb backend: add support for mixed facts/resources queries
* integrate with monitoring and alerting tools
* allow to specify a rollback strategy
* CLI: allow to have an external audit log, for example IRC/SAL
* CLI: improve the dry-run mode to show what would have been done

## On the targets

##### Next improvements

* Create a single entry point to execute modules
* Create a safe and reliable sync up mechanism for the modules
* Allow to handle timeouts and failures locally within the module (local rollback and/or cleanup)
