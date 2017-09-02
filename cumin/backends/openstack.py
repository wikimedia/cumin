"""OpenStack backend."""
import pyparsing as pp

from keystoneauth1 import session as keystone_session
from keystoneauth1.identity import v3 as keystone_identity
from keystoneclient.v3 import client as keystone_client
from novaclient import client as nova_client

from cumin import nodeset, nodeset_fromlist
from cumin.backends import BaseQuery, InvalidQueryError


def grammar():
    """Define the query grammar.

    Backus-Naur form (BNF) of the grammar::

        <grammar> ::= "*" | <items>
          <items> ::= <item> | <item> <whitespace> <items>
           <item> ::= <key>:<value>

    Given that the pyparsing library defines the grammar in a BNF-like style, for the details of the tokens not
    specified above check directly the source code.

    Returns:
        pyparsing.ParserElement: the grammar parser.

    """
    quoted_string = pp.quotedString.copy().addParseAction(pp.removeQuotes)  # Both single and double quotes are allowed

    # Key-value tokens: key:value
    # Lowercase key, all printable characters except the parentheses that are part of the global grammar for the value
    key = pp.Word(pp.srange('[a-z0-9-_.]"'), min=2)('key')
    all_but_par = ''.join([c for c in pp.printables if c not in ('(', ')', '{', '}')])
    value = (quoted_string | pp.Word(all_but_par))('value')
    item = pp.Combine(key + ':' + value)

    # Final grammar, see the docstring for its BNF based on the tokens defined above
    # Groups are used to split the parsed results for an easy access
    return pp.Group(pp.Literal('*')('all')) | pp.OneOrMore(pp.Group(item))


def _get_keystone_session(config, project=None):
    """Return a new keystone session based on configuration.

    Arguments:
        config (dict): a dictionary with the session configuration keys: ``auth_url``, ``username``, ``password``.
        project (str, optional): a project to scope the session to.

    Returns:
        keystoneauth1.session.Session: the Keystone session scoped for the project if specified.

    """
    auth = keystone_identity.Password(
        auth_url='{auth_url}/v3'.format(auth_url=config.get('auth_url', 'http://localhost:5000')),
        username=config.get('username', 'username'),
        password=config.get('password', 'password'),
        project_name=project,
        user_domain_id='default',
        project_domain_id='default')
    return keystone_session.Session(auth=auth)


def _get_nova_client(config, project):
    """Return a new nova client tailored to the given project.

    Arguments:
        config (dict): a dictionary with the session configuration keys: ``auth_url``, ``username``, ``password``,
            ``nova_api_version``, ``timeout``.
        project (str): the project to scope the `novaclient` session to.

    Returns:
        novaclient.client.Client: the novaclient Client instance, already authenticated.

    """
    return nova_client.Client(
        config.get('nova_api_version', '2'),
        session=_get_keystone_session(config, project),
        endpoint_type='public',
        timeout=config.get('timeout', 10))


