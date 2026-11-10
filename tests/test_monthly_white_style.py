from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('name', ['app.py', 'employee_app.py'])
def test_monthly_table_white_rows_and_larger_headers(name):
    text = (ROOT / name).read_text(encoding='utf-8')
    assert '.monthly-table tbody tr { background:#fff; }' in text
    assert '.monthly-table tbody tr:nth-child(even)' not in text
    assert '.monthly-table th:not(:last-child) { font-size:13px; }' in text
    assert 'background:#eaf4fa; color:#173958; font-size:11px;' in text
