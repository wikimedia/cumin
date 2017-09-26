"""Transport factory."""

import importlib

from cumin import CuminError


class Transport(object):
    """Transport factory class."""

    @staticmethod
    def new(config, target, logger=None):
        """Return an instance of the worker class for the configured transport.

        Arguments:
        config -- the configuration dictionary
        target -- a Target instance
        logger -- an optional logging instance [optional, default: None]
        """
        if 'transport' not in config:
            raise CuminError("Missing required parameter 'transport' in the configuration dictionary")

        try:
            module = importlib.import_module('cumin.transports.{transport}'.format(transport=config['transport']))
            return module.worker_class(config, target, logger=logger)
        except (AttributeError, ImportError) as e:
            raise RuntimeError("Unable to load worker class for transport '{transport}': {msg}".format(
                transport=config['transport'], msg=repr(e)))
