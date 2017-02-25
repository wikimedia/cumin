"""Query handling: factory and builder"""

import importlib
import logging

from ClusterShell.NodeSet import NodeSet
from pyparsing import ParseResults

from cumin.grammar import grammar


class Query(object):
    """Query factory class"""

    @staticmethod
    def new(config, logger=None):
        """ Return an instance of the query class for the configured backend

            Arguments:
            config - the configuration dictionary
            logger - an optional logging instance [optional, default: None]
        """
        try:
            module = importlib.import_module('cumin.backends.{backend}'.format(backend=config['backend']))
            return module.query_class(config, logger)
        except (AttributeError, ImportError) as e:
            raise RuntimeError("Unable to load query class for backend '{backend}': {msg}".format(
                backend=config['backend'], msg=repr(e)))


class QueryBuilder(object):
    """ Query builder class

        Parse a given query string and converts it into a query object for the configured backend
    """

    def __init__(self, query_string, config, logger=None):
        """ Query builder constructor

            Arguments:
            query_string -- the query string to be parsed and passed to the query builder
            config       -- the configuration dictionary
            logger       -- an optional logging instance [optional, default: None]
        """
        self.logger = logger or logging.getLogger(__name__)
        self.query_string = query_string.strip()
        self.query = Query.new(config, logger=self.logger)
        self.level = 0  # Nesting level for sub-groups

    def build(self):
        """Parse the query string according to the grammar and build the query object for the configured backend"""
        parsed = grammar.parseString(self.query_string, parseAll=True)
        for token in parsed:
            self._parse_token(token)

        return self.query

    def _parse_token(self, token, level=0):
        """ Recursively interpret the tokens returned by the grammar parsing

            Arguments:
            token -- a single token returned by the grammar parsing
            level -- Nesting level in case of sub-groups in the query [optional, default: 0]
        """
        if not isinstance(token, ParseResults):
            raise RuntimeError("Invalid query string syntax '{query}'. Token is '{token}'".format(
                query=self.query_string, token=token))

        token_dict = token.asDict()
        if not token_dict:
            for subtoken in token:
                self._parse_token(subtoken, level=(level + 1))
        else:
            self._build_token(token_dict, level)

    def _build_token(self, token_dict, level):
        """ Buld a token into the query object for the configured backend

            Arguments:
            token_dict -- the dictionary of the parsed token returned by the grammar parsing
            level      -- Nesting level in the query
        """
        keys = token_dict.keys()

        # Handle sub-groups
        if level > self.level:
            self.query.open_subgroup()
        elif level < self.level:
            self.query.close_subgroup()

        self.level = level

        # Based on the token type build the corresponding query object
        if 'bool' in keys:
            if token_dict['bool'] == 'and':
                self.query.add_and()
            elif token_dict['bool'] == 'or':
                self.query.add_or()

        elif 'hosts' in keys:
            token_dict['hosts'] = NodeSet(token_dict['hosts'])
            self.query.add_hosts(**token_dict)

        elif 'category' in keys:
            self.query.add_category(**token_dict)
