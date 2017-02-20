"""Vulture whitelist to avoid false positives."""


class Whitelist:
    """Helper class that allows mocking Python objects."""

    def __getattr__(self, _):
        """Mocking magic method __getattr__."""
        pass


whitelist_logging = Whitelist()
whitelist_logging.raiseExceptions

whitelist_cli = Whitelist()
whitelist_cli.run.h

whitelist_tests_integration_conftest = Whitelist()
whitelist_tests_integration_conftest.pytest_cmdline_preparse
whitelist_tests_integration_conftest.pytest_runtest_makereport

whitelist_tests_integration_test_cli_TestCLI = Whitelist()
whitelist_tests_integration_test_cli_TestCLI.setup_method
