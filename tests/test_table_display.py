"""Real Streamlit rendering of regulatory document numbers and table layout."""
from pathlib import Path
import io
import zipfile

import streamlit as st
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"
HASH = "MHRA-0123456789abcdef01234567"


def run_app(monkeypatch):
    st.cache_data.clear()
    items = [
        {"no": 1, "title": "Synthetic event", "publisher": "MHRA (UK)", "doc_no": HASH,
         "publish_date": "2026-01-02", "change_date": "2026-02-03", "effective_date": "2026-03-04", "search_month": "2026-01"},
        {"no": 2, "title": "Real guidance", "publisher": "MHRA (UK)", "doc_no": "MHRA-GUIDANCE-1", "search_month": "2026-02"},
        {"no": 3, "title": "Other agency", "publisher": "FDA (US)", "doc_no": HASH, "search_month": "2026-02"},
    ]
    class Response:
        def raise_for_status(self): pass
        def json(self): return items
    monkeypatch.setattr("requests.get", lambda *a, **k: Response())
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not app.exception
    return app, items


def test_synthetic_mhra_number_hidden_without_changing_selection_or_other_numbers(monkeypatch):
    app, items = run_app(monkeypatch)
    table = next(m.value for m in app.markdown if '<table class="reg-table">' in m.value)
    summary = next(m.value for m in app.markdown if 'class="summary-card"' in m.value)
    assert HASH not in table.split('</tr>')[1]
    assert HASH not in summary
    assert 'MHRA-GUIDANCE-1' in table and HASH in table  # other publisher is untouched
    assert items[0]['doc_no'] == HASH
    app.selectbox[1].select('MHRA (UK)').run()
    assert not app.exception
    assert 'Other agency' not in next(m.value for m in app.markdown if '<table class="reg-table">' in m.value)
    app.selectbox[2].select(2).run()
    assert 'MHRA-GUIDANCE-1' in next(m.value for m in app.markdown if 'class="summary-card"' in m.value)


def test_excel_export_respects_filters_and_hides_only_synthetic_mhra_number(monkeypatch):
    exports = []
    original = st.download_button

    def capture(*args, **kwargs):
        exports.append(kwargs['data'])
        return original(*args, **kwargs)

    monkeypatch.setattr(st, 'download_button', capture)
    app, _ = run_app(monkeypatch)
    app.selectbox[1].select('MHRA (UK)').run()
    assert not app.exception
    with zipfile.ZipFile(io.BytesIO(exports[-1])) as workbook:
        strings = workbook.read('xl/sharedStrings.xml').decode()
    assert 'Synthetic event' in strings and 'Real guidance' in strings
    assert 'Other agency' not in strings and HASH not in strings
    assert 'MHRA-GUIDANCE-1' in strings


def test_table_date_cells_do_not_wrap_and_obligation_header_has_two_lines(monkeypatch):
    app, _ = run_app(monkeypatch)
    css = next(m.value for m in app.markdown if '.reg-table td {' in m.value)
    table = next(m.value for m in app.markdown if '<table class="reg-table">' in m.value)
    assert '.reg-table td.date-cell' in css and 'white-space:nowrap' in css.split('.reg-table td.date-cell', 1)[1].split('}', 1)[0].replace(' ', '')
    assert table.count('class="date-cell"') == 9
    assert 'Manufacturer<br>obligation' in table
