"""Color tests."""
from unittest import mock

import pytest

from cumin.color import Colored


def test_red():
    """It should return the message enclosed in ASCII red color code."""
    assert Colored.red('message') == '\x1b[31mmessage\x1b[39m'


def test_green():
    """It should return the message enclosed in ASCII green color code."""
    assert Colored.green('message') == '\x1b[32mmessage\x1b[39m'


def test_yellow():
    """It should return the message enclosed in ASCII yellow color code."""
    assert Colored.yellow('message') == '\x1b[33mmessage\x1b[39m'


def test_blue():
    """It should return the message enclosed in ASCII blue color code."""
    assert Colored.blue('message') == '\x1b[34mmessage\x1b[39m'


def test_cyan():
    """It should return the message enclosed in ASCII cyan color code."""
    assert Colored.cyan('message') == '\x1b[36mmessage\x1b[39m'


def test_wrong_case():
    """It should raise AttributeError if called with the wrong case."""
    with pytest.raises(AttributeError, match="'Colored' object has no attribute 'Red'"):
        Colored.Red('')


def test_non_existent():
    """It should raise AttributeError if called with a non existent color."""
    with pytest.raises(AttributeError, match="'Colored' object has no attribute 'missing'"):
        Colored.missing('')


def test_emtpy():
    """It should return an empty string if the object is empty."""
    assert Colored.red('') == ''


@mock.patch('cumin.color.Colored.disabled', new_callable=mock.PropertyMock)
def test_disabled(mocked_colored_disabled):
    """It should return the message untouched if coloration is disabled."""
    mocked_colored_disabled.return_value = True
    assert Colored.red('message') == 'message'
    assert mocked_colored_disabled.called
