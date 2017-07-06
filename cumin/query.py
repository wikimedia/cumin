"""Query handling: factory and builder."""

import importlib
import logging

from ClusterShell.NodeSet import NodeSet
from pyparsing import ParseResults

from cumin.backends import InvalidQueryError
from cumin.grammar import grammar


class Query(object):
    """Query factory class."""

    @staticmethod
    def new(config, logger=None):
        """Return an instance of the query class for the configured backend.

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
    """Query builder class.

    Parse a given query string and converts it into a query object for the configured backend
    """

    def __init__(self, config, logger=None):
        """Query builder constructor.

        Arguments:
        config       -- the configuration dictionary
        logger       -- an optional logging instance [optional, default: None]
        """
        self.logger = logger or logging.getLogger(__name__)
        self.query = Query.new(config, logger=self.logger)
        self.aliases = config.get(config['backend'], {}).get('aliases', {})
        self.level = None  # Nesting level for sub-groups

    def build(self, query_string):
        """Parse the query string according to the grammar and build the query object for the configured backend.

        Arguments:
        query_string -- the query string to be parsed and passed to the query builder
        """
        self.level = 0
        parsed = grammar.parseString(query_string.strip(), parseAll=True)
        for token in parsed:
            self._parse_token(token)

        return self.query

    def _parse_token(self, token, level=0):
        """Recursively interpret the tokens returned by the grammar parsing.

        Arguments:
        token -- a single token returned by the grammar parsing
        level -- nesting level in case of sub-groups in the query [optional, default: 0]
        """
        if not isinstance(token, ParseResults):  # Non-testable block, this should never happen
            raise InvalidQueryError('Expected an instance of pyparsing.ParseResults, got {instance}: {token}'.format(
                instance=type(token), token=token))

        token_dict = token.asDict()
        if not token_dict:
            for subtoken in token:
                self._parse_token(subtoken, level=(level + 1))
        else:
            if not self._replace_alias(token_dict, level):
                self._build_token(token_dict, level)

        while self.level > level:
            self.query.close_subgroup()
            self.level -= 1

    def _build_token(self, token_dict, level):
        """Build a token into the query object for the configured backend.

        Arguments:
        token_dict -- the dictionary of the parsed token returned by the grammar parsing
        level      -- nesting level in the query
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
            else:  # Non-testable block, this should never happen with the current grammar
                raise InvalidQueryError("Got bool '{bool}', one of and|or expected".format(bool=token_dict['bool']))

        elif 'hosts' in keys:
            token_dict['hosts'] = NodeSet(token_dict['hosts'])
            self.query.add_hosts(**token_dict)

        elif 'category' in keys:
            self.query.add_category(**token_dict)

        else:  # Non-testable block, this should never happen with the current grammar
            raise InvalidQueryError(
                "No valid key found in token, one of bool|hosts|category expected: {token}".format(token=token_dict))

    def _replace_alias(self, token_dict, level):
        """Replace any alias in the query in a recursive way, alias can reference other aliases.

        Return True if a replacement was made, False otherwise. Raise InvalidQueryError on failure.

        Arguments:
        token_dict -- the dictionary of the parsed token returned by the grammar parsing
        level      -- nesting level in the query
        """
        keys = token_dict.keys()
        if 'category' not in keys or token_dict['category'] != 'A':
            return False

        if 'operator' in keys or 'value' in keys:
            raise InvalidQueryError('Invalid alias syntax, aliases can be only of the form: A:alias_name')

        alias_name = token_dict['key']
        if alias_name not in self.aliases:
            raise InvalidQueryError("Unable to find alias replacement for '{alias}' in the configuration".format(
                alias=alias_name))

        neg = 'not ' if 'neg' in keys and token_dict['neg'] else ''
        alias = '{neg}({alias})'.format(neg=neg, alias=self.aliases[alias_name])
        parsed_alias = grammar.parseString(alias, parseAll=True)
        for token in parsed_alias:
            self._parse_token(token, level=level)

        return True
