"""Automation and orchestration framework written in Python."""
import logging
import os
import subprocess

import yaml

from ClusterShell.NodeSet import NodeSet, RESOLVER_NOGROUP
from pkg_resources import DistributionNotFound, get_distribution


KERBEROS_KLIST = '/usr/bin/klist'
try:  # TODO: use importlib.metadata once Python 3.7 support is dropped
    __version__ = get_distribution(__name__).version
    """:py:class:`str`: the version of the current Cumin module."""
except DistributionNotFound:  # pragma: no cover - this happens only if the package is not installed
    # Support the use case of the Debian building system where tests are run without installation
    if 'SETUPTOOLS_SCM_PRETEND_VERSION' in os.environ:
        __version__ = os.environ['SETUPTOOLS_SCM_PRETEND_VERSION']


class CuminError(Exception):
    """Base Exception class for all Cumin's custom Exceptions."""


##############################################################################
# Add a custom log level TRACE to logging for development debugging

LOGGING_TRACE_LEVEL_NUMBER = 8
LOGGING_TRACE_LEVEL_NAME = 'TRACE'


# Fail if the custom logging slot is already in use with a different name or
# Access to a private property of logging was preferred over matching the default string returned by
# logging.getLevelName() for unused custom slots.
if (LOGGING_TRACE_LEVEL_NUMBER in logging._levelToName  # pylint: disable=protected-access
        and LOGGING_TRACE_LEVEL_NAME not in logging._nameToLevel):  # pylint: disable=protected-access
    raise CuminError("Unable to set custom logging for trace, logging level {level} is alredy set for '{name}'.".format(
        level=LOGGING_TRACE_LEVEL_NUMBER, name=logging.getLevelName(LOGGING_TRACE_LEVEL_NUMBER)))


def trace(self, msg, *args, **kwargs):
    """Additional logging level for development debugging.

    :Parameters:
        according to :py:class:`logging.Logger` interface for log levels.

    """
    if self.isEnabledFor(LOGGING_TRACE_LEVEL_NUMBER):
        self._log(LOGGING_TRACE_LEVEL_NUMBER, msg, args, **kwargs)  # pragma: no cover, pylint: disable=protected-access


# Install the trace method and it's logging level if not already present
if LOGGING_TRACE_LEVEL_NAME not in logging._nameToLevel:  # pylint: disable=protected-access
    logging.addLevelName(LOGGING_TRACE_LEVEL_NUMBER, LOGGING_TRACE_LEVEL_NAME)
if not hasattr(logging.Logger, 'trace'):
    logging.Logger.trace = trace  # type: ignore
##############################################################################


class Config(dict):
    """Singleton-like dictionary class to load the configuration from a given path only once."""

    _instances = {}  # Keep track of different loaded configurations

    def __new__(cls, config='/etc/cumin/config.yaml'):
        """Load the given configuration if not already loaded and return it.

        Called by Python's data model for each new instantiation of the class.

        Arguments:
            config (str, optional): path to the configuration file to load.

        Returns:
            dict: the configuration dictionary.

        Examples:
            >>> import cumin
            >>> config = cumin.Config()

        """
        if config not in cls._instances:
            cls._instances[config] = parse_config(config)
            alias_file = os.path.join(os.path.dirname(config), 'aliases.yaml')
            if os.path.isfile(alias_file):  # Load the aliases only if present
                cls._instances[config]['aliases'] = parse_config(alias_file)

        return cls._instances[config]


def parse_config(config_file):
    """Parse the YAML configuration file.

    Arguments:
        config_file (str): the path of the configuration file to load.

    Returns:
        dict: the configuration dictionary.

    Raises:
        CuminError: if unable to read or parse the configuration.

    """
    try:
        with open(os.path.expanduser(config_file), 'r', encoding='utf8') as f:
            config = yaml.safe_load(f)
    except IOError as e:
        raise CuminError('Unable to read configuration file: {message}'.format(message=e)) from e
    except yaml.parser.ParserError as e:
        raise CuminError("Unable to parse configuration file '{config}':\n{message}".format(
            config=config_file, message=e)) from e

    if config is None:
        config = {}

    return config


def nodeset(nodes=None):
    """Instantiate a ClusterShell NodeSet with the resolver defaulting to :py:const:`RESOLVER_NOGROUP`.

    This allow to avoid any conflict with Cumin grammars.

    Returns:
        ClusterShell.NodeSet.NodeSet: the instantiated NodeSet.

    See Also:
        https://github.com/cea-hpc/clustershell/issues/368

    """
    return NodeSet(nodes=nodes, resolver=RESOLVER_NOGROUP)


def nodeset_fromlist(nodelist):
    """Instantiate a ClusterShell NodeSet from a list with the resolver defaulting to :py:const:`RESOLVER_NOGROUP`.

    This allow to avoid any conflict with Cumin grammars.

    Returns:
        ClusterShell.NodeSet.NodeSet: the instantiated NodeSet.

    See Also:
        https://github.com/cea-hpc/clustershell/issues/368

    """
    return NodeSet.fromlist(nodelist, resolver=RESOLVER_NOGROUP)


def ensure_kerberos_ticket(config: Config) -> None:
    """Ensure that there is a valid Kerberos ticket for the current user, according to the given configuration.

    Arguments:
        config (cumin.Config): the Cumin's configuration dictionary.

    """
    kerberos_config = config.get('kerberos', {})
    if not kerberos_config or not kerberos_config.get('ensure_ticket', False):
        return

    if not kerberos_config.get('ensure_ticket_root', False) and os.geteuid() == 0:
        return

    if not os.access(KERBEROS_KLIST, os.X_OK):
        raise CuminError('The Kerberos config ensure_ticket is set to true, but {klist} executable was '
                         'not found.'.format(klist=KERBEROS_KLIST))

    try:
        subprocess.run([KERBEROS_KLIST, '-s'], check=True)  # nosec
    except subprocess.CalledProcessError as e:
        raise CuminError('The Kerberos config ensure_ticket is set to true, but no active Kerberos ticket was found, '
                         "please run 'kinit' and retry.") from e
