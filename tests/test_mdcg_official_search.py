import pytest
from collectors import mdcg_official_search as official
from collectors import mdcg_grounded_adapter as adapter


def test_official_search_follows_only_official_result_pages_and_extracts_documents():
    page = 'https://health.ec.europa.eu/latest-updates/mdcg-2020-16-rev4_en'
    pdf = 'https://health.ec.europa.eu/document/download/old_en'
    seen = []
    def fetch(url):
        seen.append(url)
        if url.startswith('https://ec.europa.eu/search/'):
            return f'<main><a href="{page}">MDCG 2020-16 rev.4</a><a href="https://evil.test/x">MDCG 2020-16 rev.4</a></main>'
        return '<main><a href="/document/download/old_en">PDF</a><a href="https://evil.test/old.pdf">bad</a></main>'
    assert official.discover_official_links('2020-16', 4, fetch=fetch) == [pdf]
    assert seen == [seen[0], page]


def test_adapter_falls_back_when_grounding_fails(monkeypatch):
    def fail(query): raise RuntimeError('429')
    monkeypatch.setattr(adapter, 'discover_links', fail)
    monkeypatch.setattr(adapter, 'discover_official_links', lambda number, rev: ['https://health.ec.europa.eu/document/download/old'])
    result = adapter.discover_previous('MDCG 2020-16 rev.5', download=lambda u: b'pdf', extract=lambda b: ('MDCG 2020-16 rev.4\nText',))
    assert result.status == 'verified' and not result.exhaustive


def test_no_results_not_exhaustive_on_official_search(monkeypatch):
    def fail(query): raise RuntimeError('404')
    monkeypatch.setattr(adapter, 'discover_links', fail)
    monkeypatch.setattr(adapter, 'discover_official_links', lambda number, rev: [])
    result = adapter.discover_previous('MDCG 2020-16 rev.5')
    assert result.status == 'no_results' and not result.exhaustive
