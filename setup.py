#!/usr/bin/env python
"""Package configuration."""
import os

from setuptools import find_packages, setup


with open('README.rst', 'r') as readme:
    long_description = readme.read()

# Required dependencies
install_requires = [
    'clustershell>=1.8.3,<=1.9.99',
    'pyparsing>=2.4.7,<=3.99.0',
    'pyyaml>=5.3.1',
    'requests>=2.25.1',
    'tqdm>=4.57.0',
]

# Extra dependencies
extras_require = {
    # Optional dependencies for additional features
    'with-openstack': [
        'keystoneauth1>=4.2.1',
        'python-keystoneclient>=4.1.1',
        'python-novaclient>=17.2.1',
    ],

    # Test dependencies
    'tests': [
        'bandit>=1.6.1',
        'flake8>=3.8.4',
        'flake8-import-order>=0.18.2',
        'mypy',
        'pytest-cov>=2.10.1',
        'pytest-xdist>=2.2.0',
        'pytest>=6.0.2',
        'requests-mock>=1.7.0',
        'sphinx_rtd_theme>=1.0',
        'sphinx-argparse>=0.2.5',
        # Temporary pinning due to https://github.com/sphinx-doc/sphinx/issues/11890
        'sphinxcontrib-applehelp<=1.0.4',
        'sphinxcontrib-devhelp<=1.0.2',
        'sphinxcontrib-htmlhelp<=2.0.1',
        'sphinxcontrib-serializinghtml<=1.1.6',
        'sphinxcontrib-qthelp<=1.0.3',
        # End of temporary pinning
        'Sphinx>=3.4.3',
        'types-PyYAML',
        'types-requests',
    ],
    'prospector': [
        'prospector[with_everything]>=1.3.1',
        'pytest>=6.0.2',
        'requests-mock>=1.7.0',
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
# Add Sphinx-related packates limit for min-tests, they are not pinned in Sphinx and break if too recent
extras_require['tests-min'].append('sphinxcontrib-applehelp<1.0.6')
extras_require['tests-min'].append('sphinxcontrib-devhelp<1.0.4')
extras_require['tests-min'].append('sphinxcontrib-htmlhelp<2.0.3')
extras_require['tests-min'].append('sphinxcontrib-serializinghtml<1.1.7')
extras_require['tests-min'].append('sphinxcontrib-qthelp<1.0.4')
# Add optional dependencies to the tests ones
extras_require['tests'].extend(extras_require['with-openstack'])
extras_require['tests-min'].extend(dep.replace('>=', '==') for dep in extras_require['with-openstack'])
extras_require['prospector'].extend(extras_require['with-openstack'])

if os.getenv('CUMIN_MIN_DEPS', False):
    install_requires = [dep.split(',')[0].replace('>=', '==') for dep in install_requires]

setup_requires = [
    'pytest-runner>=2.11.1',
    'setuptools_scm>=5.0.1',
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
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
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
    python_requires='>=3.9',
    setup_requires=setup_requires,
    url='https://github.com/wikimedia/cumin',
    use_scm_version=True,
    zip_safe=False,
)
