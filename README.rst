Cumin - An automation and orchestration framework
-------------------------------------------------

|GitHub Release| |PyPI Release| |Build Status| |Coveralls Coverage| |Codcov Coverage| |Codacy| |License|

Cumin provides a flexible and scalable automation framework to execute multiple commands on multiple hosts in parallel.

It allows to easily perform complex selections of hosts through a user-friendly query language which can interface
with different backend modules and combine their results for a fine grained selection. The transport layer can also be
selected, and can provide multiple execution strategies. The executed commands outputs are automatically grouped for an
easy-to-read result.

It can be used both via its command line interface (CLI) `cumin` and as a Python 3 only library.
Cumin was Python 2 only before the 3.0.0 release, due to ClusterShell not yet being Python 3 compatible.


|Cumin GIF|

The documentation is available on `Wikimedia Documentation`_ and `Read the Docs`_. The details on how Cumin it's used
at the Wikimedia Foundation are available on `Wikitech`_.


.. |GitHub Release| image:: https://img.shields.io/github/release/wikimedia/cumin.svg
   :target: https://github.com/wikimedia/cumin/releases
.. |PyPI Release| image:: https://img.shields.io/pypi/v/cumin.svg
   :target: https://pypi.org/project/cumin/
.. |Build Status| image:: https://travis-ci.org/wikimedia/cumin.svg?branch=master
   :target: https://travis-ci.org/wikimedia/cumin
.. |Coveralls Coverage| image:: https://coveralls.io/repos/github/wikimedia/cumin/badge.svg?branch=master
   :target: https://coveralls.io/github/wikimedia/cumin
.. |Codcov Coverage| image:: https://codecov.io/github/wikimedia/cumin/coverage.svg?branch=master
   :target: https://codecov.io/github/wikimedia/cumin
.. |Codacy| image:: https://api.codacy.com/project/badge/Grade/73d9a429dc7343eb935471bf05826fc0
   :target: https://www.codacy.com/app/volans-/cumin
.. |License| image:: https://img.shields.io/badge/license-GPLv3%2B-blue.svg
   :target: https://github.com/wikimedia/cumin/blob/master/LICENSE
.. |Cumin GIF| image:: https://people.wikimedia.org/~volans/cumin.gif

.. _`Read the Docs`: https://cumin.readthedocs.io
.. _`Wikimedia Documentation`: https://doc.wikimedia.org/cumin
.. _`Wikitech`: https://wikitech.wikimedia.org/wiki/Cumin
