from pathlib import Path
import pytest
from collectors import mdsap

URL = 'https://www.mdsap.global/sites/default/files/2026-07/MDSAP%20AU%20P0002.011%20MDSAP%20Audit%20Approach.pdf'
HTML = f'<div class="file-collection__content"><div class="file-collection__header">Audit Approach – MDSAP AU P0002.011</div><a href="{URL}">Download</a></div>'
TEXT = '''# Policy Title: MDSAP AUDIT APPROACH
# Document No: MDSAP AU P0002. 011
# Revision Date:
# 2026-08-03
# Summary of Changes from Prior Revisions
Changes from version 010 to 011
Actual change.
Changes from version 009 to 010
Old change.'''

def test_priority_document_extracts_version_date_and_history():
    item = mdsap.parse_priority(HTML, TEXT)
    assert item['doc_no'] == 'MDSAP AU P0002.011'
    assert item['search_month'] == '2026-08'
    assert item['revision_date'] == '2026-08-03'
    assert item['publish_date'] is None
    ev = item['revision_evidence']
    assert ev['status'] == 'revision_history' and ev['current_url'] == URL
    assert 'Actual change.' in ev['sections'][0]['quote'] and 'Old change.' not in ev['sections'][0]['quote']
    assert 'Jina' in ev['sections'][0]['title']
    assert 'current_pdf_sha256' not in ev

def test_rejects_oversized_url():
    assert not mdsap._safe_url('https://www.mdsap.global/' + 'a' * 5000)

def test_reader_source_url_mismatch_rejected():
    with pytest.raises(ValueError):
        mdsap.parse_priority(HTML, 'URL Source: https://evil.example/other.pdf\n' + TEXT)

def test_successful_recrawl_preserves_existing_summary():
    from collectors.store import _retain_failed_collection
    current = mdsap.parse_priority(HTML, TEXT)
    old = dict(current, summary='기존 유익한 요약')
    result = _retain_failed_collection(old, current)
    assert result['summary'] == old['summary']
    assert result['revision_evidence'] == current['revision_evidence']

def test_failed_mdsap_collection_retains_prior_summary_and_evidence():
    from collectors.store import _retain_failed_collection
    good = mdsap.parse_priority(HTML, TEXT)
    good['summary'] = '기존 유익한 요약'
    failed = dict(good, summary='실패', summary_status='source_unavailable', revision_evidence={'status': 'discovery_incomplete'})
    result = _retain_failed_collection(good, failed)
    assert result['summary'] == good['summary'] and result['summary_retained_stale'] is True
    assert result['revision_evidence']['retained_evidence_stale'] is True
    assert result['revision_evidence']['retained_evidence'] == good['revision_evidence']

@pytest.mark.parametrize('html,text', [(HTML.replace('www.mdsap.global/', 'www.mdsap.global.evil/'), TEXT), (HTML, TEXT.replace('P0002. 011', 'P0002. 010')), (HTML, TEXT.replace('2026-08-03', '2026-99-99')), (HTML, TEXT.replace('010 to 011', '009 to 010'))])
def test_rejects_unverified_document(html, text):
    with pytest.raises(ValueError):
        mdsap.parse_priority(html, text)
