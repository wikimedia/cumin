import unittest

from cumin.backends import BaseQuery


class TestBaseQuery(unittest.TestCase):
    """BaseQuery class tests"""

    def test_instantiation(self):
        """BaseQuery is not instantiable being an abstract class"""
        with self.assertRaises(TypeError):
            BaseQuery({})
