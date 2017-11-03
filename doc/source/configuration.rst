Configuration
=============

.. _config.yaml:

config.yaml
-----------

The default configuration file for ``cumin`` is expected to be found at ``/etc/cumin/config.yaml``. Its path can
be changed in the CLI via the command-line switch ``--config PATH``. A commented example configuration is available in
the source code at ``doc/examples/config.yaml`` and included here below:

.. literalinclude:: ../examples/config.yaml
   :language: yaml

The example file is also shipped, depending on the installation method, to:

* ``$VENV_PATH/share/doc/cumin/examples/config.yaml`` when installed in a Python ``virtualenv`` via ``pip``.
* ``/usr/local/share/doc/cumin/examples/config.yaml`` when installed globally via ``pip``.
* ``/usr/share/doc/cumin/examples/config.yaml`` when installed via the Debian package.

aliases.yaml
------------

Cumin will also automatically load any aliases defined in a ``aliases.yaml`` file, if present in the same directory
of the main configuration file. An aliases example file is available in the source code at
``doc/examples/aliases.yaml`` and included here below:

.. literalinclude:: ../examples/aliases.yaml
   :language: yaml

The file is also shipped in the same directory of the example configuration file, see `config.yaml`_.
