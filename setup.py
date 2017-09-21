#!/usr/bin/env python
"""Package configuration."""

from setuptools import find_packages, setup


long_description = """
Cumin provides a flexible and scalable automation framework to execute multiple commands on
multiple targets in parallel.
It allows to easily perform complex selections of hosts through a user-friendly query language which can interface
with different backend modules.
The transport layer can also be selected, providing multiple execution strategies.
It can be used both via its command line interface (CLI) and as a Python library.
"""

install_requires = [
    'clustershell==1.7.3',
    'colorama>=0.3.2',
    'keystoneauth1>=2.4.1',
    'pyparsing==2.1.10',
    'python-keystoneclient>=2.3.1',
    'python-novaclient>=3.3.1',
    'pyyaml>=3.11',
    'requests>=2.12.0',
    'tqdm>=4.11.2',
]

tests_require = [
    'bandit>=0.13.2',
    'flake8>=3.2.1',
    'mock>=2.0.0',
    'pytest>=3.0.3',
    'pytest-cov>=1.8.0',
    'pytest-xdist>=1.15.0',
    'requests-mock>=0.7.0',
    'tox>=2.5.0',
    'vulture>=0.6,<0.25',  # Required for https://github.com/landscapeio/prospector/issues/230
]

setup(
    author='Riccardo Coccioli',
    author_email='rcoccioli@wikimedia.org',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: POSIX :: BSD',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 2 :: Only',
        'Programming Language :: Python :: 2.7',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: System :: Clustering',
        'Topic :: System :: Distributed Computing',
        'Topic :: System :: Systems Administration',
    ],
    data_files=[('share/doc/cumin/examples/', ['doc/examples/config.yaml', 'doc/examples/aliases.yaml'])],
    description='Automation and orchestration framework written in Python',
    entry_points={
        'console_scripts': [
            'cumin = cumin.cli:main',
        ],
    },
    extras_require={'tests': tests_require + ['prospector[with_everything]>=0.12.4']},
    install_requires=install_requires,
    keywords=['cumin', 'automation framework', 'orchestration framework'],
    license='GPLv3+',
    long_description=long_description,
    name='cumin',
    packages=find_packages(exclude=['*.tests', '*.tests.*']),
    platforms=['GNU/Linux', 'BSD', 'MacOSX'],
    setup_requires=['pytest-runner>=2.7.1', 'setuptools_scm>=1.15.0'],
    tests_require=tests_require,
    url='https://github.com/wikimedia/cumin',
    use_scm_version=True,
    zip_safe=False,
)
