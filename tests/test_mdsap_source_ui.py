from datetime import datetime, timezone

from app_logic import mdsap_source_messages

NOW = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
STAMP = '2026-11-10T11:00:00+00:00'
LIBRARY = 'https://www.mdsap.global/documents/library/audit-approach'


def test_failed_legacy_status_keeps_truth_and_stored_version():
    rows = [{'publisher': 'MDSAP', 'doc_no': 'MDSAP AU P0002.011'}]
    messages = mdsap_source_messages({'status': 'error', 'checked_at': STAMP}, rows, NOW)
    text = '\n'.join(messages)
    assert 'MDSAP AU P0002.011' in text and STAMP in text
    assert '실패' in text and '수동 확인 권장' in text and LIBRARY in text
    assert '완료' not in text


def test_structured_sources_are_reported_independently():
    state = {'status': 'error', 'checked_at': STAMP, 'sources': {
        'p0002': 'error', 'documents_rss': 'ok', 'news_rss': 'error'}}
    text = '\n'.join(mdsap_source_messages(state, [], NOW))
    assert '저장된 버전 없음' in text
    assert 'MDSAP AU P0002 수집 실패' in text
    assert 'MDSAP 문서 RSS 수집 완료' in text
    assert 'MDSAP 뉴스 RSS 수집 실패' in text


def test_structured_overall_failure_is_not_hidden_when_sources_succeed():
    state = {'status': 'error', 'checked_at': STAMP, 'sources': {
        'p0002': 'ok', 'documents_rss': 'ok', 'news_rss': 'ok'}}
    text = '\n'.join(mdsap_source_messages(state, [], NOW))
    assert 'MDSAP 전체 수집 상태: 실패' in text
    assert 'MDSAP AU P0002 수집 완료' in text


def test_stale_error_displays_both_failure_and_staleness():
    text = '\n'.join(mdsap_source_messages({'status': 'error', 'checked_at': '2026-11-01T00:00:00+00:00'}, [], NOW))
    assert all(x in text for x in ['수집 실패', '오래됨', '수동 확인 권장'])


def test_both_dashboards_render_source_information(monkeypatch):
    from pathlib import Path
    import requests
    import streamlit as st
    from streamlit.testing.v1 import AppTest

    class Response:
        def __init__(self, value): self.value = value
        def raise_for_status(self): pass
        def json(self): return self.value

    stamp = datetime.now(timezone.utc).isoformat()
    state = {'status': 'error', 'checked_at': stamp, 'sources': {
        'p0002': 'error', 'documents_rss': 'ok', 'news_rss': 'error'}}
    import json
    rows = [next(x for x in json.loads((Path(__file__).resolve().parents[1] / 'data/regulations.json').read_text()) if x.get('doc_no') == 'MDSAP AU P0002.011')]
    monkeypatch.setattr(requests, 'get', lambda url, **kw: Response(state if url.endswith('mdsap_status.json') else rows))
    for filename in ('app.py', 'employee_app.py'):
        st.cache_data.clear()
        app = AppTest.from_file(Path(__file__).resolve().parents[1] / filename).run(timeout=90)
        assert not app.exception
        source = next(x for x in app.expander if x.label == '데이터 출처 및 수집 안내')
        text = '\n'.join(x.value for x in list(source.caption) + list(source.markdown))
        assert all(x in text for x in ['MDSAP AU P0002.011', stamp, '수집 실패', '수동 확인 권장', LIBRARY, 'MDSAP 문서 RSS 수집 완료', 'MDSAP 뉴스 RSS 수집 실패'])
        assert not any('MDSAP' in x.value for x in source.warning)
