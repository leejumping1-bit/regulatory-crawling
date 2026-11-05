from types import SimpleNamespace
from collectors import mfds, health_canada, mhra, regional_revision_evidence


def _summary_stubs(monkeypatch, module):
    monkeypatch.setattr(module, 'summarize', lambda *a: 'unchanged summary')
    monkeypatch.setattr(module, 'guess_scope', lambda *a, **k: '')
    monkeypatch.setattr(module, 'guess_manufacturer_obligation', lambda *a, **k: False)
    monkeypatch.setattr(module, 'load_previous_snapshot', lambda *a: None)
    monkeypatch.setattr(module, 'save_snapshot', lambda *a: None)


def test_mhra_result_has_revision_history_without_changing_summary(monkeypatch):
    _summary_stubs(monkeypatch, mhra)
    url = 'https://www.gov.uk/guidance/example'
    page = '<html><title>Example</title><p>Last updated: 20 February 2026</p><ol id="full-publication-update-history"><li class="gem-c-metadata__change-history-item"><time class="gem-c-metadata__change-date">20 February 2026</time><p class="gem-c-metadata__change-note">Updated A.</p></li></ol></html>'
    monkeypatch.setattr(mhra, 'fetch', lambda url: SimpleNamespace(ok=True, robots_disallowed=False, text=page))
    monkeypatch.setattr(mhra, '_extract_attachment_text', lambda *a: '')
    monkeypatch.setattr(regional_revision_evidence, '_get_exact', lambda *a: page)
    item, _ = mhra._process_source('test', url, False)
    assert item['revision_evidence']['sections'][0]['quote'] == 'Updated A.'
    assert item['summary'].startswith('unchanged summary')


def test_health_canada_result_reports_incomplete(monkeypatch):
    _summary_stubs(monkeypatch, health_canada)
    monkeypatch.setattr(health_canada, 'fetch', lambda url: SimpleNamespace(ok=True, robots_disallowed=False, text='<main>last amended on 2026-02-01</main>'))
    monkeypatch.setattr(health_canada, '_fetch_full_text', lambda url: 'Full current text' if url else '')
    monkeypatch.setattr(health_canada, '_historical_version_url', lambda date: None)
    items, _ = health_canada.run()
    assert items[0]['revision_evidence']['status'] == 'discovery_incomplete'
    assert items[0]['summary'].startswith('unchanged summary')


def test_mfds_result_evidence_is_from_exact_detail_not_summary(monkeypatch):
    _summary_stubs(monkeypatch, mfds)
    url = 'https://www.mfds.go.kr/brd/m_207/view.do?seq=1'
    row = {'board': '제개정고시등', 'title': '의료기기 일부개정', 'view_url': url, 'pub_date': '2026-02-01', 'attachments': [], 'doc_no': 'x'}
    monkeypatch.setattr(mfds, '_search_board', lambda *a: ([row], None))
    monkeypatch.setattr(mfds, '_fetch_detail_and_attachment', lambda *a: ('summary source', None, 'OK'))
    monkeypatch.setattr(regional_revision_evidence, '_get_exact', lambda *a: '<div class="bv_cont"><p>1. 개정이유</p><p>Original reason</p></div>')
    items, _ = mfds.run()
    assert items[0]['revision_evidence']['sections'][0]['quote'] == 'Original reason'
    assert items[0]['summary'] == 'unchanged summary'
