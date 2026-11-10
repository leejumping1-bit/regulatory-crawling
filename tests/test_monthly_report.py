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
    assert report.count('<tr class="monthly-row">') == 2
    assert report.index('<td>7</td>') < report.index('<td>2</td>')
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
    assert report.count('<tr class="monthly-row">') == 3 and '전체' in report
    assert calls and all(url.endswith(('/regulations.json', '/mdsap_status.json')) for url in calls)


def test_report_table_excerpts_are_verbatim_for_real_records_and_escaping():
    import json
    from html.parser import HTMLParser
    from app_logic import monthly_report_html

    class Parser(HTMLParser):
        def __init__(self):
            super().__init__(); self.rows = []; self.row = None; self.cell = None; self.excerpts = []; self.row_excerpts = []; self.excerpt = None; self.headers = []
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'tr' and attrs.get('class') == 'monthly-row': self.row = []; self.row_excerpts.append([])
            if tag == 'td' and self.row is not None: self.cell = ''
            if tag == 'th': self.cell = ''
            if attrs.get('class') == 'monthly-excerpt': self.excerpt = ''
            if tag == 'br' and self.excerpt is not None: self.excerpt += '\n'
        def handle_data(self, data):
            if self.cell is not None: self.cell += data
            if self.excerpt is not None: self.excerpt += data
        def handle_endtag(self, tag):
            if tag == 'span' and self.excerpt is not None: self.excerpts.append(self.excerpt); self.row_excerpts[-1].append(self.excerpt); self.excerpt = None
            if tag == 'td' and self.row is not None: self.row.append(self.cell); self.cell = None
            if tag == 'th': self.headers.append(self.cell); self.cell = None
            if tag == 'tr' and self.row is not None: self.rows.append(self.row); self.row = None

    items = json.loads((ROOT / 'data/regulations.json').read_text())
    items += [dict(no=9999, title='<script>x</script>', publisher='A&B', publish_date='2026-01-01', manufacturer_obligation='★', summary='[핵심 내용]\n첫 번째 <핵심> 문장입니다.\n[제조업체 의무사항]\n- 제조자는 기록을 보관해야 합니다.\n[기타]\n무시.', summary_retained_stale=True)]
    html = monthly_report_html(items, '전체', '전체')
    parser = Parser(); parser.feed(html)
    assert parser.headers == ['No.', '고시일', '발행처', '제목', '요약내용', 'Manufacturer obligation']
    assert len(parser.rows) == len(items)
    for row, item in zip(parser.rows, items):
        assert row[0] == str(item['no'])
        assert row[1] == (item.get('publish_date') or '-')
        assert row[2] == (item.get('publisher') or '-')
        assert row[3].startswith(item.get('title') or '-')
        assert row[5] == (item.get('manufacturer_obligation', item.get('sop_required')) or '-')
        assert '요약 근거:' in row[4]
        if item.get('summary_retained_stale'):
            assert '이전' in row[4] and ('다를 수 있습니다' in row[4] or '최신 여부는 확인되지 않았습니다' in row[4])
        if item.get('summary_status') == 'summary_unavailable':
            assert '한글 요약을 생성하지 못했습니다' in row[4]
    assert all(excerpt in (item.get('summary') or '') for item, excerpts in zip(items, parser.row_excerpts) for excerpt in excerpts)
    assert '&lt;script&gt;' in html and '<script>' not in html and 'A&amp;B' in html
    assert '발췌 · 전체 내용은 아래 02' in html
    assert '요약 근거:' in html and '이전에 저장한 요약' in html
    assert '첫 번째 <핵심> 문장입니다.' in parser.excerpts
    assert '- 제조자는 기록을 보관해야 합니다.' in parser.excerpts


def test_structured_excerpt_preserves_continuation_of_complete_bullets():
    from app_logic import monthly_summary_excerpts
    summary = ('[핵심 내용]\n- ' + '가' * 250 + '\n계속되는 같은 항목입니다.\n'
               '- 두 번째 완결된 항목입니다.\n- 세 번째 항목입니다.\n[기타]\n제외')
    excerpts, shortened = monthly_summary_excerpts(summary)
    assert shortened
    assert '계속되는 같은 항목입니다.' in '\n'.join(excerpts)
    assert '두 번째 완결된 항목입니다.' in '\n'.join(excerpts)
    assert '세 번째 항목입니다.' not in '\n'.join(excerpts)
    assert all(part in summary for part in excerpts)
