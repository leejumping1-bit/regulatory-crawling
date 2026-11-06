from collectors import mdsap
from test_mdsap_jina import HTML, TEXT, URL


def test_run_falls_back_and_returns_partial_failure(monkeypatch):
    calls = []
    def get(url, *, reader=False, html=False):
        calls.append((url, reader, html))
        if url == mdsap.LIBRARY_URL:
            if not reader:
                raise OSError('direct unavailable')
            return HTML
        if url == URL:
            return TEXT
        raise OSError('feed unavailable')
    monkeypatch.setattr(mdsap, '_get', get)
    monkeypatch.setattr(mdsap, 'load_regulations', lambda: [])
    items, error = mdsap.run()
    assert len(items) == 1 and items[0]['doc_no'] == 'MDSAP AU P0002.011'
    assert error is not None and not error.ok and 'RSS' in error.error
    assert (mdsap.LIBRARY_URL, True, True) in calls
    assert (URL, True, False) in calls


def test_feeds_are_secondary_signals_not_unverified_ledger_items(monkeypatch):
    monkeypatch.setattr(mdsap, '_detail', lambda: HTML)
    monkeypatch.setattr(mdsap, '_get', lambda url, **kw: TEXT)
    seen = []
    def feed(url):
        seen.append(url)
        return []
    monkeypatch.setattr(mdsap, '_feed', feed)
    items, error = mdsap.run()
    assert [x['doc_no'] for x in items] == ['MDSAP AU P0002.011']
    assert seen == [mdsap.RSS_URL, mdsap.NEWS_RSS_URL]
    assert error is None


def test_newer_revision_in_news_feed_is_not_silent(monkeypatch):
    import xml.etree.ElementTree as ET
    monkeypatch.setattr(mdsap, '_detail', lambda: HTML)
    monkeypatch.setattr(mdsap, '_get', lambda url, **kw: TEXT)
    monkeypatch.setattr(mdsap, '_feed', lambda url: [ET.fromstring('<item><title>Announcing Revision 12 of MDSAP Audit Approach</title></item>')] if url == mdsap.NEWS_RSS_URL else [])
    items, error = mdsap.run()
    assert len(items) == 1 and error and not error.ok
    assert 'RSS' in error.error and '12' in error.error


def test_priority_failure_marks_prior_data_stale(monkeypatch):
    item = mdsap.parse_priority(HTML, TEXT)
    monkeypatch.setattr(mdsap, '_detail', lambda: (_ for _ in ()).throw(OSError('down')))
    monkeypatch.setattr(mdsap, '_feed', lambda url: [])
    monkeypatch.setattr(mdsap, 'load_regulations', lambda: [item])
    items, error = mdsap.run()
    assert error and not error.ok
    assert items[0]['revision_evidence']['status'] == 'discovery_incomplete'
    assert items[0]['summary_status'] == 'source_unavailable'
