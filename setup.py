#!/usr/bin/env python
"""Package configuration."""
import os

from setuptools import find_packages, setup


with open('README.rst', 'r') as readme:
    long_description = readme.read()

# Required dependencies
install_requires = [
    'clustershell>=1.8.1,<=1.9.99',
    'pyparsing>=2.2.0,<=3.99.0',
    'pyyaml>=3.13',
    'requests>=2.21.0',
    'tqdm>=4.19.4',
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
        'mypy',
        'pytest-cov>=2.6.0',
        'pytest-xdist>=1.26.1',
        'pytest>=3.10.1',
        'requests-mock>=1.5.2',
        'sphinx_rtd_theme>=0.4.3',
        'sphinx-argparse>=0.2.2',
        'Sphinx>=1.8.4',
        'types-pkg_resources',
        'types-PyYAML',
        'types-requests',
    ],
    'prospector': [
        'prospector[with_everything]>=1.3.1,<=1.7.7',  # Temporary upper limit for an upstream regression
        'pylint<2.15.7',  # Temporary upper limit for a change that breaks prospector that can't be upgraded
        'pytest>=3.10.1',
        'requests-mock>=1.5.2',
    ],
}

# Copy tests requirements to test only base dependencies
extras_require['tests-base'] = extras_require['tests'][:]
# Copy tests requirements to test with the minimum version of the install_requires and Sphinx that is used to
# generate the manpage during the Debian build process.
extras_require['tests-min'] = [dep.split(',')[0].replace('>=', '==') if dep.lower().startswith('sphinx') else dep
                               for dep in extras_require['tests']]
# Add Jinja2 upper limit for min-tests, it breaks with more recent versions
extras_require['tests-min'].append('jinja2<3.1.0')
# Add optional dependencies to the tests ones
extras_require['tests'].extend(extras_require['with-openstack'])
extras_require['tests-min'].extend(dep.replace('>=', '==') for dep in extras_require['with-openstack'])
extras_require['prospector'].extend(extras_require['with-openstack'])

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
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
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
    python_requires='>=3.7',
    setup_requires=setup_requires,
    url='https://github.com/wikimedia/cumin',
    use_scm_version=True,
    zip_safe=False,
)
