"""Read-only entrypoint regression tests, including degraded data and exports."""
import io
import json
import zipfile
from pathlib import Path

import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'employee_app.py'


def test_filtered_export_and_evidence_without_mutations(monkeypatch):
    st.cache_data.clear()
    writes = []
    import collectors.store as store
    monkeypatch.setattr(store, 'save_regulations', lambda *a, **k: writes.append((a, k)))
    ledger = ROOT / 'data/regulations.json'
    before = ledger.read_bytes()
    items = [
        dict(no=1, title='FDA guidance', publisher='FDA', search_month='2026-01', summary='한국어 요약', revision_evidence={'status': 'discovery_incomplete'}),
        dict(no=2, title='MHRA guidance', publisher='MHRA', search_month='2026-02', summary='다른 요약'),
    ]
    calls = []
    def request(self, method, url, **kwargs):
        calls.append((method.upper(), url))
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(items if url.endswith('regulations.json') else {}).encode()
        return response
    monkeypatch.setattr(requests.sessions.Session, 'request', request)
    exports = []
    original = st.download_button
    def capture(*args, **kwargs):
        exports.append(kwargs['data'])
        return original(*args, **kwargs)
    monkeypatch.setattr(st, 'download_button', capture)
    app = AppTest.from_file(APP, default_timeout=30)
    app.query_params.update({'action': 'update', 'run': 'true', 'page': 'admin', 'workflow': 'run'})
    app.run()
    assert not app.exception
    assert any('이전 버전 확인 실패' in w.value for w in app.warning)
    app.selectbox[1].select('FDA').run()
    with zipfile.ZipFile(io.BytesIO(exports[-1])) as workbook:
        strings = workbook.read('xl/sharedStrings.xml').decode()
    assert 'FDA guidance' in strings and 'MHRA guidance' not in strings
    assert not app.button and not writes and ledger.read_bytes() == before
    assert calls and all(method == 'GET' for method, _ in calls)
    assert all(url.startswith('https://raw.githubusercontent.com/leejumping1-bit/regulatory-crawling/main/data/') for _, url in calls)


def test_remote_failure_does_not_fall_back_or_offer_update(monkeypatch):
    st.cache_data.clear()
    def unavailable(*args, **kwargs):
        raise requests.ConnectionError('offline')
    monkeypatch.setattr(requests, 'get', unavailable)
    app = AppTest.from_file(APP, default_timeout=30).run()
    assert not app.exception and not app.button
    assert any('접근할 수 없습니다' in x.value for x in app.info)
    assert not app.get('download_button')
    assert not any('Actions' in x.value or '갱신' in x.value for x in app.markdown)
