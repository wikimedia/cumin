import importlib


class Transport(object):
    """Transport factory class"""

    @staticmethod
    def new(config, logger=None):
        """ Return an instance of the worker class for the configured transport

            Arguments:
            config - the configuration dictionary
            logger - an optional logging instance [optional, default: None]
        """
        try:
            module = importlib.import_module('cumin.transports.{transport}'.format(transport=config['transport']))
            return module.worker_class(config, logger)
        except (AttributeError, ImportError) as e:
            raise RuntimeError("Unable to load worker class for transport '{transport}': {msg}".format(
                transport=config['transport'], msg=repr(e)))
