import json
import xml.etree.ElementTree as ET
import pytest

import crawler
from collectors import mdsap
from collectors import store
from test_mdsap_jina import HTML, TEXT


def test_rss_failure_does_not_hide_successful_priority(monkeypatch, tmp_path):
    monkeypatch.setattr(mdsap, '_detail', lambda: HTML)
    monkeypatch.setattr(mdsap, '_get', lambda *args, **kwargs: TEXT)
    def feed(url):
        if url == mdsap.RSS_URL:
            raise OSError('secret-token')
        return [ET.fromstring('<item><title>Update</title></item>')]
    monkeypatch.setattr(mdsap, '_feed', feed)
    path = tmp_path / 'status.json'
    monkeypatch.setattr(crawler, 'MDSAP_STATUS_PATH', path)
    saved = []
    monkeypatch.setattr(crawler, 'load_regulations', lambda: [])
    monkeypatch.setattr(crawler, 'upsert_regulations', lambda items: saved.extend(items))
    crawler.run_crawler(only=['mdsap'])
    status = json.loads(path.read_text())
    assert status['status'] == 'error'
    assert status['sources'] == {'p0002': 'ok', 'documents_rss': 'error', 'news_rss': 'ok'}
    assert saved[0]['doc_no'] == 'MDSAP AU P0002.011'
    assert 'secret-token' not in path.read_text()


def test_invalid_news_entry_is_a_failed_news_check(monkeypatch):
    monkeypatch.setattr(mdsap, '_detail', lambda: HTML)
    monkeypatch.setattr(mdsap, '_get', lambda *args, **kwargs: TEXT)
    monkeypatch.setattr(mdsap, '_feed', lambda url: [None] if url == mdsap.NEWS_RSS_URL else [])
    items, error, sources = mdsap.run_detailed()
    assert items and error
    assert sources == {'p0002': 'ok', 'documents_rss': 'ok', 'news_rss': 'error'}


@pytest.mark.parametrize('failed', [None, 'p0002', 'documents_rss', 'news_rss'])
def test_independent_outcomes_and_existing_record_retention(monkeypatch, tmp_path, failed):
    previous = mdsap.parse_priority(HTML, TEXT)
    previous['summary'] = 'Previously verified summary'
    data_path = tmp_path / 'regulations.json'
    data_path.write_text(json.dumps([previous]))
    monkeypatch.setattr(store, 'DATA_PATH', str(data_path))
    monkeypatch.setattr(crawler, 'MDSAP_STATUS_PATH', tmp_path / 'status.json')
    def detail():
        if failed == 'p0002':
            raise OSError('unavailable')
        return HTML
    def feed(url):
        if failed == ('documents_rss' if url == mdsap.RSS_URL else 'news_rss'):
            raise OSError('unavailable')
        return [ET.fromstring('<item><title>Update</title></item>')]
    monkeypatch.setattr(mdsap, '_detail', detail)
    monkeypatch.setattr(mdsap, '_get', lambda *args, **kwargs: TEXT)
    monkeypatch.setattr(mdsap, '_feed', feed)
    crawler.run_crawler(only=['mdsap'])
    status = json.loads((tmp_path / 'status.json').read_text())
    assert status['status'] == ('error' if failed else 'ok')
    assert status['sources'] == {key: ('error' if key == failed else 'ok')
                                 for key in ('p0002', 'documents_rss', 'news_rss')}
    saved = store.load_regulations()
    assert len(saved) == 1
    assert saved[0]['doc_no'] == previous['doc_no']
    if failed == 'p0002':
        assert saved[0]['summary'] == previous['summary']
        assert saved[0]['summary_retained_stale'] is True
        assert saved[0]['revision_evidence']['retained_evidence'] == previous['revision_evidence']


def test_conflicting_news_is_not_reported_as_success(monkeypatch):
    monkeypatch.setattr(mdsap, '_detail', lambda: HTML)
    monkeypatch.setattr(mdsap, '_get', lambda *args, **kwargs: TEXT)
    monkeypatch.setattr(mdsap, '_feed', lambda url: [ET.fromstring('<item><title>Revision 12 MDSAP Audit Approach</title></item>')] if url == mdsap.NEWS_RSS_URL else [])
    items, error, sources = mdsap.run_detailed()
    assert len(items) == 1 and error
    assert sources == {'p0002': 'ok', 'documents_rss': 'ok', 'news_rss': 'error'}


def test_legacy_run_returns_two_values_on_success(monkeypatch):
    monkeypatch.setattr(mdsap, '_detail', lambda: HTML)
    monkeypatch.setattr(mdsap, '_get', lambda *args, **kwargs: TEXT)
    monkeypatch.setattr(mdsap, '_feed', lambda url: [])
    items, error = mdsap.run()
    assert len(items) == 1 and error is None
