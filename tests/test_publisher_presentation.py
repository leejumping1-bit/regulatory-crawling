from pathlib import Path
import copy
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('filename', ['app.py', 'employee_app.py'])
def test_configured_count_and_publisher_presentation(monkeypatch, filename):
    import io
    import zipfile
    from crawler import AUTO_AGENCIES
    monkeypatch.setattr('crawler.AUTO_AGENCIES', AUTO_AGENCIES + ['test_source'])
    from crawler import AUTO_AGENCIES
    rows = [dict(no=1, title='Audit Approach', publisher='MDSAP', search_month='2026-01', summary='본문'),
            dict(no=2, title='Other', publisher='FDA (US)', search_month='2026-01', summary='내용')]
    original = copy.deepcopy(rows)
    class Response:
        def raise_for_status(self): pass
        def json(self): return rows
    monkeypatch.setattr('requests.get', lambda *a, **kw: Response())
    downloads = []
    download = st.download_button
    def capture_download(*args, **kwargs):
        downloads.append((kwargs['data'], kwargs['file_name']))
        return download(*args, **kwargs)
    monkeypatch.setattr(st, 'download_button', capture_download)
    st.cache_data.clear()
    app = AppTest.from_file(str(ROOT / filename), default_timeout=30).run()
    assert not app.exception
    assert any(f'수집 대상 {len(AUTO_AGENCIES)}개' in m.value for m in app.markdown)
    assert 'MDSAP AU' in app.selectbox[1].options
    app.selectbox[1].select('MDSAP AU').run()
    assert not app.exception
    report = next(m.value for m in app.markdown if 'class="monthly-report"' in m.value)
    ledger = next(m.value for m in app.markdown if '<table class="reg-table">' in m.value)
    summary = next(m.value for m in app.markdown if 'class="summary-card"' in m.value)
    assert all('MDSAP AU' in s for s in (report, ledger, summary))
    assert 'Other' not in ledger
    content, filename = downloads[-1]
    with zipfile.ZipFile(io.BytesIO(content)) as xlsx:
        strings = xlsx.read('xl/sharedStrings.xml').decode()
    assert 'MDSAP AU' in strings
    assert 'MDSAP AU' in filename
    assert rows == original


def test_display_and_filter_preserve_stored_publisher():
    from app_logic import display_publisher, filter_by_publisher
    rows = [{'publisher': 'MDSAP'}, {'publisher': 'FDA (US)'}, {}]
    assert display_publisher(rows[0]) == 'MDSAP AU'
    assert display_publisher(rows[1]) == 'FDA (US)'
    assert filter_by_publisher(rows, 'MDSAP') == [rows[0]]
    assert rows[0]['publisher'] == 'MDSAP'
