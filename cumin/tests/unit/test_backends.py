"""Abstract query tests."""

import pytest

from cumin.backends import BaseQuery


def test_base_query_instantiation():
    """Class BaseQuery is not instantiable being an abstract class."""
    with pytest.raises(TypeError):
        BaseQuery({})  # pylint: disable=abstract-class-instantiated
