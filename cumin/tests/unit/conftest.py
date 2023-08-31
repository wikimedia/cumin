"""Pytest customization for unit tests."""
import pytest
import requests_mock

from cumin.backends import puppetdb


def _requests_matcher_non_existent(request):
    return request.json() == {'query': '["or", ["=", "certname", "non_existent_host"]]'}


def _requests_matcher_invalid(request):
    return request.json() == {'query': '["or", ["=", "certname", "invalid_query"]]'}


@pytest.fixture()
def mocked_requests():
    """Set mocked requests fixture."""
    with requests_mock.Mocker() as mocker:
        yield mocker


@pytest.fixture()
def query_requests(mocked_requests):  # pylint: disable=redefined-outer-name
    """Set the requests library mock for each test and PuppetDB API version."""
    query = puppetdb.PuppetDBQuery({})
    for endpoint in ('nodes', 'resources'):
        mocked_requests.register_uri(
            'POST', query.url + endpoint, status_code=200, complete_qs=True,
            json=[
                {'certname': endpoint + '_host1', 'key': 'value1'},
                {'certname': endpoint + '_host2', 'key': 'value2'}
            ])

    # Register a requests response for a non matching query
    mocked_requests.register_uri(
        'POST', query.url + query.endpoints['F'], status_code=200, json=[], complete_qs=True,
        additional_matcher=_requests_matcher_non_existent)
    # Register a requests response for an invalid query
    mocked_requests.register_uri(
        'POST', query.url + query.endpoints['F'], status_code=400, complete_qs=True,
        additional_matcher=_requests_matcher_invalid)

    return query, mocked_requests
