"""Query handling: factory and builder."""
from pyparsing import ParseException, ParseResults

from cumin import grammar
from cumin.backends import BaseQuery, BaseQueryAggregator, InvalidQueryError


class Query(BaseQueryAggregator):
    """Cumin main query class.

    It has multi-query capability and allow to use a default backend, if set, without additional syntax.
    If a ``default_backend`` is set in the configuration, it will try to execute the query string first with the
    default backend and only if the query is not parsable with that backend it will try to execute it with the
    multi-query grammar.

    When a query is executed, a :py:class:`ClusterShell.NodeSet.NodeSet` with the FQDN of the matched hosts is
    returned.

    Examples:
        >>> import cumin
        >>> from cumin.query import Query
        >>> config = cumin.Config()
        >>> hosts = Query(config).execute(query_string)

    """

    def __init__(self, config):
        """Query constructor, initialize the registered backends.

        :Parameters:
            according to parent :py:meth:`cumin.backends.BaseQueryAggregator.__init__`.
        """
        super().__init__(config)
        external = self.config.get('plugins', {}).get('backends', [])
        self.registered_backends = grammar.get_registered_backends(external=external)
        self.grammar = grammar.grammar(self.registered_backends.keys())

    def execute(self, query_string):
        """Override parent class execute method to implement the multi-query capability.

        :Parameters:
            according to parent :py:meth:`cumin.backends.BaseQueryAggregator.execute`.

        Returns:
            ClusterShell.NodeSet.NodeSet: with the FQDNs of the matching hosts.

        Raises:
            cumin.backends.InvalidQueryError: if unable to parse the query.

        """
        if 'default_backend' not in self.config:
            try:  # No default backend set, using directly the global grammar
                return super().execute(query_string)
            except ParseException as e:
                raise InvalidQueryError(("Unable to parse the query '{query}' with the global grammar and no "
                                         "default backend is set:\n{error}").format(query=query_string, error=e))

        try:  # Default backend set, trying it first
            hosts = self._query_default_backend(query_string)
        except ParseException as e_default:
            try:  # Trying global grammar as a fallback
                hosts = super().execute(query_string)
            except ParseException as e_global:
                raise InvalidQueryError(
                    ("Unable to parse the query '{query}' neither with the default backend '{name}' nor with the "
                     "global grammar:\n{name}: {e_def}\nglobal: {e_glob}").format(
                        query=query_string, name=self.config['default_backend'], e_def=e_default, e_glob=e_global))

        return hosts

    def _query_default_backend(self, query_string):
        """Execute the query with the default backend, according to the configuration.

        Arguments:
            query_string (str): the query string to be parsed and executed with the default backend.

        Returns:
            ClusterShell.NodeSet.NodeSet: with the FQDNs of the matching hosts.

        Raises:
            cumin.backends.InvalidQueryError: if unable to get the default backend from the registered backends.

        """
        for registered_backend in self.registered_backends.values():
            if registered_backend.name == self.config['default_backend']:
                backend = registered_backend
                break
        else:
            raise InvalidQueryError("Default backend '{name}' is not registered: {backends}".format(
                name=self.config['default_backend'], backends=self.registered_backends))

        query = backend.cls(self.config)

        return query.execute(query_string)

    def _parse_token(self, token):
        """Concrete implementation of parent abstract method.

        :Parameters:
            according to parent :py:meth:`cumin.backends.BaseQueryAggregator._parse_token`.

        Raises:
            cumin.backends.InvalidQueryError: on internal parsing error.

        """
        if not isinstance(token, ParseResults):  # pragma: no cover - this should never happen
            raise InvalidQueryError('Expecting ParseResults object, got {type}: {token}'.format(
                type=type(token), token=token))

        token_dict = token.asDict()
        self.logger.trace('Token is: %s', token_dict)

        if self._replace_alias(token_dict):
            return  # This token was an alias and got replaced

        if 'backend' in token_dict and 'query' in token_dict:
            element = self._get_stack_element()
            query = self.registered_backends[token_dict['backend']].cls(self.config)
            element['hosts'] = query.execute(token_dict['query'])
            if 'bool' in token_dict:
                element['bool'] = token_dict['bool']
            self.stack_pointer['children'].append(element)
        elif 'open_subgroup' in token_dict and 'close_subgroup' in token_dict:
            self._open_subgroup()
            if 'bool' in token_dict:
                self.stack_pointer['bool'] = token_dict['bool']
            for subtoken in token:
                if isinstance(subtoken, str):
                    continue
                self._parse_token(subtoken)
            self._close_subgroup()
        else:  # pragma: no cover - this should never happen
            raise InvalidQueryError('Got unexpected token: {token}'.format(token=token))

    def _replace_alias(self, token_dict):
        """Replace any alias in the query in a recursive way, alias can reference other aliases.

        Arguments:
            token_dict (dict): the dictionary of the parsed token returned by the grammar parsing.

        Returns:
            bool: :py:data:`True` if a replacement was made, :py:data`False` otherwise.

        Raises:
            cumin.backends.InvalidQueryError: if unable to replace an alias.

        """
        if 'alias' not in token_dict:
            return False

        alias_name = token_dict['alias']
        if alias_name not in self.config.get('aliases', {}):
            raise InvalidQueryError("Unable to find alias replacement for '{alias}' in the configuration".format(
                alias=alias_name))

        self._open_subgroup()
        if 'bool' in token_dict:
            self.stack_pointer['bool'] = token_dict['bool']

        # Calling BaseQuery._build() directly and not the parent's one to avoid resetting the stack
        BaseQuery._build(self, self.config['aliases'][alias_name])  # pylint: disable=protected-access
        self._close_subgroup()

        return True
