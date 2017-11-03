"""Query grammar definition."""
import importlib
import pkgutil

from collections import namedtuple

import pyparsing as pp

from cumin import backends, CuminError


INTERNAL_BACKEND_PREFIX = 'cumin.backends'


Backend = namedtuple('Backend', ['keyword', 'name', 'cls'])
""":py:func:`collections.namedtuple` that define a Backend object.

Keyword Arguments:
    keyword (str): The backend keyword to be used in the grammar.
    name (str): The backend name.
    cls (BaseQuery): The backend class object.
"""


def get_registered_backends(external=()):
    """Get a mapping of all the registered backends with their keyword.

    Arguments:
        external (list, tuple, optional): external backend modules to register.

    Returns:
        dict: A dictionary with a ``{keyword: Backend object}`` mapping for each available backend.

    Raises:
        cumin.CuminError: If unable to register a backend.

    """
    available_backends = {}
    backend_names = ['{prefix}.{backend}'.format(prefix=INTERNAL_BACKEND_PREFIX, backend=name)
                     for _, name, ispkg in pkgutil.iter_modules(backends.__path__) if not ispkg]

    for name in backend_names + list(external):
        keyword, backend = _import_backend(name, available_backends)
        if keyword is not None and backend is not None:
            available_backends[keyword] = backend

    return available_backends


def grammar(backend_keys):
    """Define the main multi-query grammar.

    Cumin provides a user-friendly generic query language that allows to combine the results of subqueries for multiple
    backends:

    * Each query part can be composed with the others using boolean operators ``and``, ``or``, ``and not``, ``xor``.
    * Multiple query parts can be grouped together with parentheses ``(``, ``)``.
    * Specific backend query ``I{backend-specific query syntax}``, where ``I`` is an identifier for the specific
      backend.
    * Alias replacement, according to aliases defined in the configuration file ``A:group1``.
    * The identifier ``A`` is reserved for the aliases replacement and cannot be used to identify a backend.
    * A complex query example: ``(D{host1 or host2} and (P{R:Class = Role::MyClass} and not A:group1)) or D{host3}``

    Backus-Naur form (BNF) of the grammar::

              <grammar> ::= <item> | <item> <boolean> <grammar>
                 <item> ::= <backend_query> | <alias> | "(" <grammar> ")"
        <backend_query> ::= <backend> "{" <query> "}"
                <alias> ::= A:<alias_name>
              <boolean> ::= "and not" | "and" | "xor" | "or"

    Given that the pyparsing library defines the grammar in a BNF-like style, for the details of the tokens not
    specified above check directly the source code.

    Arguments:
        backend_keys (list): list of the GRAMMAR_PREFIX for each registered backend.

    Returns:
        pyparsing.ParserElement: the grammar parser.

    """
    # Boolean operators
    boolean = (pp.CaselessKeyword('and not').leaveWhitespace() | pp.CaselessKeyword('and') |
               pp.CaselessKeyword('xor') | pp.CaselessKeyword('or'))('bool')

    # Parentheses
    lpar = pp.Literal('(')('open_subgroup')
    rpar = pp.Literal(')')('close_subgroup')

    # Backend query: P{PuppetDB specific query}
    query_start = pp.Combine(pp.oneOf(backend_keys, caseless=True)('backend') + pp.Literal('{'))
    query_end = pp.Literal('}')
    # Allow the backend specific query to use the end_query token as well, as long as it's in a quoted string
    # and fail if there is a query_start token before the first query_end is reached
    query = pp.SkipTo(query_end, ignore=pp.quotedString, failOn=query_start)('query')
    backend_query = pp.Combine(query_start + query + query_end)

    # Alias
    alias = pp.Combine(pp.CaselessKeyword('A') + ':' + pp.Word(pp.alphanums + '-_.+')('alias'))

    # Final grammar, see the docstring for its BNF based on the tokens defined above
    # Group are used to have an easy dictionary access to the parsed results
    full_grammar = pp.Forward()
    item = backend_query | alias | lpar + full_grammar + rpar
    full_grammar << pp.Group(item) + pp.ZeroOrMore(pp.Group(boolean + item))  # pylint: disable=expression-not-assigned

    return full_grammar


def _import_backend(module, available_backends):
    """Dynamically import a backend for Cumin and validate it.

    Arguments:
        module (str): the full module name of the backend to register. Must be importable from Python ``PATH``.
        available_backends (dict): dictionary with a ``{keyword: Backend object}`` mapping for all registered backends.

    Returns:
        tuple: with two elements: ``(keyword, Backend object)`` of the imported backend.

    """
    try:
        backend = importlib.import_module(module)
    except ImportError as e:
        if module.startswith(INTERNAL_BACKEND_PREFIX):
            return (None, None)  # Internal backend not available, are all the dependencies installed?
        else:
            raise CuminError("Unable to import backend '{module}': {e}".format(module=module, e=e))

    name = module.split('.')[-1]
    message = "Unable to register backend '{name}' in module '{module}'".format(name=name, module=module)
    try:
        keyword = backend.GRAMMAR_PREFIX
    except AttributeError:
        raise CuminError('{message}: GRAMMAR_PREFIX module attribute not found'.format(message=message))

    if keyword in available_backends:
        raise CuminError(("{message}: keyword '{key}' already registered: {backends}").format(
            message=message, key=keyword, backends=available_backends))

    try:
        class_obj = backend.query_class
    except AttributeError:
        raise CuminError('{message}: query_class module attribute not found'.format(message=message))

    if not issubclass(class_obj, backends.BaseQuery):
        raise CuminError('{message}: query_class module attribute is not a subclass of cumin.backends.BaseQuery')

    return (keyword, Backend(name=name, keyword=keyword, cls=class_obj))
