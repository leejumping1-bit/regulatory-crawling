from pathlib import Path
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / 'app.py'


def test_table_uses_original_font_sizes_without_changing_summary():
    source = APP.read_text(encoding='utf-8')
    assert 'font-size: 12.8px; background:#fff' in source
    assert 'white-space:nowrap; font-size:11.5px' in source
    assert '.reg-scope-tag { display:inline-block; font-size:11px' in source
    assert '.summary-card .summary-text { font-size:16px' in source
    assert '.reg-table td.date-cell { white-space:nowrap; }' in source


def test_rendered_ui_has_readable_korean_summary_and_no_brand_badge(monkeypatch):
    import requests
    import streamlit as st

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return [{"no": 1, "title": "의료기기 지침", "summary": "첫 줄\n둘째 줄",
                     "publisher": "기관", "publish_date": "2026-01-01"}]

    monkeypatch.setattr(requests, 'get', lambda *args, **kwargs: Response())
    st.cache_data.clear()
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    assert not at.exception
    markup = '\n'.join(m.value for m in at.markdown)
    assert '<span class="rw-brand-mark">RA/QA</span>' not in markup
    assert 'class="summary-text"' in markup
    assert '첫 줄<br>둘째 줄' in markup
    assert 'font-size:16px' in markup
    assert 'line-height:1.8' in markup
    assert 'Noto Sans KR' in markup
    assert '조회 월' in markup
