"""Cumin package tests."""
# pylint: disable=invalid-name
import importlib
import logging
import os

import pytest

from ClusterShell.NodeSet import NodeSet

import cumin

from cumin.tests import get_fixture_path


def test_config_class_valid():
    """Should return the config. Multiple Config with the same path should return the same object."""
    config_file = get_fixture_path(os.path.join('config', 'valid', 'config.yaml'))
    config1 = cumin.Config(config=config_file)
    assert 'log_file' in config1
    config2 = cumin.Config(config=config_file)
    assert config1 is config2


def test_config_class_empty():
    """An empty dictionary is returned if the configuration is empty."""
    config = cumin.Config(config=get_fixture_path(os.path.join('config', 'empty', 'config.yaml')))
    assert config == {}


def test_config_class_invalid():
    """A CuminError is raised if the configuration cannot be parsed."""
    with pytest.raises(cumin.CuminError, match='Unable to parse configuration file'):
        cumin.Config(config=get_fixture_path(os.path.join('config', 'invalid', 'config.yaml')))


def test_config_class_valid_with_aliases():
    """Should return the config including the aliases."""
    config = cumin.Config(config=get_fixture_path(os.path.join('config', 'valid_with_aliases', 'config.yaml')))
    assert 'log_file' in config
    assert 'aliases' in config
    assert 'role1' in config['aliases']
    assert config['aliases']['role1'] == 'P{R:Class = Role::Role1}'
    assert 'group1' in config['aliases']
    assert config['aliases']['group1'] == 'D{host10[10-22].example.org}'


def test_config_class_empty_aliases():
    """The configuration is loaded also if the aliases file is empty."""
    config = cumin.Config(config=get_fixture_path(os.path.join('config', 'valid_with_empty_aliases', 'config.yaml')))
    assert 'log_file' in config
    assert 'aliases' in config
    assert config['aliases'] == {}


def test_config_class_invalid_aliases():
    """A CuminError is raised if one of the backend aliases is invalid."""
    with pytest.raises(cumin.CuminError, match='Unable to parse configuration file'):
        cumin.Config(config=get_fixture_path(os.path.join('config', 'valid_with_invalid_aliases', 'config.yaml')))


def test_parse_config_ok():
    """The configuration file is properly parsed and accessible."""
    config = cumin.parse_config(get_fixture_path(os.path.join('config', 'valid', 'config.yaml')))
    assert 'log_file' in config


def test_parse_config_non_existent():
    """A CuminError is raised if the configuration file is not available."""
    with pytest.raises(cumin.CuminError, match='Unable to read configuration file'):
        cumin.parse_config('not_existent_config.yaml')


def test_parse_config_invalid():
    """A CuminError is raised if the configuration cannot be parsed."""
    with pytest.raises(cumin.CuminError, match='Unable to parse configuration file'):
        cumin.parse_config(get_fixture_path(os.path.join('config', 'invalid', 'config.yaml')))


def test_parse_config_empty():
    """An empty dictionary is returned if the configuration is empty."""
    config = cumin.parse_config(get_fixture_path(os.path.join('config', 'empty', 'config.yaml')))
    assert config == {}


def test_trace_logging_level_conflict():
    """If the logging level for trace is already registered, should raise CuminError."""
    importlib.reload(logging)  # Avoid conflict given the singleton nature of this module
    logging.addLevelName(cumin.LOGGING_TRACE_LEVEL_NUMBER, 'CONFLICT')
    match = 'Unable to set custom logging for trace'
    try:  # pytest.raises doesn't catch the reload exception
        importlib.reload(cumin)
    except cumin.CuminError as e:
        assert str(e).startswith(match)
    else:
        raise AssertionError("Failed: DID NOT RAISE {exc} matching '{match}'".format(
            exc=cumin.CuminError, match=match))


def test_trace_logging_level_existing_same():
    """If the custom logging level is registered on the same level, it should use it and add a trace method."""
    importlib.reload(logging)  # Avoid conflict given the singleton nature of this module
    logging.addLevelName(cumin.LOGGING_TRACE_LEVEL_NUMBER, cumin.LOGGING_TRACE_LEVEL_NAME)
    assert not hasattr(logging.Logger, 'trace')
    importlib.reload(cumin)
    assert logging.getLevelName(cumin.LOGGING_TRACE_LEVEL_NUMBER) == cumin.LOGGING_TRACE_LEVEL_NAME
    assert logging.getLevelName(cumin.LOGGING_TRACE_LEVEL_NAME) == cumin.LOGGING_TRACE_LEVEL_NUMBER
    assert hasattr(logging.Logger, 'trace')


def test_trace_logging_level_existing_different():
    """If the custom logging level is registered on a different level, it should use it and add a trace method."""
    importlib.reload(logging)  # Avoid conflict given the singleton nature of this module
    logging.addLevelName(cumin.LOGGING_TRACE_LEVEL_NUMBER - 1, cumin.LOGGING_TRACE_LEVEL_NAME)
    assert not hasattr(logging.Logger, 'trace')
    importlib.reload(cumin)
    assert logging.getLevelName(cumin.LOGGING_TRACE_LEVEL_NAME) == cumin.LOGGING_TRACE_LEVEL_NUMBER - 1
    assert logging.getLevelName(cumin.LOGGING_TRACE_LEVEL_NUMBER) != cumin.LOGGING_TRACE_LEVEL_NAME
    assert hasattr(logging.Logger, 'trace')


def test_trace_logging_method_existing():
    """If there is already a trace method registered, it should use it without problems adding the level."""
    importlib.reload(logging)  # Avoid conflict given the singleton nature of this module
    logging.Logger.trace = cumin.trace
    importlib.reload(cumin)
    assert logging.getLevelName(cumin.LOGGING_TRACE_LEVEL_NUMBER) == cumin.LOGGING_TRACE_LEVEL_NAME
    assert logging.getLevelName(cumin.LOGGING_TRACE_LEVEL_NAME) == cumin.LOGGING_TRACE_LEVEL_NUMBER
    assert hasattr(logging.Logger, 'trace')


def test_nodeset():
    """Calling nodeset() should return an instance of ClusterShell NodeSet with no resolver."""
    nodeset = cumin.nodeset('node[1-2]')
    assert isinstance(nodeset, NodeSet)
    assert nodeset == NodeSet('node[1-2]')
    assert nodeset._resolver is None  # pylint: disable=protected-access


def test_nodeset_empty():
    """Calling nodeset() without parameter should return an instance of ClusterShell NodeSet with no resolver."""
    nodeset = cumin.nodeset()
    assert isinstance(nodeset, NodeSet)
    assert nodeset == NodeSet()
    assert nodeset._resolver is None  # pylint: disable=protected-access


def test_nodeset_fromlist():
    """Calling nodeset_fromlist() should return an instance of ClusterShell NodeSet with no resolver."""
    nodeset = cumin.nodeset_fromlist(['node1', 'node2'])
    assert isinstance(nodeset, NodeSet)
    assert nodeset == NodeSet('node[1-2]')
    assert nodeset._resolver is None  # pylint: disable=protected-access


def test_nodeset_fromlist_empty():
    """Calling nodeset_fromlist() with empty list should return an instance of ClusterShell NodeSet with no resolver."""
    nodeset = cumin.nodeset_fromlist([])
    assert isinstance(nodeset, NodeSet)
    assert nodeset == NodeSet()
    assert nodeset._resolver is None  # pylint: disable=protected-access
