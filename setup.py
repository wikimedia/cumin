#!/usr/bin/env python
"""Package configuration."""
import os

from setuptools import find_packages, setup


with open('README.rst', 'r') as readme:
    long_description = readme.read()

# Required dependencies
install_requires = [
    'clustershell==1.8',
    'colorama>=0.3.2',
    'pyparsing==2.1.10',
    'pyyaml>=3.11',
    'requests>=2.11.0',
    'tqdm>=4.11.2',
]

# Extra dependencies
extras_require = {
    # Optional dependencies for additional features
    'with-openstack': [
        'keystoneauth1>=2.4.1',
        'python-keystoneclient>=2.3.1',
        'python-novaclient>=3.3.1',
    ],

    # Test dependencies
    'tests': [
        'bandit>=1.1.0',
        'flake8>=3.2.1',
        'prospector[with_everything]>=0.12.4',
        'pytest-cov>=1.8.0',
        'pytest-xdist>=1.15.0',
        'pytest>=3.0.3',
        'requests-mock>=1.3.0',
        'sphinx_rtd_theme>=0.1.6',
        'sphinx-argparse>=0.1.15',
        'Sphinx>=1.4.9',
        'vulture>=0.6,<0.25',  # Required for https://github.com/landscapeio/prospector/issues/230
    ],
}

# Copy tests requirements to test only base dependencies
extras_require['tests-base'] = extras_require['tests'][:]
# Add optional dependencies to the tests ones
extras_require['tests'].extend(extras_require['with-openstack'])

# Generate minimum dependencies
extras_require['tests-min'] = [dep.replace('>=', '==') for dep in extras_require['tests']]
if os.getenv('CUMIN_MIN_DEPS', False):
    install_requires = [dep.replace('>=', '==') for dep in install_requires]

setup_requires = [
    'pytest-runner>=2.7.1',
    'setuptools_scm>=1.15.0',
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
        'Programming Language :: Python :: 3 :: Only',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: System :: Clustering',
        'Topic :: System :: Distributed Computing',
        'Topic :: System :: Systems Administration',
    ],
    data_files=[('share/doc/cumin/examples/', ['doc/examples/config.yaml', 'doc/examples/aliases.yaml'])],
    description='Automation and orchestration framework and CLI written in Python',
    entry_points={
        'console_scripts': [
            'cumin = cumin.cli:main',
        ],
    },
    extras_require=extras_require,
    install_requires=install_requires,
    keywords=['cumin', 'automation', 'orchestration'],
    license='GPLv3+',
    long_description=long_description,
    name='cumin',
    packages=find_packages(exclude=['*.tests', '*.tests.*']),
    platforms=['GNU/Linux', 'BSD', 'MacOSX'],
    setup_requires=setup_requires,
    url='https://github.com/wikimedia/cumin',
    use_scm_version=True,
    zip_safe=False,
)
