"""Cumin package tests."""
import os
import tempfile

import pytest

import cumin


def test_config_class_instantiation():
    """Should return the config. Multiple Config with the same path should return the same object."""
    config1 = cumin.Config('doc/examples/config.yaml')
    assert 'log_file' in config1
    config2 = cumin.Config('doc/examples/config.yaml')
    assert config1 is config2


def test_parse_config_ok():
    """The configuration file is properly parsed and accessible."""
    config = cumin.parse_config('doc/examples/config.yaml')
    assert 'log_file' in config


def test_parse_config_non_existent():
    """A CuminError is raised if the configuration file is not available."""
    with pytest.raises(cumin.CuminError, match='Unable to read configuration file'):
        cumin.parse_config('not_existent_config.yaml')


def test_parse_config_invalid():
    """A CuminError is raised if the configuration cannot be parsed."""
    invalid_yaml = '\n'.join((
        'foo:',
        '  bar: baz',
        '  - foobar',
    ))
    tmpfile, tmpfilepath = tempfile.mkstemp(suffix='config.yaml', prefix='cumin', text=True)
    os.write(tmpfile, invalid_yaml)

    with pytest.raises(cumin.CuminError, match='Unable to parse configuration file'):
        cumin.parse_config(tmpfilepath)


def test_parse_config_empty():
    """A CuminError is raised if the configuration is empty."""
    empty_yaml = ''
    tmpfile, tmpfilepath = tempfile.mkstemp(suffix='config.yaml', prefix='cumin', text=True)
    os.write(tmpfile, empty_yaml)

    with pytest.raises(cumin.CuminError, match='Empty configuration found in'):
        cumin.parse_config(tmpfilepath)
