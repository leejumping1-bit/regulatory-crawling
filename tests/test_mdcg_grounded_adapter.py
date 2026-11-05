from types import SimpleNamespace

import pytest

from collectors import mdcg_grounded_adapter as adapter

OFFICIAL = 'https://health.ec.europa.eu/document/download/old'
NB = 'https://www.bsigroup.com/documents/old.pdf'
DOC = 'MDCG 2020-16 rev.5'


def lookup(links, text='MDCG 2020-16 rev.4\nActual text', **kwargs):
    return adapter.discover_previous(DOC, search=lambda q: links,
        download=lambda url: b'pdf', extract=lambda data: (text,), **kwargs)


def test_verified_predecessor_uses_pdf_not_search_snippet():
    result = lookup([OFFICIAL])
    assert result.status == 'verified'
    assert result.official[0].pages == ('MDCG 2020-16 rev.4\nActual text',)
    assert result.exhaustive is False


def test_empty_failed_and_unverified_discovery_are_distinct():
    assert lookup([]).status == 'no_results'
    def fail(query):
        raise RuntimeError('network')
    assert adapter.discover_previous(DOC, search=fail).status == 'unavailable'
    result = lookup([OFFICIAL], text='MDCG 2020-16 rev.5\nwrong version')
    assert result.status == 'nonexhaustive' and result.failed == 1


@pytest.mark.parametrize('url', [
    'https://health.ec.europa.eu.evil.test/a.pdf',
    'http://health.ec.europa.eu/a.pdf',
    'https://health.ec.europa.eu@evil.test/a.pdf',
    'https://health.ec.europa.eu:444/a.pdf',
    'https://someblog.test/a.pdf',
    'https://www.bsigroup.com/blog/post',
])
def test_disallowed_hosts_and_non_document_paths_are_never_fetched(url):
    result = lookup([url], include_notified_bodies=True)
    assert result.status == 'nonexhaustive' and result.rejected == 1


def test_notified_body_is_opt_in_and_labeled_supplemental():
    assert lookup([NB]).rejected == 1
    result = lookup([NB], include_notified_bodies=True)
    assert result.status == 'nonexhaustive' and not result.official
    assert result.supplemental[0].url == NB


@pytest.mark.parametrize('text', [
    'MDCG 2020-17 rev.4\nwrong number',
    'MDCG 2020-16 rev.5\nMDCG 2020-16 rev.4',
    'MDCG 2020-16 rev.4 Appendix',
    'Commentary on MDCG 2020-16 rev.4\nNot the guidance',
    'Intro\n' * 13 + 'MDCG 2020-16 rev.4',
])
def test_header_verification_rejects_wrong_ambiguous_or_body_identity(text):
    assert not lookup([OFFICIAL], text=text).official


def test_original_predecessor_and_duplicate_candidates():
    result = adapter.discover_previous('MDCG 2020-16 rev.1', search=lambda q: [OFFICIAL, OFFICIAL],
        download=lambda u: b'pdf', extract=lambda b: ('MDCG 2020-16\nOriginal',))
    assert len(result.official) == 1 and result.official[0].revision == 0


def test_search_receives_query_and_invalid_identity_never_searches():
    queries = []
    adapter.discover_previous(DOC, search=lambda q: queries.append(q) or [])
    assert 'site:health.ec.europa.eu' in queries[0] and '2020-16' in queries[0]
    assert adapter.discover_previous('MDCG 2020-16', search=lambda q: pytest.fail()).status == 'unavailable'


def test_default_download_refuses_redirects(monkeypatch):
    calls = []
    class Response:
        def __init__(self, status):
            self.status_code = status
        def __enter__(self): return self
        def __exit__(self, *args): pass
    def get(url, **kwargs):
        calls.append((url, kwargs))
        return Response(404 if url.endswith('/robots.txt') else 302)
    monkeypatch.setattr(adapter.requests, 'get', get)
    with pytest.raises(ValueError):
        adapter._download(OFFICIAL)
    assert len(calls) == 2 and all(not opts['allow_redirects'] for _, opts in calls)


def test_official_discovery_is_default_search(monkeypatch):
    seen = []
    monkeypatch.setattr(adapter, 'discover_official_links', lambda number, revision: seen.append((number, revision)) or [])
    assert adapter.discover_previous(DOC).status == 'no_results'
    assert seen == [('2020-16', 4)]
