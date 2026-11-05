import json
from types import SimpleNamespace

import pytest

from collectors import fda


def version(day, substantive=True, **extra):
    return {"part": "820", "date": day, "amendment_date": day,
            "issue_date": day, "substantive": substantive, **extra}


def xml(text):
    return f'<DIV5 N="820" TYPE="PART"><HEAD>Part 820</HEAD><P>{text}</P></DIV5>'


def setup_collector(monkeypatch, versions, bodies, snapshots=None):
    monkeypatch.setattr(fda, 'discover_federal_register', lambda *args: [])
    snapshots = dict(snapshots or {})
    calls = []

    def fetch(url):
        calls.append(url)
        if url == fda.VERSIONS_API:
            return SimpleNamespace(ok=True, text=json.dumps({"content_versions": versions}))
        day = url.split('/full/')[1].split('/')[0]
        value = bodies.get(day)
        return SimpleNamespace(ok=value is not None, text=value or '', error='unavailable')

    monkeypatch.setattr(fda, 'fetch', fetch)
    monkeypatch.setattr(fda, 'load_previous_snapshot', lambda agency, key: snapshots.get(key))
    monkeypatch.setattr(fda, 'save_snapshot', lambda agency, key, text: snapshots.__setitem__(key, text))
    monkeypatch.setattr(fda, 'summarize', lambda title, text: 'summary')
    monkeypatch.setattr(fda, 'guess_manufacturer_obligation', lambda title, text: False)
    return calls, snapshots


def test_versions_api_requests_part_820_directly():
    assert '?part=820' in fda.VERSIONS_API


def test_only_explicit_substantive_amendment_dates_are_selected():
    data = {'content_versions': [
        version('2026-02-04', issue_date_unused='x'),
        {**version('2026-02-04', False), 'issue_date': '2026-10-30'},
        {'part': '820', 'amendment_date': '2026-11-01'},
        {'part': '820', 'issue_date': '2026-12-01', 'substantive': True},
        {'part': '820', 'amendment_date': '2026-12-02', 'substantive': 1},
        {'part': '21', 'amendment_date': '2027-01-01', 'substantive': True},
    ]}
    assert fda._extract_issue_dates(data) == ['2026-02-04']
    assert fda._extract_latest_issue_date(data) == '2026-02-04'


def test_compares_official_immediately_prior_text_not_local_snapshot(monkeypatch):
    calls, snapshots = setup_collector(monkeypatch, [version('2026-02-04'),
        {**version('2026-02-04', False), 'issue_date': '2026-10-30'}],
        {'2026-02-04': xml('New rule.'), '2026-02-03': xml('Old rule.')},
        {fda.DOC_NO: 'Unrelated stale snapshot'})
    items, _ = fda.run()
    assert len(items) == 1
    assert items[0]['publish_date'] == ''
    assert items[0]['effective_date'] != '2026-10-30'
    assert 'Old rule.' in items[0]['gap_analysis']['past_text']
    assert any('/full/2026-02-03/' in url for url in calls)
    assert snapshots[fda.LAST_SEEN_KEY] == '2026-02-04'


@pytest.mark.parametrize('prior', [None, '<html>unavailable</html>', '<DIV5'])
def test_unavailable_or_invalid_official_prior_fails_closed(monkeypatch, prior):
    _, snapshots = setup_collector(monkeypatch, [version('2026-02-04')],
        {'2026-02-04': xml('New rule.'), '2026-02-03': prior},
        {fda.DOC_NO: 'stale text'})
    items, failure = fda.run()
    assert items == [] and failure and '공식 개정 전/후 원문' in failure.error
    assert fda.LAST_SEEN_KEY not in snapshots


def test_equivalent_normalized_text_produces_no_entry(monkeypatch):
    _, snapshots = setup_collector(monkeypatch, [version('2026-02-04')],
        {'2026-02-04': xml('Same   rule.'), '2026-02-03': xml('Same rule.')})
    assert fda.run()[0] == []


def test_future_legacy_last_seen_does_not_reemit_older_amendment(monkeypatch):
    calls, snapshots = setup_collector(monkeypatch, [version('2026-02-04')],
        {'2026-02-04': xml('New rule.'), '2026-02-03': xml('Old rule.')},
        {fda.LAST_SEEN_KEY: '2026-10-30'})
    assert fda.run()[0] == []
    assert calls == [fda.VERSIONS_API]
    assert snapshots[fda.LAST_SEEN_KEY] == '2026-10-30'


def test_missing_or_false_substantive_never_creates_entry(monkeypatch):
    calls, _ = setup_collector(monkeypatch, [
        {**version('2026-02-04', False), 'issue_date': '2026-10-30'},
        {'part': '820', 'amendment_date': '2026-10-31'}], {})
    items, failure = fda.run()
    assert items == [] and failure and 'FDA 버전 확인 실패' in failure.error
    assert calls == [fda.VERSIONS_API]
