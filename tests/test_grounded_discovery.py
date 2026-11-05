import pytest
pytestmark = pytest.mark.skip(reason='Google grounding has been permanently disabled; see test_mdcg_no_google.py')

from types import SimpleNamespace as NS

from collectors.grounded_discovery import discover_links


def test_grounded_sources_only_and_allowlist():
    chunks = [NS(web=NS(uri='https://health.ec.europa.eu/document/a')),
              NS(web=NS(uri='https://blog.example/a'))]
    response = NS(candidates=[NS(grounding_metadata=NS(web_search_queries=['query'], grounding_chunks=chunks))], text='https://evil.example')
    calls = []
    result = discover_links('MDCG 2020-16', api_key='fake', generate=lambda query: calls.append(query) or response)
    assert result == ['https://health.ec.europa.eu/document/a']
    assert calls == ['MDCG 2020-16']


def test_google_redirect_resolves_only_to_allowed_source_without_following():
    import collectors.grounded_discovery as gd
    from unittest.mock import patch
    uri = 'https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc'
    response = NS(candidates=[NS(grounding_metadata=NS(web_search_queries=['q'], grounding_chunks=[NS(web=NS(uri=uri))]))])
    with patch.object(gd.requests, 'get', return_value=NS(status_code=302, headers={'Location': 'https://health.ec.europa.eu/old.pdf'})) as get:
        assert discover_links('q', api_key='fake', generate=lambda _: response) == ['https://health.ec.europa.eu/old.pdf']
        assert get.call_args.kwargs['allow_redirects'] is False
        assert get.call_args.kwargs['timeout'] == 4


def test_missing_redirect_location_is_an_explicit_failure():
    import collectors.grounded_discovery as gd
    import pytest
    from unittest.mock import patch
    uri = 'https://vertexaisearch.cloud.google.com/grounding-api-redirect/a'
    response = NS(candidates=[NS(grounding_metadata=NS(web_search_queries=['q'], grounding_chunks=[NS(web=NS(uri=uri))]))])
    with patch.object(gd.requests, 'get', return_value=NS(status_code=302, headers={})):
        with pytest.raises(gd.GroundedDiscoveryError, match='redirect'):
            discover_links('q', api_key='fake', generate=lambda _: response)


def test_fail_closed_without_grounding_or_key_and_sanitize_api_errors(monkeypatch):
    import pytest
    from collectors.grounded_discovery import GroundedDiscoveryError
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    with pytest.raises(GroundedDiscoveryError, match='not configured'):
        discover_links('q')
    with pytest.raises(GroundedDiscoveryError, match='grounding metadata'):
        discover_links('q', api_key='fake', generate=lambda _: NS(candidates=[]))
    def fail(_):
        raise RuntimeError('secret-fake')
    with pytest.raises(GroundedDiscoveryError) as error:
        discover_links('q', api_key='secret-fake', generate=fail)
    assert 'secret-fake' not in str(error.value)


def test_rejects_host_spoofs_and_non_https():
    urls = ['https://health.ec.europa.eu.evil.test/a', 'https://health.ec.europa.eu@evil.test/a',
            'http://health.ec.europa.eu/a', 'https://health.ec.europa.eu:444/a',
            'https://www.bsigroup.com/news/a']
    response = NS(candidates=[NS(grounding_metadata=NS(web_search_queries=['q'], grounding_chunks=[NS(web=NS(uri=u)) for u in urls]))])
    assert discover_links('q', api_key='fake', generate=lambda _: response) == [urls[-1]]


def test_rejects_redirect_to_untrusted_host_without_following():
    import collectors.grounded_discovery as gd
    from unittest.mock import patch
    uri = 'https://vertexaisearch.cloud.google.com/grounding-api-redirect/a'
    response = NS(candidates=[NS(grounding_metadata=NS(web_search_queries=['q'], grounding_chunks=[NS(web=NS(uri=uri))]))])
    with patch.object(gd.requests, 'get', return_value=NS(status_code=302, headers={'Location': 'https://blog.example/a'})) as get:
        assert discover_links('q', api_key='fake', generate=lambda _: response) == []
        assert get.call_count == 1


def test_real_calls_are_limited_per_process(monkeypatch):
    import collectors.grounded_discovery as gd
    import pytest
    response = NS(candidates=[NS(grounding_metadata=NS(web_search_queries=['q'], grounding_chunks=[NS(web=NS(uri='https://health.ec.europa.eu/a'))]))])
    monkeypatch.setattr(gd, '_request_count', 0, raising=False)
    monkeypatch.setenv('REVISION_SEARCH_MAX_PER_RUN', '1')
    monkeypatch.setattr(gd, '_generate', lambda q, k: response)
    assert gd.discover_links('q', api_key='fake')
    with pytest.raises(gd.GroundedDiscoveryError, match='budget'):
        gd.discover_links('q', api_key='fake')


def test_real_sdk_serializes_google_search_tool(monkeypatch):
    import json
    import pytest
    genai = pytest.importorskip('google.genai')
    httpx = pytest.importorskip('httpx')
    import collectors.grounded_discovery as gd
    requests_seen = []
    def handler(request):
        requests_seen.append(request)
        return httpx.Response(200, json={'candidates': [{'content': {'parts': [{'text': 'ignore me'}]},
            'groundingMetadata': {'webSearchQueries': ['q'], 'groundingChunks': [{'web': {'uri': 'https://health.ec.europa.eu/a'}}]}}]})
    real_client = genai.Client
    transport = httpx.MockTransport(handler)
    def client(**kwargs):
        kwargs['http_options'].httpx_client = httpx.Client(transport=transport)
        return real_client(**kwargs)
    monkeypatch.setattr(genai, 'Client', client)
    assert gd.discover_links('q', api_key='fake') == ['https://health.ec.europa.eu/a']
    payload = json.loads(requests_seen[0].content)
    assert payload['tools'] == [{'googleSearch': {}}]
    assert 'gemini-2.5-flash' in str(requests_seen[0].url)
