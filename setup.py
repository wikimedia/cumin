#!/usr/bin/env python
"""Package configuration."""
import os

from setuptools import find_packages, setup


with open('README.rst', 'r') as readme:
    long_description = readme.read()

# Required dependencies
install_requires = [
    'clustershell>=1.9.1,<=1.9.99',
    'pyparsing>=3.0.9,<=3.99.0',
    'pyyaml>=6.0',
    'requests>=2.28.1',
    'tqdm>=4.64.1',
]

# Extra dependencies
extras_require = {
    # Optional dependencies for additional features
    'with-openstack': [
        'keystoneauth1>=5.0.0',
        'python-keystoneclient>=5.0.1',
        'python-novaclient>=18.1.0',
    ],

    # Test dependencies
    'tests': [
        'bandit>=1.6.2',
        'flake8>=5.0.4',
        'flake8-import-order>=0.18.2',
        'mypy',
        'pytest-cov>=4.0.0',
        'pytest-xdist>=3.1.0',
        'pytest>=7.2.1',
        'requests-mock>=1.9.3',
        'sphinx_rtd_theme>=1.2.0',
        'sphinx-argparse>=0.3.2',
        'Sphinx>=5.3.0',
        'types-PyYAML',
        'types-requests',
    ],
    'prospector': [
        'prospector[with-everything]>=1.10.3',
        'pytest>=7.2.1',
        'requests-mock>=1.9.3',
    ],
}

# Copy tests requirements to test only base dependencies
extras_require['tests-base'] = extras_require['tests'][:]
# Copy tests requirements to test with the minimum version of the install_requires and Sphinx that is used to
# generate the manpage during the Debian build process.
extras_require['tests-min'] = [dep.split(',')[0].replace('>=', '==') if dep.lower().startswith('sphinx') else dep
                               for dep in extras_require['tests']]
# Add optional dependencies to the tests ones
extras_require['tests'].extend(extras_require['with-openstack'])
extras_require['tests-min'].extend(dep.replace('>=', '==') for dep in extras_require['with-openstack'])
extras_require['prospector'].extend(extras_require['with-openstack'])

if os.getenv('CUMIN_MIN_DEPS', False):
    install_requires = [dep.split(',')[0].replace('>=', '==') for dep in install_requires]

setup_requires = [
    'pytest-runner>=2.11.1',
    'setuptools_scm>=7.1.0',
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
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
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
    long_description_content_type='text/x-rst',
    name='cumin',
    packages=find_packages(exclude=['*.tests', '*.tests.*']),
    platforms=['GNU/Linux', 'BSD', 'MacOSX'],
    python_requires='>=3.11',
    setup_requires=setup_requires,
    url='https://github.com/wikimedia/cumin',
    use_scm_version=True,
    zip_safe=False,
)
