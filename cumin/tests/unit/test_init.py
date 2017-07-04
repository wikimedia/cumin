"""Cumin package tests."""
# pylint: disable=invalid-name
import os

import pytest

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
    """A CuminError is raised if the configuration is empty."""
    with pytest.raises(cumin.CuminError, match='Empty configuration found in'):
        cumin.Config(config=get_fixture_path(os.path.join('config', 'empty', 'config.yaml')))


def test_config_class_invalid():
    """A CuminError is raised if the configuration cannot be parsed."""
    with pytest.raises(cumin.CuminError, match='Unable to parse configuration file'):
        cumin.Config(config=get_fixture_path(os.path.join('config', 'invalid', 'config.yaml')))


def test_config_class_valid_with_aliases():
    """Should return the config including the backend aliases."""
    config = cumin.Config(config=get_fixture_path(os.path.join('config', 'valid_with_aliases', 'config.yaml')))
    assert 'log_file' in config
    assert 'aliases' in config['puppetdb']
    assert 'role1' in config['puppetdb']['aliases']
    assert config['puppetdb']['aliases']['role1'] == 'R:Class = Role::Role1'
    assert 'aliases' in config['direct']
    assert 'group1' in config['direct']['aliases']
    assert config['direct']['aliases']['group1'] == 'host10[10-22].example.org'


def test_config_class_empty_aliases():
    """A CuminError is raised if one of the backend aliases is empty."""
    with pytest.raises(cumin.CuminError, match='Empty configuration found in'):
        cumin.Config(config=get_fixture_path(os.path.join('config', 'valid_with_empty_aliases', 'config.yaml')))


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
    """A CuminError is raised if the configuration is empty."""
    with pytest.raises(cumin.CuminError, match='Empty configuration found in'):
        cumin.parse_config(get_fixture_path(os.path.join('config', 'empty', 'config.yaml')))


def test_load_backend_aliases_missing():
    """If no aliases file is present, load_backend_aliases() should not raise any error."""
    base_path = get_fixture_path(os.path.join('config', 'valid'))
    config = {}
    cumin.load_backend_aliases(config, base_path)
    assert config == {}


def test_load_backend_aliases_valid():
    """If valid aliases files are present, load_backend_aliases() should load them into the configuration."""
    base_path = get_fixture_path(os.path.join('config', 'valid_with_aliases'))
    config = {'direct': {}}
    cumin.load_backend_aliases(config, base_path)
    assert 'aliases' in config['puppetdb']
    assert 'role1' in config['puppetdb']['aliases']
    assert config['puppetdb']['aliases']['role1'] == 'R:Class = Role::Role1'
    assert 'aliases' in config['direct']
    assert 'group1' in config['direct']['aliases']
    assert config['direct']['aliases']['group1'] == 'host10[10-22].example.org'


def test_load_backend_aliases_empty():
    """If empty aliases files are present, load_backend_aliases() should raise CuminError."""
    base_path = get_fixture_path(os.path.join('config', 'valid_with_empty_aliases'))
    with pytest.raises(cumin.CuminError, match='Empty configuration found in'):
        cumin.load_backend_aliases({}, base_path)


def test_load_backend_aliases_invalid():
    """If invalid aliases files are present, load_backend_aliases() should raise CuminError."""
    base_path = get_fixture_path(os.path.join('config', 'valid_with_invalid_aliases'))
    with pytest.raises(cumin.CuminError, match='Unable to parse configuration file'):
        cumin.load_backend_aliases({}, base_path)
