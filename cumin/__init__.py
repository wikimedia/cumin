"""Automation and orchestration framework written in Python."""
import logging
import os
import pkgutil

from pkg_resources import DistributionNotFound, get_distribution

import yaml


try:
    __version__ = get_distribution(__name__).version
except DistributionNotFound:
    pass  # package is not installed


class CuminError(Exception):
    """Base Exception class for all Cumin's custom Exceptions."""


##############################################################################
# Add a custom log level TRACE to logging for development debugging

LOGGING_TRACE_LEVEL_NUMBER = 8
LOGGING_TRACE_LEVEL_NAME = 'TRACE'


# Fail if the custom logging slot is already in use with a different name or
# Access to a private property of logging was preferred over matching the default string returned by
# logging.getLevelName() for unused custom slots.
if (LOGGING_TRACE_LEVEL_NUMBER in logging._levelNames and  # pylint: disable=protected-access
        LOGGING_TRACE_LEVEL_NAME not in logging._levelNames):  # pylint: disable=protected-access
    raise CuminError("Unable to set custom logging for trace, logging level {level} is alredy set for '{name}'.".format(
        level=LOGGING_TRACE_LEVEL_NUMBER, name=logging.getLevelName(LOGGING_TRACE_LEVEL_NUMBER)))


def trace(self, msg, *args, **kwargs):
    """Additional logging level for development debugging."""
    if self.isEnabledFor(LOGGING_TRACE_LEVEL_NUMBER):
        self._log(LOGGING_TRACE_LEVEL_NUMBER, msg, args, **kwargs)  # pylint: disable=protected-access


# Install the trace method and it's logging level if not already present
if LOGGING_TRACE_LEVEL_NAME not in logging._levelNames:  # pylint: disable=protected-access
    logging.addLevelName(LOGGING_TRACE_LEVEL_NUMBER, LOGGING_TRACE_LEVEL_NAME)
if not hasattr(logging.Logger, 'trace'):
    logging.Logger.trace = trace
##############################################################################


class Config(dict):
    """Singleton-like dictionary class to load the configuration from a given path only once."""

    _instances = {}  # Keep track of different loaded configurations

    def __new__(cls, config='/etc/cumin/config.yaml'):
        """Load the given configuration if not already loaded and return it.

        Called by Python's data model for each new instantiation of the class.

        Arguments:
        config -- path to the configuration file to load. [optional, default: /etc/cumin/config.yaml]
        """
        if config not in cls._instances:
            cls._instances[config] = parse_config(config)
            load_backend_aliases(cls._instances[config], os.path.dirname(config))

        return cls._instances[config]


def parse_config(config_file):
    """Parse the YAML configuration file.

    Arguments:
    config_file -- the path of the configuration file to load
    """
    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
    except IOError as e:
        raise CuminError('Unable to read configuration file: {message}'.format(message=e))
    except yaml.parser.ParserError as e:
        raise CuminError("Unable to parse configuration file '{config}':\n{message}".format(
            config=config_file, message=e))

    if config is None:
        raise CuminError("Empty configuration found in '{config}'".format(config=config_file))

    return config


def load_backend_aliases(config, base_path):
    """Given a configuration, automatically add backend aliases from configuration files in the base_path directory.

    It will look for files named {backend}_aliases.yaml in the base_path directory and will load it's content into the
    main configuration under the 'aliases' key under the backend specific configuration, so that it will be accessible
    by config[backend]['aliases'].

    Arguments:
    config    -- the configuration object to add the aliases to.
    base_path -- the base path where to look for the aliases files.
    """
    abs_path = os.path.dirname(os.path.abspath(__file__))
    backends = [name for _, name, _ in pkgutil.iter_modules([os.path.join(abs_path, 'backends')])]

    for backend in backends:
        alias_file = os.path.join(base_path, '{backend}_aliases.yaml'.format(backend=backend))
        if os.path.isfile(alias_file):  # Do not fail if the alias file doesn't exists
            if config.get(backend) is None:
                config[backend] = {}

            config[backend]['aliases'] = parse_config(alias_file)
