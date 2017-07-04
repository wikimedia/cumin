"""Automation and orchestration framework written in Python."""
from pkg_resources import DistributionNotFound, get_distribution

import yaml


try:
    __version__ = get_distribution(__name__).version
except DistributionNotFound:
    pass  # package is not installed


class CuminError(Exception):
    """Base Exception class for all Cumin's custom Exceptions."""


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