class OpenStackQuery(BaseQuery):
    r"""OpenStackQuery query builder.

    Query VMs deployed in an OpenStack infrastructure using the API.
    This is an optional backend, its dependencies will not be installed automatically, see the Installation section
    of the documentation for more details.

    * Each query can specify multiple parameters to filter the hosts selection in the form ``key:value``.
    * The special ``project`` key allow to filter by the OpenStack project name: ``project:project_name``. If not
      specified all the visible and enabled projects will be queried.
    * Any other ``key:value`` pair will be passed as is to the
      `OpenStack Compute API list-servers <https://developer.openstack.org/api-ref/compute/#list-servers>`_. Multiple
      filters can be added separated by space. The value can be enclosed in single or double quotes:
      ``name:"host1.*\.domain" image:UUID``
    * By default the filters ``status:ACTIVE`` and ``vm_state:ACTIVE`` are also added, but will be overridden if
      specified in the query.
    * To mix multiple selections the general grammar must be used with multiple subqueries:
      ``O{project:project1} or O{project:project2}``
    * The special query ``*`` is a shortcut to select all hosts in all OpenStack projects.
    * See the example configuration in ``doc/examples/config.yaml`` for all the OpenStack-related parameters that can
      be set.

    Some query examples:

    * All hosts in all OpenStack projects: ``*``
    * All hosts in a specific OpenStack project: ``project:project_name``
    * Filter hosts using any parameter allowed by the OpenStack list-servers API: ``name:host1 image:UUID``
      See `OpenStack Compute API list-servers <https://developer.openstack.org/api-ref/compute/#list-servers>`_ for
      more details. Multiple filters can be added separated by space. The value can be enclosed in single or double
      quotes. If the ``project`` key is not specified the hosts will be selected from all projects.
    * To mix multiple selections the general grammar must be used with multiple subqueries:
      ``O{project:project1} or O{project:project2}``
    """

    grammar = grammar()
    """:py:class:`pyparsing.ParserElement`: load the grammar parser only once in a singleton-like way."""

    def __init__(self, config):
        """Override parent class constructor for specific setup.

        :Parameters:
            according to parent :py:meth:`cumin.backends.BaseQuery.__init__`.

        """
        super().__init__(config)
        self.openstack_config = self.config.get('openstack', {})
        self.search_project = None
        self.search_params = self._get_default_search_params()

    def _get_default_search_params(self):
        """Return the default search parameters dictionary and set the project, if configured.

        Returns:
            dict: the dictionary with the default search parameters.

        """
        params = {'status': 'ACTIVE', 'vm_state': 'ACTIVE'}
        config_params = self.openstack_config.get('query_params', {})

        if 'project' in config_params:
            self.search_project = config_params.pop('project')

        params.update(config_params)
        return params

    def _build(self, query_string):
        """Override parent class _build method to reset the search parameters.

        :Parameters:
            according to parent :py:meth:`cumin.backends.BaseQuery._build`.

        """
        self.search_params = self._get_default_search_params()
        super()._build(query_string)

    def _execute(self):
        """Concrete implementation of parent abstract method.

        :Parameters:
            according to parent :py:meth:`cumin.backends.BaseQuery._execute`.

        Returns:
            ClusterShell.NodeSet.NodeSet: with the FQDNs of the matching hosts.

        """
        if self.search_project is None:
            hosts = nodeset()
            for project in self._get_projects():
                hosts |= self._get_project_hosts(project)
        else:
            hosts = self._get_project_hosts(self.search_project)

        return hosts

    def _parse_token(self, token):
        """Concrete implementation of parent abstract method.

        :Parameters:
            according to parent :py:meth:`cumin.backends.BaseQuery._parse_token`.

        Raises:
            cumin.backends.InvalidQueryError: on internal parsing error.

        """
        if not isinstance(token, pp.ParseResults):  # pragma: no cover - this should never happen
            raise InvalidQueryError('Expecting ParseResults object, got {type}: {token}'.format(
                type=type(token), token=token))

        token_dict = token.asDict()
        self.logger.trace('Token is: %s | %s', token_dict, token)

        if 'key' in token_dict and 'value' in token_dict:
            if token_dict['key'] == 'project':
                self.search_project = token_dict['value']
            else:
                self.search_params[token_dict['key']] = token_dict['value']
        elif 'all' in token_dict:
            pass  # nothing to do, search_project and search_params have the right defaults
        else:  # pragma: no cover - this should never happen
            raise InvalidQueryError('Got unexpected token: {token}'.format(token=token))

    def _get_projects(self):
        """Get all the project names from keystone API, filtering out the special `admin` project. Is a `generator`.

        Yields:
            str: the project name for all the selected projects.

        """
        client = keystone_client.Client(
            session=_get_keystone_session(self.openstack_config), timeout=self.openstack_config.get('timeout', 10))
        return (project.name for project in client.projects.list(enabled=True) if project.name != 'admin')

    def _get_project_hosts(self, project):
        """Return a NodeSet with the list of matching hosts based for the project based on the search parameters.

        Arguments:
            project (str): the project name where to get the list of hosts.

        Returns:
            ClusterShell.NodeSet.NodeSet: with the FQDNs of the matching hosts.

        """
        client = _get_nova_client(self.openstack_config, project)

        domain = ''
        domain_suffix = self.openstack_config.get('domain_suffix', None)
        if domain_suffix is not None:
            if domain_suffix[0] != '.':
                domain = '.{suffix}'.format(suffix=domain_suffix)
            else:
                domain = domain_suffix

        return nodeset_fromlist('{host}.{project}{domain}'.format(host=server.name, project=project, domain=domain)
                                for server in client.servers.list(search_opts=self.search_params))


GRAMMAR_PREFIX = 'O'
""":py:class:`str`: the prefix associate to this grammar, to register this backend into the general grammar.
Required by the backend auto-loader in :py:meth:`cumin.grammar.get_registered_backends`."""

query_class = OpenStackQuery  # pylint: disable=invalid-name
"""Required by the backend auto-loader in :py:meth:`cumin.grammar.get_registered_backends`."""
