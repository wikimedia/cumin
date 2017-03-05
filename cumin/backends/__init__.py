"""Abstract backend."""

import logging

from abc import ABCMeta, abstractmethod

from cumin import CuminError


class InvalidQueryError(CuminError):
    """Custom exception class for invalid queries."""


class BaseQuery(object):
    """Query Builder interface."""

    __metaclass__ = ABCMeta

    def __init__(self, config, logger=None):
        """Query Builder constructor.

        Arguments:
        config -- a dictionary with the parsed configuration file
        logger -- an optional logger instance [optional, default: None]
        """
        self.config = config
        self.logger = logger or logging.getLogger(__name__)

    @abstractmethod
    def add_category(self, category, key, value=None, operator='=', neg=False):
        """Add a category token to the query 'F:key = value'.

        Arguments:
        category -- the category of the token, one of cumin.grammar.categories
        key      -- the key for this category
        value    -- the value to match, if not specified the key itself will be matched [optional, default: None]
        operator -- the comparison operator to use, one of cumin.grammar.operators [optional: default: =]
        neg      -- whether the token must be negated [optional, default: False]
        """

    @abstractmethod
    def add_hosts(self, hosts, neg=False):
        """Add a list of hosts to the query.

        Arguments:
        hosts -- a list of hosts to match
        neg   -- whether the token must be negated [optional, default: False]
        """

    @abstractmethod
    def open_subgroup(self):
        """Open a subgroup in the query."""

    @abstractmethod
    def close_subgroup(self):
        """Close a subgroup in the query."""

    @abstractmethod
    def add_and(self):
        """Add an AND query block to the query."""

    @abstractmethod
    def add_or(self):
        """Add an OR query block to the query."""

    @abstractmethod
    def execute(self):
        """Execute the query and return the list of FQDN hostnames that matches."""
