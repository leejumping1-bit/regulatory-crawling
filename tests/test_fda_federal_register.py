import json
from types import SimpleNamespace

import pytest

from collectors import fda


def response(results, pages=1):
    return SimpleNamespace(ok=True, text=json.dumps({'count': len(results), 'total_pages': pages, 'results': results}))


def document(**overrides):
    value = {'document_number': '2026-12345', 'title': 'Medical Devices; Draft Guidance for Industry',
             'type': 'Notice', 'action': 'Notice of availability.', 'publication_date': '2026-04-01',
             'effective_on': None, 'html_url': 'https://www.federalregister.gov/documents/2026/04/01/2026-12345/example',
             'abstract': 'Official abstract.', 'agencies': [{'slug': 'food-and-drug-administration'}]}
    value.update(overrides)
    return value


def test_discovery_preserves_official_record(monkeypatch):
    monkeypatch.setattr(fda, 'federal_register_fetch', lambda url: response([document()]))
    items = fda.discover_federal_register(2026, 1)
    assert len(items) == 1
    item = items[0]
    assert item['title'] == 'Medical Devices; Draft Guidance for Industry'
    assert item['doc_no'] == '2026-12345'
    assert item['publish_date'] == '2026-04-01'
    assert item['effective_date'] == ''
    assert item['summary'] == '[Federal Register 공식 초록 (영문)]\nOfficial abstract.'
    assert item['url'].startswith('https://www.federalregister.gov/documents/')
    assert item['document_status'] == 'draft'
    assert not item.get('gap_analysis')


def test_pages_are_fetched_and_deduplicated(monkeypatch):
    urls = []
    def fetch(url):
        urls.append(url)
        page = len(urls)
        rows = [document()] if page == 1 else [document(), document(document_number='2026-23456')]
        return response(rows, pages=2)
    monkeypatch.setattr(fda, 'federal_register_fetch', fetch)
    items = fda.discover_federal_register(2026, 1)
    assert [x['doc_no'] for x in items] == ['2026-12345', '2026-23456']
    assert len(urls) == 2 and 'page=2' in urls[1]


def test_run_combines_discovery_with_existing_collector(monkeypatch):
    monkeypatch.setattr(fda, 'discover_federal_register', lambda *args: [{'doc_no': '2026-12345'}])
    monkeypatch.setattr(fda, '_run_part_820', lambda *args: ([{'doc_no': '21 CFR Part 820'}], None), raising=False)
    items, error = fda.run(2026, 1)
    assert error is None
    assert [x['doc_no'] for x in items] == ['21 CFR Part 820', '2026-12345']


def test_rejects_unsafe_incomplete_and_nonmedical_items(monkeypatch):
    rows = [document(agencies=[{'slug': 'other-agency'}]),
            document(title='Drug Guidance', abstract='A drug therapy.', raw_text_url='https://www.federalregister.gov/documents/full_text/text/2026/04/01/2026-12345.txt'),
            document(title='Medical Devices; Public Meeting', type='Notice'),
            document(title=''),
            document(html_url='https://example.com/document'),
            document(publication_date=None),
            document(document_number='2026-99999', type='Rule', title='Medical Devices; Classification',
                     action='Final order', effective_on='2026-05-01')]
    monkeypatch.setattr(fda, 'federal_register_fetch', lambda url: response(rows))
    monkeypatch.setattr(fda, 'fetch_fr_text', lambda url: 'A drug therapy.')
    items = fda.discover_federal_register(2026, 1)
    assert len(items) == 1
    assert items[0]['doc_no'] == '2026-99999'
    assert items[0]['effective_date'] == '2026-05-01'
    assert items[0]['document_status'] == 'final'


def test_zero_result_real_api_shape_is_success(monkeypatch):
    monkeypatch.setattr(fda, 'federal_register_fetch', lambda url: SimpleNamespace(ok=True, text='{"description":"No matches","count":0}'))
    assert fda.discover_federal_register(2100, 1) == []


def test_inconsistent_empty_response_is_failure_not_zero(monkeypatch):
    monkeypatch.setattr(fda, 'federal_register_fetch', lambda url: SimpleNamespace(ok=True, text=json.dumps({'count': 42, 'total_pages': 0, 'results': []})))
    with pytest.raises(RuntimeError, match='Federal Register'):
        fda.discover_federal_register(2026, 1)
