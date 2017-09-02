"""Transport factory."""

import importlib

from cumin import CuminError


class Transport(object):
    """Transport factory class.

    The transport layer is the one used to convey the commands to be executed into the selected hosts. The transport
    abstraction allow to specify a mode to choose the execution plan, an event handler class and a success threshold.
    Those can be used by the chosen transport to customize the behavior of the execution plan.

    All the transports share a common interface that is defined in the :py:class:`cumin.transports.BaseWorker` class
    and they are instantiated through the :py:class:`cumin.transport.Transport` factory class. Each transport module
    need to define a ``worker_class`` module variable that is a pointer to the transport class for dynamic
    instantiation.
    """

    @staticmethod
    def new(config, target):
        """Create a transport worker class based on the configuration (`factory`).

        Arguments:
            config (dict): the configuration dictionary.
            target (cumin.transports.Target): a Target instance.

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
            return module.worker_class(config, target)
        except (AttributeError, ImportError) as e:
            raise CuminError("Unable to load worker class for transport '{transport}': {msg}".format(
                transport=config['transport'], msg=repr(e))) from e
