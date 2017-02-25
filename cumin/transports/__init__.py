"""Abstract transport."""

import logging
import os

from abc import ABCMeta, abstractmethod


class BaseWorker(object):
    """Worker interface."""

    __metaclass__ = ABCMeta

    def __init__(self, config, logger=None):
        """Worker constructor. Setup environment variables.

        Arguments:
        config -- a dictionary with the parsed configuration file
        logger -- an optional logger instance [optional, default: None]
        """
        self.config = config
        self.logger = logger or logging.getLogger(__name__)

        environment = config.get(config.get('transport', ''), {}).get('environment', {})
        for key, value in environment.iteritems():
            os.environ[key] = value

    @abstractmethod
    def execute(self, hosts, commands, mode=None, handler=None, timeout=0, success_threshold=1):
        """Execute the given commands on the given hosts.

        Arguments:
        hosts             -- a list of hosts to target for the execution of the commands
        commands          -- a list of commands to be executed on the hosts
        mode              -- the mode of operation, needed only when more than one command is specified. It depends
                             on the actual transport chosen. Typical values are: sync, async.
                             [optional, default: None]
        handler           -- an event handler to be notified of the progress during execution. Its interface
                             depends on the actual transport chosen. Accepted values are: None => don't use an
                             event handler (default), True => use the transport's default event hander, an event
                             handler class. [optional, default: None]
        timeout           -- the timeout in seconds for the whole execution. [optional, default: 0 (unlimited)]
        success_threshold -- The success ratio threshold that must be reached to consider the run successful. A
                             float between 0 and 1. The specific meaning might change based on the chosen transport.
                             [optional, default: 1]
        """

    @abstractmethod
    def get_results(self):
        """Generator that yields the results of the current execution."""
