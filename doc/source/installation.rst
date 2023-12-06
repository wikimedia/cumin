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

Starting from Debian 12 (*"bookworm"*) Cumin is available directly from the official `Debian repositories`_.

The Debian package for each release is also available for download on the `Release page`_ on GitHub, along with its GPG
signature. To build the Debian package from the source code use ``gbp buildpackage`` in the ``debian`` branch. See the
`Source code`_ section on how to get the source code. The dependencies of the optional backends are listed as
``Suggested`` packages.


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
.. _`Debian repositories`: https://packages.debian.org/search?keywords=cumin&searchon=names&exact=1&suite=all&section=all
