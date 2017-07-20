"""Abstract backend."""

import logging

from abc import ABCMeta, abstractmethod

import pyparsing

from ClusterShell.NodeSet import NodeSet

from cumin import CuminError


class InvalidQueryError(CuminError):
    """Custom exception class for invalid queries."""


class BaseQuery(object):
    """Query abstract class.

    All backends query classes must inherit, directly or indirectly, from this one.
    """

    __metaclass__ = ABCMeta

    """Derived classes must define their own pyparsing grammar and set this class attribute accordingly."""
    grammar = pyparsing.NoMatch()  # This grammar will never match.

    def __init__(self, config, logger=None):
        """Query constructor.

        Arguments:
        config -- a dictionary with the parsed configuration file
        logger -- an optional logging.Logger instance [optional, default: None]
        """
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        self.logger.trace('Backend {name} created with config: {config}'.format(
            name=type(self).__name__, config=config))

    def execute(self, query_string):
        """Build and execute the query, return the list of FQDN hostnames that matches.

        Arguments:
        query_string -- the query string to be parsed and executed
        """
        self._build(query_string)
        return self._execute()

    @abstractmethod
    def _execute(self):
        """Execute the already parsed query and return the list of FQDN hostnames that matches."""

    @abstractmethod
    def _parse_token(self, token):
        """Recursively interpret the tokens returned by the grammar parsing.

        Arguments:
        token -- a single token returned by the grammar parsing
        """

    @abstractmethod
    def _open_subgroup(self):
        """Is called when a subgroup is opened in the parsing of the query.

        Given that each backend has it's own grammar and parsing logic, keeping this in the abstract class to force
        each backend to support subgrouping in the grammar for usability and coherence between backends.
        """

    @abstractmethod
    def _close_subgroup(self):
        """Is called when a subgroup is closed in the parsing of the query.

        Given that each backend has it's own grammar and parsing logic, keeping this in the abstract class to force
        each backend to support subgrouping in the grammar for usability and coherence between backends.
        """

    def _build(self, query_string):
        """Parse the query string according to the grammar and build the query for later execution.

        Arguments:
        query_string -- the query string to be parsed
        """
        self.logger.trace('Parsing query: {query}'.format(query=query_string))
        parsed = self.grammar.parseString(query_string.strip(), parseAll=True)
        self.logger.trace('Parsed query: {parsed}'.format(parsed=parsed))
        for token in parsed:
            self._parse_token(token)


class BaseQueryAggregator(BaseQuery):
    """Query aggregator abstract class.

    Add to BaseQuery the capability of aggregating query subgroups and sub tokens into a unified result using common
    boolean operators for sets: and, or, and not, xor.
    The class has a stack-like structure that must be populated by the derived classes while building the query.
    On execution the stack is traversed and the results are aggreagated together based on subgroups and boolean
    operators.
    """

    def __init__(self, config, logger=None):
        """Query aggregator constructor, initialize the stack."""
        super(BaseQueryAggregator, self).__init__(config, logger=logger)

        self.stack = None
        self.stack_pointer = None

    def _build(self, query_string):
        """Override parent class _build method to reset the stack and log it."""
        self.stack = self._get_stack_element()
        self.stack_pointer = self.stack
        super(BaseQueryAggregator, self)._build(query_string)
        self.logger.trace('Query stack: {stack}'.format(stack=self.stack))

    def _execute(self):
        """Required by BaseQuery."""
        hosts = NodeSet()
        self._loop_stack(hosts, self.stack)  # The hosts nodeset is updated in place while looping the stack
        self.logger.debug('Found {num} hosts'.format(num=len(hosts)))

        return hosts

    def _open_subgroup(self):
        """Required by BaseQuery."""
        element = self._get_stack_element()
        element['parent'] = self.stack_pointer
        self.stack_pointer['children'].append(element)
        self.stack_pointer = element

    def _close_subgroup(self):
        """Required by BaseQuery."""
        self.stack_pointer = self.stack_pointer['parent']

    @abstractmethod
    def _parse_token(self, token):
        """Required by BaseQuery."""

    @staticmethod
    def _get_stack_element():
        """Return an empty stack element."""
        return {'hosts': None, 'children': [], 'parent': None, 'bool': None}

    def _loop_stack(self, hosts, stack_element):
        """Loop the stack generated while parsing the query and aggregate the results.

        Arguments:
        hosts         -- the NodeSet of hosts to update with the current stack element results. This object is updated
                         in place by reference.
        stack_element -- the stack element to iterate
        """
        if stack_element['hosts'] is None:
            element_hosts = NodeSet()
            for child in stack_element['children']:
                self._loop_stack(element_hosts, child)
        else:
            element_hosts = stack_element['hosts']

        self._aggregate_hosts(hosts, element_hosts, stack_element['bool'])

    def _aggregate_hosts(self, hosts, element_hosts, bool_operator):
        """.

        Arguments:
        hosts         -- the NodeSet of hosts to update with the results in element_hosts according to the
                         bool_operator. This object is updated in place by reference.
        element_hosts -- the NodeSet of additional hosts to aggregate to the results based on the bool_operator
        bool_operator -- the boolean operator to apply while aggregating the two NodeSet. It must be None when adding
                         the first hosts.
        """
        self.logger.trace("Aggregating: {hosts} | {boolean} | {element_hosts}".format(
            hosts=hosts, boolean=bool_operator, element_hosts=element_hosts))

        # This should never happen
        if (bool_operator is None and hosts) or (bool_operator is not None and not hosts):  # pragma: no cover
            raise InvalidQueryError("Unexpected boolean operator '{boolean}' with hosts '{hosts}'".format(
                boolean=bool_operator, hosts=hosts))

        if bool_operator is None or bool_operator == 'or':
            hosts |= element_hosts
        elif bool_operator == 'and':
            hosts &= element_hosts
        elif bool_operator == 'and not':
            hosts -= element_hosts
        elif bool_operator == 'xor':
            hosts ^= element_hosts
        else:  # pragma: no cover - this should never happen
            raise InvalidQueryError("Invalid bool operator '{boolean}' found, one of and|and not|or expected".format(
                boolean=bool_operator))
