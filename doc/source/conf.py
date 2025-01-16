# -*- coding: utf-8 -*-
"""Sphynx configuration."""
#
# Cumin documentation build configuration file, created by
# sphinx-quickstart on Sat Sep 30 13:33:02 2017.
#
# This file is execfile()d with the current directory set to its
# containing dir.
#
# Note that not all possible configuration values are present in this
# autogenerated file.
#
# All configuration values have a default; values that are commented out
# serve to show the default.

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
import os
import sys

from importlib.metadata import version as meta_version

import sphinx_rtd_theme

from sphinx import __version__ as sphinx_version

# Adjust path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))


# -- General configuration ------------------------------------------------

# If your documentation needs a minimal Sphinx version, state it here.
#
# needs_sphinx = '1.0'

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.intersphinx',
    'sphinx.ext.todo',
    'sphinx.ext.coverage',
    'sphinx.ext.viewcode',
    'sphinx.ext.githubpages',
    'sphinxarg.ext',
]

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# The suffix(es) of source filenames.
# You can specify multiple suffix as a list of string:
#
# source_suffix = ['.rst', '.md']
source_suffix = '.rst'

# The master toctree document.
master_doc = 'index'

# General information about the project.
project = u'Cumin'
title = u'{project} Documentation'.format(project=project)
copyright = u"2017-2020, Riccardo Coccioli <rcoccioli@wikimedia.org>, Wikimedia Foundation, Inc."
author = u'Riccardo Coccioli'

# The version info for the project you're documenting, acts as replacement for
# |version| and |release|, also used in various other places throughout the
# built documents.
#
# The full version, including alpha/beta/rc tags.
release = meta_version('cumin')
# The short X.Y version.
version = release


# The language for content autogenerated by Sphinx. Refer to documentation
# for a list of supported languages.
#
# This is also used if you do content translation via gettext catalogs.
# Usually you set "language" from the command line for these cases.
language = 'en'

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This patterns also effect to html_static_path and html_extra_path
exclude_patterns = []

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = 'sphinx'

# If true, `todo` and `todoList` produce output, else they produce nothing.
todo_include_todos = True


# -- Options for HTML output ----------------------------------------------

html_theme = 'sphinx_rtd_theme'
html_theme_path = [sphinx_rtd_theme.get_html_theme_path()]
sphinx_version_parts = [int(i) for i in sphinx_version.split('.')]
if sphinx_version_parts[0] == 1 and sphinx_version_parts[1] < 6:
    html_use_smartypants = False

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']

# -- Options for HTMLHelp output ------------------------------------------

# Output file base name for HTML help builder.
htmlhelp_basename = 'Cumindoc'


# -- Options for manual page output ---------------------------------------

# One entry per manual page. List of tuples
# (source start file, name, description, authors, manual section).
man_pages = [
    ('cli', 'cumin', 'Automation and orchestration framework written in Python', [author], 1),
]


# -- Options for intersphinx ---------------------------------------

intersphinx_mapping = {
    'python': ('https://docs.python.org/3/', None),
    'requests': ('https://requests.readthedocs.io/en/master/', None),
    'ClusterShell': ('https://clustershell.readthedocs.io/en/v1.8.1/', None),
    'keystoneauth1': ('https://docs.openstack.org/keystoneauth/latest', None),
    'novaclient': ('https://docs.openstack.org/python-novaclient/latest/', None),
    'pyparsing': ('https://pythonhosted.org/pyparsing/', 'pyparsing.inv'),
}

# Napoleon settings
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = False
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = False
napoleon_use_admonition_for_examples = False
napoleon_use_admonition_for_notes = False
napoleon_use_admonition_for_references = False
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_use_keyword = True

# Autodoc settings
autodoc_default_options = {
    # Using None as value instead of True to support the version of Sphinx used in Buster
    'members': None,
    'member-order': 'bysource',
    'private-members': None,
    'show-inheritance': None,
}
autoclass_content = 'both'


# -- Helper functions -----------------------------------------------------
def filter_namedtuple_docstrings(app, what, name, obj, options, lines):
    """Fix the automatically generated docstrings for namedtuples classes."""
    if what == 'property' and len(lines) == 1 and lines[0].startswith('Alias for field number'):
        del lines[:]


# Keep track of documented classes to avoid annotating both class and __init__.
# Necessary when using autoclass_content 'both' and add_abstract_annotations().
_cumin_documented_classes = set()


def add_abstract_annotations(app, what, name, obj, options, lines):
    """Workaround to add an abstract annotation for ABC abstract classes."""
    if what == 'class' and len(getattr(obj, '__abstractmethods__', [])) > 0 and name not in _cumin_documented_classes:
        lines.insert(0, '``abstract``')
        _cumin_documented_classes.add(name)


def setup(app):
    """Register the helper functions."""
    app.connect('autodoc-process-docstring', filter_namedtuple_docstrings)
    app.connect('autodoc-process-docstring', add_abstract_annotations)
    app.add_css_file('theme_overrides.css')  # override wide tables in RTD theme
