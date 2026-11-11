from datetime import datetime, timezone

import pytest

from app_logic import mdsap_source_messages

NOW = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
STAMP = '2026-11-10T11:00:00+00:00'
LIBRARY = 'https://www.mdsap.global/documents/library/audit-approach'
NOTICE = 'MDSAP AU P0002 최신 여부 미확인 · 수동 확인 권장'
ROWS = [{'publisher': 'MDSAP', 'doc_no': 'MDSAP AU P0002.011'}]


@pytest.mark.parametrize('state,unverified', [
    (None, True), ({}, True), ('invalid', True),
    ({'status': 'error', 'checked_at': STAMP}, True),
    ({'status': 'unknown', 'checked_at': STAMP}, True),
    ({'status': 'ok', 'checked_at': STAMP}, False),
    ({'status': 'ok', 'checked_at': '2026-11-01T00:00:00+00:00'}, True),
    ({'status': 'ok', 'checked_at': 'invalid'}, True),
    ({'status': 'error', 'checked_at': STAMP, 'sources': {'p0002': 'error', 'documents_rss': 'error', 'news_rss': 'error'}}, True),
    ({'status': 'error', 'checked_at': STAMP, 'sources': {'p0002': 'ok', 'documents_rss': 'error', 'news_rss': 'error'}}, False),
    ({'status': 'ok', 'checked_at': STAMP, 'sources': {'p0002': 'unknown'}}, True),
    ({'status': 'ok', 'checked_at': STAMP, 'sources': {}}, True),
    ({'status': 'ok', 'checked_at': STAMP, 'sources': []}, True),
    ({'status': 'ok', 'checked_at': STAMP, 'sources': None}, True),
    ({'status': 'ok', 'checked_at': STAMP, 'sources': {'p0002': 'ok'}}, False),
    ({'status': 'ok', 'checked_at': '2026-11-01T00:00:00+00:00', 'sources': {'p0002': 'ok'}}, True),
])
def test_source_messages_are_neutral_and_only_describe_p0002(state, unverified):
    messages = mdsap_source_messages(state, ROWS, NOW)
    text = '\n'.join(messages)
    assert 'MDSAP AU P0002.011' in text and LIBRARY in text
    assert (NOTICE in messages) is unverified
    assert len(messages) == (3 if unverified else 2)
    assert not any(word in text for word in ['실패', 'RSS', '완료', '변경 없음'])


def test_no_stored_version():
    assert '저장된 버전 없음' in mdsap_source_messages(None, [], NOW)[0]


@pytest.mark.parametrize('filename', ['app.py', 'employee_app.py'])
@pytest.mark.parametrize('p0002', ['error', 'ok', 'unknown'])
def test_both_dashboards_hide_failure_and_rss_statuses(monkeypatch, filename, p0002):
    from pathlib import Path
    import json
    import requests
    import streamlit as st
    from streamlit.testing.v1 import AppTest

    class Response:
        def __init__(self, value): self.value = value
        def raise_for_status(self): pass
        def json(self): return self.value

    state = {'status': 'error', 'checked_at': datetime.now(timezone.utc).isoformat(), 'sources': {
        'p0002': p0002, 'documents_rss': 'error', 'news_rss': 'error'}}
    root = Path(__file__).resolve().parents[1]
    rows = [next(x for x in json.loads((root / 'data/regulations.json').read_text()) if x.get('doc_no') == 'MDSAP AU P0002.011')]
    monkeypatch.setattr(requests, 'get', lambda url, **kw: Response(state if url.endswith('mdsap_status.json') else rows))
    st.cache_data.clear()
    app = AppTest.from_file(root / filename).run(timeout=90)
    assert not app.exception
    source = next(x for x in app.expander if x.label == '데이터 출처 및 수집 안내')
    text = '\n'.join(x.value for x in list(source.caption) + list(source.markdown) + list(source.warning))
    assert 'MDSAP AU P0002.011' in text and LIBRARY in text
    assert (NOTICE in text) is (p0002 != 'ok')
    assert not any(word in text for word in ['실패', 'RSS', '수집 완료', '변경 없음'])
