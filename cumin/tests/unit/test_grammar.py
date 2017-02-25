"""Grammar tests"""
import unittest

from cumin.grammar import grammar
from cumin.tests import get_fixture


class TestGrammar(unittest.TestCase):
    """Grammar class tests"""

    def _get_category_key_token(self, category='F', key='key1', operator='=', value='value1'):
        """Generate and return a category token string and it's expected dictionary of tokens when parsed"""
        expected = {'category': category, 'key': key, 'operator': operator, 'value': value}
        token = '{category}:{key} {operator} {value}'.format(**expected)
        return token, expected

    def test_valid_strings(self):
        """Run quick pyparsing test over valid grammar strings"""
        results = grammar.runTests(get_fixture('valid_grammars.txt', as_string=True))
        self.assertTrue(results[0])

    def test_invalid_strings(self):
        """Run quick pyparsing test over invalid grammar strings"""
        results = grammar.runTests(get_fixture('invalid_grammars.txt', as_string=True), failureTests=True)
        self.assertTrue(results[0])

    def test_single_category_key_token(self):
        """A valid single token with a category that has key is properly parsed and interpreted"""
        token, expected = self._get_category_key_token()
        parsed = grammar.parseString(token, parseAll=True)
        self.assertDictEqual(parsed[0].asDict(), expected)

    def test_hosts_selection(self):
        """A host selection is properly parsed and interpreted"""
        hosts = {'hosts': 'host[10-20,30-40].domain'}
        parsed = grammar.parseString(hosts['hosts'], parseAll=True)
        self.assertDictEqual(parsed[0].asDict(), hosts)
