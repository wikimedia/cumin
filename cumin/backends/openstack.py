"""OpenStack backend."""
import pyparsing as pp

from ClusterShell.NodeSet import NodeSet
from keystoneauth1 import session as keystone_session
from keystoneauth1.identity import v3 as keystone_identity
from keystoneclient.v3 import client as keystone_client
from novaclient import client as nova_client

from cumin.backends import BaseQuery, InvalidQueryError


def grammar():
    """Define the query grammar.

    Some query examples:
    - All hosts in all OpenStack projects: `*`
    - All hosts in a specific OpenStack project: `project:project_name`
    - Filter hosts using any parameter allowed by the OpenStack list-servers API: `name:host1 image:UUID`
      See https://developer.openstack.org/api-ref/compute/#list-servers for more details.
      Multiple filters can be added separated by space. The value can be enclosed in single or double quotes.
      If the `project` key is not specified the hosts will be selected from all projects.
    - To mix multiple selections the general grammar must be used with multiple subqueries:
      `O{project:project1} or O{project:project2}`

    Backus-Naur form (BNF) of the grammar:
            <grammar> ::= "*" | <items>
              <items> ::= <item> | <item> <whitespace> <items>
               <item> ::= <key>:<value>

    Given that the pyparsing library defines the grammar in a BNF-like style, for the details of the tokens not
    specified above check directly the code.
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
    config  -- a dictionary with the session configuration: auth_url, username, password
    project -- a project to scope the session to. [optional, default: None]
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
    config  -- a dictionary with the session configuration: auth_url, username, password, nova_api_version, timeout
    project -- a project to scope the session to. [optional, default: None]
    """
    return nova_client.Client(
        config.get('nova_api_version', '2'),
        session=_get_keystone_session(config, project),
        endpoint_type='public',
        timeout=config.get('timeout', 10))


class OpenStackQuery(BaseQuery):
    """OpenStackQuery query builder.

    Query VMs deployed in an OpenStack infrastructure using the API.
    """

    grammar = grammar()

    def __init__(self, config, logger=None):
        """Query constructor for the OpenStack backend.

        Arguments: according to BaseQuery interface
        """
        super(OpenStackQuery, self).__init__(config, logger=logger)
        self.openstack_config = self.config.get('openstack', {})
        self.search_project = None
        self.search_params = OpenStackQuery._get_default_search_params()

    @staticmethod
    def _get_default_search_params():
        """Return the default search parameters dictionary."""
        return {'status': 'ACTIVE', 'vm_state': 'ACTIVE'}

    def _build(self, query_string):
        """Override parent class _build method to reset search parameters."""
        self.search_params = OpenStackQuery._get_default_search_params()
        super(OpenStackQuery, self)._build(query_string)

    def _execute(self):
        """Required by BaseQuery."""
        if self.search_project is None:
            hosts = NodeSet()
            for project in self._get_projects():
                hosts |= self._get_project_hosts(project)
        else:
            hosts = self._get_project_hosts(self.search_project)

        return hosts

    def _parse_token(self, token):
        """Required by BaseQuery."""
        if not isinstance(token, pp.ParseResults):  # pragma: no cover - this should never happen
            raise InvalidQueryError('Expecting ParseResults object, got {type}: {token}'.format(
                type=type(token), token=token))

        token_dict = token.asDict()
        self.logger.trace('Token is: {token_dict} | {token}'.format(token_dict=token_dict, token=token))

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
        """Yield the project names for all projects (except admin) from keystone API."""
        client = keystone_client.Client(
            session=_get_keystone_session(self.openstack_config), timeout=self.openstack_config.get('timeout', 10))
        return (project.name for project in client.projects.list(enabled=True) if project.name != 'admin')

    def _get_project_hosts(self, project):
        """Return a NodeSet with the list of matching hosts based for the project based on the search parameters.

        Arguments:
        project -- the project name where to get the list of hosts
        """
        client = _get_nova_client(self.openstack_config, project)

        domain = ''
        domain_suffix = self.openstack_config.get('domain_suffix', None)
        if domain_suffix is not None:
            if domain_suffix[0] != '.':
                domain = '.{suffix}'.format(suffix=domain_suffix)
            else:
                domain = domain_suffix

        return NodeSet.fromlist('{host}.{project}{domain}'.format(host=server.name, project=project, domain=domain)
                                for server in client.servers.list(search_opts=self.search_params))


# Required by the backend auto-loader in cumin.grammar.get_registered_backends()
GRAMMAR_PREFIX = 'O'
query_class = OpenStackQuery  # pylint: disable=invalid-name
