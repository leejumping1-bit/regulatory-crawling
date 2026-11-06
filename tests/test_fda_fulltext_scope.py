import json
from types import SimpleNamespace
import pytest
from collectors import fda


def row(n='2026-12345'):
    return {'document_number': n, 'title': 'A classification', 'abstract': 'A device.', 'type': 'Rule', 'publication_date': '2026-01-01', 'html_url': f'https://www.federalregister.gov/documents/2026/01/01/{n}/example', 'raw_text_url': f'https://www.federalregister.gov/documents/full_text/text/2026/01/01/{n}.txt', 'agencies': [{'slug': 'food-and-drug-administration'}]}


def test_body_term_included(monkeypatch):
    monkeypatch.setattr(fda, 'federal_register_fetch', lambda url: SimpleNamespace(ok=True, text=json.dumps({'count': 1, 'total_pages': 1, 'results': [row()]})))
    monkeypatch.setattr(fda, 'fetch_fr_text', lambda url: 'Background: The medical device is regulated.')
    assert [x['doc_no'] for x in fda.discover_federal_register()] == ['2026-12345']


def test_failed_body_preserves_partial_results_and_reports_incomplete(monkeypatch):
    positive = dict(row('2026-12346'), title='Medical devices')
    monkeypatch.setattr(fda, 'federal_register_fetch', lambda url: SimpleNamespace(ok=True, text=json.dumps({'count': 2, 'total_pages': 1, 'results': [positive, row()]})))
    def fail(url): raise RuntimeError('network failure')
    monkeypatch.setattr(fda, 'fetch_fr_text', fail)
    monkeypatch.setattr(fda, '_run_part_820', lambda *a: ([{'doc_no': '21 CFR Part 820'}], None))
    items, error = fda.run()
    assert [x['doc_no'] for x in items] == ['21 CFR Part 820', '2026-12346']
    assert error and '2026-12345' in error.error


def test_external_body_url_rejected(monkeypatch):
    bad = dict(row(), raw_text_url='https://evil.example/test')
    monkeypatch.setattr(fda, 'federal_register_fetch', lambda url: SimpleNamespace(ok=True, text=json.dumps({'count': 1, 'total_pages': 1, 'results': [bad]})))
    monkeypatch.setattr(fda, 'fetch_fr_text', lambda url: pytest.fail('unsafe URL fetched'))
    with pytest.raises(fda.IncompleteFederalRegister): fda.discover_federal_register()


def test_true_ide_but_not_generic_device():
    assert fda.has_explicit_device_term('Investigational Device Exemption (IDE) applications')
    assert not fda.has_explicit_device_term('The device is used for drug delivery')


def test_budget_exhaustion_is_incomplete_and_does_not_fetch(monkeypatch):
    monkeypatch.setattr(fda, 'FR_TEXT_LIMIT', 0)
    monkeypatch.setattr(fda, 'federal_register_fetch', lambda url: SimpleNamespace(ok=True, text=json.dumps({'count': 1, 'total_pages': 1, 'results': [row()]})))
    monkeypatch.setattr(fda, 'fetch_fr_text', lambda url: pytest.fail('budget exceeded'))
    with pytest.raises(fda.IncompleteFederalRegister, match='2026-12345'):
        fda.discover_federal_register()


def test_html_attributes_are_not_body_content():
    p = fda._VisibleText()
    p.feed('<a href="https://example.com/medical-device">A generic device</a><script>medical device</script>')
    assert not fda.has_explicit_device_term(' '.join(p.parts))


def test_raw_url_must_match_document_date_and_no_redirect_target():
    assert fda._valid_raw_url(row()['raw_text_url'], '2026-12345', '2026-01-01')
    assert not fda._valid_raw_url(row()['raw_text_url'] + '?next=https://evil.example', '2026-12345', '2026-01-01')
    assert not fda._valid_raw_url(row()['raw_text_url'], '2026-12346', '2026-01-01')
    assert not fda._valid_raw_url(row()['raw_text_url'].replace('www.federalregister.gov', 'www.federalregister.gov.evil.example'), '2026-12345', '2026-01-01')
