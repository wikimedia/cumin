"""Tests utils"""

import logging
import os

logging.basicConfig(level=logging.DEBUG, name=__name__)
_tests_base_path = os.path.realpath(os.path.dirname(__file__))


def get_fixture(filename, as_string=False):
    """ Return the content of a fixture file

        Arguments:
        filename  -- the file to be opened in the test's fixture directory
        as_string -- return the content as a multiline string instead of a list of lines [optional, default: False]
    """
    with open(os.path.join(_tests_base_path, 'fixtures', filename)) as f:
        if as_string:
            content = f.read()
        else:
            content = f.readlines()

    return content
