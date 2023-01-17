Installation
============

PyPI
----

Cumin is available in the `Python Package Index`_ (PyPI) and can be installed via ``pip``:

.. code-block:: none

    pip install cumin

The dependencies of the optional backends are listed in dedicated ``extras_require`` keys in the ``setup.py``. To
install Cumin with the support of an optional backend run for example:

.. code-block:: none

    pip install cumin[with-openstack]


Debian package
--------------

Cumin is included in Debian (and derived distributions based on it) starting with version 12 (bookworm) and can
be installed via the ``cumin`` package.

To build the Debian package from the source code you can get it from the `Debian package repository`_ (Salsa),
it can be build using ``gbp buildpackage``. The dependencies for the optional OpenStack backend are listed
as ``Suggested`` packages, i.e. you need to deploy them by yourself if you want to use the OpenStack backend.

Source code
-----------

A gzipped tar archive of the source code for each release is available for download on the `Release page`_ on GitHub,
along with its GPG signature. The source code repository is available from `Wikimedia's Gerrit`_ website and mirrored
on `GitHub`_. To install it, from the ``master`` branch run:

.. code-block:: none

    python setup.py install


.. _`Python Package Index`: https://pypi.org/project/cumin/
.. _`Wikimedia's Gerrit`: https://gerrit.wikimedia.org/r/#/admin/projects/operations/software/cumin
.. _`GitHub`: https://github.com/wikimedia/cumin
.. _`Release page`: https://github.com/wikimedia/cumin/releases
.. _`Debian package repository`: https://salsa.debian.org/python-team/packages/cumin
