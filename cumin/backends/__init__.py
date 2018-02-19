"""Abstract backend."""

import logging

from abc import ABCMeta, abstractmethod

import pyparsing

from cumin import CuminError, nodeset


class InvalidQueryError(CuminError):
    """Custom exception class for invalid queries."""


class BaseQuery(object, metaclass=ABCMeta):
    """Query abstract class.

    All backends query classes must inherit, directly or indirectly, from this one.
    """

    grammar = pyparsing.NoMatch()  # This grammar will never match.
    """:py:class:`pyparsing.ParserElement`: derived classes must define their own pyparsing grammar and set this class
    attribute accordingly."""

    def __init__(self, config):
        """Query constructor.

        Arguments:
            config (dict): a dictionary with the parsed configuration file.
        """
        self.config = config
        self.logger = logging.getLogger('.'.join((self.__module__, self.__class__.__name__)))
        self.logger.trace('Backend %s created with config: %s', type(self).__name__, config)

    def execute(self, query_string):
        """Build and execute the query, return the NodeSet of FQDN hostnames that matches.

        Arguments:
            query_string (str): the query string to be parsed and executed.

        Returns:
            ClusterShell.NodeSet.NodeSet: with the FQDNs of the matching hosts.

        """
        self._build(query_string)
        return self._execute()

    @abstractmethod
    def _execute(self):
        """Execute the already parsed query and return the NodeSet of FQDN hostnames that matches.

        Returns:
            ClusterShell.NodeSet.NodeSet: with the FQDNs of the matching hosts.

        """

    @abstractmethod
    def _parse_token(self, token):
        """Recursively interpret the tokens returned by the grammar parsing.

        Arguments:
            token (pyparsing.ParseResults): a single token returned by the grammar parsing.
        """

    def _build(self, query_string):
        """Parse the query string according to the grammar and build the query for later execution.

        Arguments:
            query_string (str): the query string to be parsed.
        """
        self.logger.trace('Parsing query: %s', query_string)
        parsed = self.grammar.parseString(query_string.strip(), parseAll=True)
        self.logger.trace('Parsed query: %s', parsed)
        for token in parsed:
            self._parse_token(token)


class BaseQueryAggregator(BaseQuery):
    """Query aggregator abstract class.

    Add to :py:class:`cumin.backends.BaseQuery` the capability of aggregating query subgroups and sub tokens into a
    unified result using common boolean operators for sets: ``and``, ``or``, ``and not`` and ``xor``.
    The class has a stack-like structure that must be populated by the derived classes while building the query.
    On execution the stack is traversed and the results are aggreagated together based on subgroups and boolean
    operators.
    """

    def __init__(self, config):
        """Query aggregator constructor, initialize the stack.

        :Parameters:
            according to parent :py:meth:`cumin.backends.BaseQuery.__init__`.
        """
        super().__init__(config)

        self.stack = None
        self.stack_pointer = None

    def _build(self, query_string):
        """Override parent method to reset the stack and log it.

        :Parameters:
            according to parent :py:meth:`cumin.backends.BaseQuery._build`.
        """
        self.stack = self._get_stack_element()
        self.stack_pointer = self.stack
        super()._build(query_string)
        self.logger.trace('Query stack: %s', self.stack)

    def _execute(self):
        """Concrete implementation of parent abstract method.

        :Parameters:
            according to parent :py:meth:`cumin.backends.BaseQuery._execute`.
        """
        hosts = nodeset()
        self._loop_stack(hosts, self.stack)  # The hosts NodeSet is updated in place while looping the stack
        self.logger.debug('Found %d hosts', len(hosts))

        return hosts

    def _open_subgroup(self):
        """Handle subgroup opening."""
        element = self._get_stack_element()
        element['parent'] = self.stack_pointer
        self.stack_pointer['children'].append(element)
        self.stack_pointer = element

    def _close_subgroup(self):
        """Handle subgroup closing."""
        self.stack_pointer = self.stack_pointer['parent']

    @abstractmethod
    def _parse_token(self, token):
        """Re-define abstract method from parent abstract class.

        :Parameters:
            according to parent :py:meth:`cumin.backends.BaseQuery._parse_token`.
        """

    @staticmethod
    def _get_stack_element():
        """Return an empty stack element.

        Returns:
            dict: the dictionary with an empty stack element.

        """
        return {'hosts': None, 'children': [], 'parent': None, 'bool': None}

    def _loop_stack(self, hosts, stack_element):
        """Loop the stack generated while parsing the query and aggregate the results.

        Arguments:
            hosts (ClusterShell.NodeSet.NodeSet): the hosts to be updated with the current stack element results. This
                object is updated in place by reference.
            stack_element (dict): the stack element to iterate.
        """
        if stack_element['hosts'] is None:
            element_hosts = nodeset()
            for child in stack_element['children']:
                self._loop_stack(element_hosts, child)
        else:
            element_hosts = stack_element['hosts']

        self._aggregate_hosts(hosts, element_hosts, stack_element['bool'])

    def _aggregate_hosts(self, hosts, element_hosts, bool_operator):
        """Aggregate hosts according to their boolean operator.

        Arguments:
            hosts (ClusterShell.NodeSet.NodeSet): the hosts to update with the results in ``element_hosts`` according
                to the ``bool_operator``. This object is updated in place by reference.
            element_hosts (ClusterShell.NodeSet.NodeSet): the additional hosts to aggregate to the results based on the
                ``bool_operator``.
            bool_operator (str, None): the boolean operator to apply while aggregating the two NodeSet. It must be
                :py:data:`None` when adding the first hosts.
        """
        self.logger.trace("Aggregating: %s | %s | %s", hosts, bool_operator, element_hosts)

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
