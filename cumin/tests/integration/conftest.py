"""Pytest customization for integration tests."""
import pytest


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):  # pylint: disable=unused-argument
    """If a custom variant_params marker is set, print a section with its content."""
    outcome = yield
    marker = item.get_marker('variant_params')
    if marker:
        rep = outcome.get_result()
        rep.sections.insert(0, ('test_variant parameters', marker.args))
