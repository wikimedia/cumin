#!/usr/bin/env python
"""Package configuration."""

from setuptools import find_packages, setup

setup(
    name='cumin',
    version='0.0.2',
    description='Cumin - An automation and orchestration framework',
    author='Riccardo Coccioli',
    author_email='rcoccioli@wikimedia.org',
    url='https://github.com/wikimedia/operations-software-cumin',
    install_requires=['clustershell==1.7.3', 'colorama', 'pyparsing==2.1.10', 'pyyaml', 'requests', 'tqdm'],
    test_suite='nose.collector',
    tests_require=['mock', 'nose', 'requests-mock'],
    zip_safe=False,
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'cumin = cumin.cli:main',
        ],
    },
)
