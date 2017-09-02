"""Tests utils."""

import logging
import os

logging.basicConfig(level=logging.DEBUG)
_TESTS_BASE_PATH = os.path.realpath(os.path.dirname(__file__))


def get_fixture(path, as_string=False):
    """Return the content of a fixture file.

    Arguments:
        path: the relative path to the test's fixture directory to be opened.
        as_string: return the content as a multiline string instead of a list of lines [optional, default: False]
    """
    with open(get_fixture_path(path)) as f:
        if as_string:
            content = f.read()
        else:
            content = f.readlines()

    return content


def get_fixture_path(path):
    """Return the absolute path of the given fixture.

    Arguments:
        path: the relative path to the test's fixture directory.
    """
    return os.path.join(_TESTS_BASE_PATH, 'fixtures', path)
