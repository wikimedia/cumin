#!/usr/bin/env python
"""Package configuration."""
import os

from setuptools import find_packages, setup


with open('README.rst', 'r') as readme:
    long_description = readme.read()

# Required dependencies
install_requires = [
    'clustershell>=1.8.1,<=1.9',
    'pyparsing>=2.2.0,<=2.3',
    'pyyaml>=3.13',
    'requests>=2.21.0',
    'tqdm>=4.19.4,<=4.24.0'
]

# Extra dependencies
extras_require = {
    # Optional dependencies for additional features
    'with-openstack': [
        'keystoneauth1>=3.10.0',
        'python-keystoneclient>=3.17.0',
        'python-novaclient>=11.0.0',
    ],

    # Test dependencies
    'tests': [
        'bandit>=1.5.1',
        'flake8>=3.6.0',
        'flake8-import-order>=0.18.1',
        'prospector[with_everything]>=1.1.7',
        'pytest-cov>=2.6.0',
        'pytest-xdist>=1.26.1',
        'pytest>=3.10.1',
        'requests-mock>=1.5.2',
        'sphinx_rtd_theme>=0.4.3',
        'sphinx-argparse>=0.2.2',
        'Sphinx>=1.8.4',
    ],
}

# Copy tests requirements to test only base dependencies
extras_require['tests-base'] = extras_require['tests'][:]
# Add optional dependencies to the tests ones
extras_require['tests'].extend(extras_require['with-openstack'])

# Generate minimum dependencies
extras_require['tests-min'] = [dep.replace('>=', '==') for dep in extras_require['tests']]
if os.getenv('CUMIN_MIN_DEPS', False):
    install_requires = [dep.split(',')[0].replace('>=', '==') for dep in install_requires]

setup_requires = [
    'pytest-runner>=2.11.1',
    'setuptools_scm>=3.2.0',
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
        'Programming Language :: Python :: 3.7',
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
