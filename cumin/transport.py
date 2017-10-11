"""Transport factory."""

import importlib

from cumin import CuminError


class Transport(object):
    """Transport factory class."""

    @staticmethod
    def new(config, target, logger=None):
        """Create a transport worker class based on the configuration (`factory`).

        Arguments:
            config (dict): the configuration dictionary.
            target (cumin.transports.Target): a Target instance.
            logger (logging.Logger, optional): an optional logger instance.

        Returns:
            BaseWorker: the created worker instance for the configured transport.

        Raises:
            cumin.CuminError: if the configuration is missing the required ``transport`` key.
            exceptions.ImportError: if unable to import the transport module.
            exceptions.AttributeError: if the transport module is missing the required ``worker_class`` attribute.

        """
        if 'transport' not in config:
            raise CuminError("Missing required parameter 'transport' in the configuration dictionary")

        try:
            module = importlib.import_module('cumin.transports.{transport}'.format(transport=config['transport']))
            return module.worker_class(config, target, logger=logger)
        except (AttributeError, ImportError) as e:
            e.message = "Unable to load worker class for transport '{transport}': {msg}".format(
                transport=config['transport'], msg=repr(e))
            raise
