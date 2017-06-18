"""Abstract query tests."""

import unittest

from cumin.backends import BaseQuery


class TestBaseQuery(unittest.TestCase):
    """Class BaseQuery tests."""

    def test_instantiation(self):
        """Class BaseQuery is not instantiable being an abstract class."""
        with self.assertRaises(TypeError):
            BaseQuery({})  # pylint: disable=abstract-class-instantiated
