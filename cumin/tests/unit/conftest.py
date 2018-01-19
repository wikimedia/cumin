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


@pytest.fixture(params=(3, 4))
def query_requests(request, mocked_requests):  # pylint: disable=redefined-outer-name
    """Set the requests library mock for each test and PuppetDB API version."""
    if request.param == 3:  # PuppetDB API v3
        query = puppetdb.PuppetDBQuery(
            {'puppetdb': {'api_version': 3, 'urllib3_disable_warnings': ['SubjectAltNameWarning']}})
        for endpoint, key in query.hosts_keys.items():
            mocked_requests.register_uri('GET', query.url + endpoint + '?query=', status_code=200, json=[
                {key: endpoint + '_host1', 'key': 'value1'}, {key: endpoint + '_host2', 'key': 'value2'}])

        # Register a requests response for a non matching query
        mocked_requests.register_uri(
            'GET', query.url + query.endpoints['F'] + '?query=["or", ["=", "name", "non_existent_host"]]',
            status_code=200, json=[], complete_qs=True)
        # Register a requests response for an invalid query
        mocked_requests.register_uri(
            'GET', query.url + query.endpoints['F'] + '?query=["or", ["=", "name", "invalid_query"]]',
            status_code=400, complete_qs=True)

    elif request.param == 4:  # PuppetDB API v4
        query = puppetdb.PuppetDBQuery({})
        for endpoint, key in query.hosts_keys.items():
            mocked_requests.register_uri(
                'POST', query.url + endpoint, status_code=200, complete_qs=True,
                json=[{key: endpoint + '_host1', 'key': 'value1'}, {key: endpoint + '_host2', 'key': 'value2'}])

        # Register a requests response for a non matching query
        mocked_requests.register_uri(
            'POST', query.url + query.endpoints['F'], status_code=200, json=[], complete_qs=True,
            additional_matcher=_requests_matcher_non_existent)
        # Register a requests response for an invalid query
        mocked_requests.register_uri(
            'POST', query.url + query.endpoints['F'], status_code=400, complete_qs=True,
            additional_matcher=_requests_matcher_invalid)

    return query, mocked_requests
