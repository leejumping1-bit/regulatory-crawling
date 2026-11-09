"""Employee view must render without exposing any mutation path."""
from pathlib import Path
import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / 'employee_app.py'
ITEMS = [dict(no=1, title='Test guidance', publisher='FDA', search_month='2026-01', summary='한글 요약', url='https://example.org', revision_evidence={'status': 'discovery_incomplete'})]


def test_employee_dashboard_read_only(monkeypatch):
    st.cache_data.clear()
    calls = []
    def request(self, method, url, **kwargs):
        calls.append((method, url))
        assert method.upper() == 'GET'
        response = requests.Response()
        response.status_code = 200
        response.encoding = 'utf-8'
        response._content = (__import__('json').dumps(ITEMS) if url.endswith('regulations.json') else '{"status":"ok","checked_at":"2026-11-09T00:00:00+00:00"}').encode()
        return response
    monkeypatch.setattr(requests.sessions.Session, 'request', request)
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.query_params['update'] = 'true'
    app.query_params['admin'] = 'true'
    app.run()
    assert not app.exception
    assert not app.button
    assert not any('github.com/leejumping1-bit/regulatory-crawling/actions' in str(x) for x in app.get('link_button'))
    assert any('한글 요약' in x.value for x in app.markdown)
    assert any('reg-table' in x.value and 'Test guidance' in x.value for x in app.markdown)
    assert app.get('download_button')
    app.selectbox[0].select('2026-01').run()
    app.selectbox[1].select('FDA').run()
    assert not app.exception and not app.button
    assert calls and all(method.upper() == 'GET' for method, _ in calls)
