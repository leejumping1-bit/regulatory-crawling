from pathlib import Path
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
ITEMS = [
    dict(no=7, title='A <guide>', publisher='FDA', search_month='2026-01', publish_date='2026-01-01', revision_date='2026-01-02', effective_date='2026-03-01', manufacturer_obligation='★', summary='첫 줄\n둘째 <원문>', document_status='draft', summary_source={'type':'official_abstract'}, summary_retained_stale=True, summary_retained_stale_reason='generation_failed_or_deferred'),
    dict(no=2, title='B', publisher='FDA', search_month='2026-01', summary='', summary_status='summary_unavailable'),
    dict(no=9, title='C', publisher='MFDS', search_month='2026-02', summary='다른 월'),
]

@pytest.mark.parametrize('filename', ['app.py', 'employee_app.py'])
def test_report_matches_filtered_ledger_and_saved_summary(monkeypatch, filename):
    st.cache_data.clear()
    class Response:
        def raise_for_status(self): pass
        def json(self): return ITEMS
    calls = []
    def get(url, **kwargs):
        calls.append(url)
        assert url.endswith(('/regulations.json', '/mdsap_status.json'))
        return Response()
    monkeypatch.setattr('requests.get', get)
    app = AppTest.from_file(str(ROOT / filename), default_timeout=30).run()
    assert not app.exception
    app.selectbox[0].select('2026-01').run()
    app.selectbox[1].select('FDA').run()
    assert not app.exception
    report = next(m.value for m in app.markdown if 'class="monthly-report"' in m.value)
    assert report.count('class="monthly-item"') == 2
    assert report.index('No. 7') < report.index('No. 2')
    for value in ['2026-01-01', 'FDA', 'A &lt;guide&gt;', '★', '첫 줄<br>둘째 &lt;원문&gt;', '요약 없음', '초안', '공식 초록', '이전 요약', '한글 요약을 생성하지 못했습니다']:
        assert value in report
    assert '2026-01-02' not in report and '2026-03-01' not in report
    assert '기관별로 고시·변경·개정일 기준이 다를 수 있음' in report
    assert '빈칸은 의무가 없다는 뜻이 아님' in report
    assert '다른 월' not in report
    assert 'search_month' in report and '2026-01' in report
    ledger = next(m.value for m in app.markdown if '<table class="reg-table">' in m.value)
    assert ledger.index('<td>7</td>') < ledger.index('<td>2</td>')
    summary = next(m.value for m in app.markdown if 'class="summary-card"' in m.value)
    assert '첫 줄<br>둘째 &lt;원문&gt;' in summary
    app.selectbox[0].select('전체').run()
    app.selectbox[1].select('전체').run()
    report = next(m.value for m in app.markdown if 'class="monthly-report"' in m.value)
    assert report.count('class="monthly-item"') == 3 and '전체' in report
    assert calls and all(url.endswith(('/regulations.json', '/mdsap_status.json')) for url in calls)
