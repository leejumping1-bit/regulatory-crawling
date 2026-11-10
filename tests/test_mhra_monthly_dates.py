from html.parser import HTMLParser

import pytest

from app_logic import filter_by_month, filter_by_publisher, monthly_report_html


class Rows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == 'tr' and dict(attrs).get('class') == 'monthly-row':
            self.row = []
        elif tag == 'td' and self.row is not None:
            self.cell = ''

    def handle_data(self, data):
        if self.cell is not None:
            self.cell += data

    def handle_endtag(self, tag):
        if tag == 'td' and self.cell is not None:
            self.row.append(self.cell)
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def dates(items, month='전체', publisher='전체'):
    selected = filter_by_publisher(filter_by_month(items, month), publisher)
    html = monthly_report_html(selected, month, publisher)
    parser = Rows()
    parser.feed(html)
    return {row[0]: row[1] for row in parser.rows}, html


def test_mhra_cross_year_update_follows_row_month_in_overall_view():
    items = [dict(no=1, publisher='MHRA (UK)', search_month='2026-10',
                  publish_date='2020-02-11', change_date='2026-10-16')]
    result, html = dates(items)
    assert result['1'] == '2026-10-16 (업데이트일)'
    assert '<th>고시일 / MHRA 업데이트일</th>' in html


@pytest.mark.parametrize('fields, expected', [
    (dict(publish_date='2026-10-01', change_date='2026-10-16', revision_date='2026-10-20'), '2026-10-16 (업데이트일)'),
    (dict(publish_date='2026-10-01', change_date='2026-09-16', revision_date='2026-10-20'), '2026-10-20 (업데이트일)'),
    (dict(publish_date='2026-10', change_date='2026-09-16'), '2026-10'),
    (dict(publish_date='2020-02-11', change_date='2026-09-16'), '2020-02-11 (해당 월 일치 미확인)'),
    (dict(change_date='2026-09'), '- (해당 월 일치 미확인)'),
    (dict(publish_date='2020-02-11', change_date='2026-10-99'), '2020-02-11 (해당 월 일치 미확인)'),
    (dict(publish_date='2020-02-11', change_date='2026-10'), '2026-10 (업데이트일)'),
])
def test_mhra_date_priority_and_precision(fields, expected):
    item = dict(no=1, publisher='MHRA (UK)', search_month='2026-10', **fields)
    assert dates([item])[0]['1'] == expected


def test_unknown_month_other_issuers_filters_and_escaping():
    items = [
        dict(no=1, publisher='MHRA (UK)', search_month='2026-10', publish_date='2020-01-01', change_date='2026-10-09'),
        dict(no=2, publisher='MHRA (UK)', search_month='2026-11', publish_date='2020-01-01', revision_date='2026-11-02'),
        dict(no=3, publisher='MHRA (UK)', search_month='UNKNOWN', publish_date='<img src=x>', change_date='2026-10-09'),
        dict(no=4, publisher='FDA (US)', search_month='2026-10', publish_date='2020-01-01', change_date='2026-10-09'),
    ]
    result, html = dates(items)
    assert result == {'1': '2026-10-09 (업데이트일)', '2': '2026-11-02 (업데이트일)',
                      '3': '<img src=x> (해당 월 일치 미확인)', '4': '2020-01-01'}
    assert '&lt;img src=x&gt;' in html and '<img src=x>' not in html
    assert dates(items, '2026-10', 'MHRA (UK)')[0] == {'1': '2026-10-09 (업데이트일)'}
    assert dates(items, 'UNKNOWN', 'MHRA (UK)')[0] == {'3': '<img src=x> (해당 월 일치 미확인)'}
