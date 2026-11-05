from collectors import mhra


def test_events_keep_official_dates_history_and_distinct_identity():
    content = {
        'base_path': '/guidance/example', 'title': 'Medical devices guidance',
        'first_published_at': '2020-01-01T00:00:00Z',
        'public_updated_at': '2026-02-03T10:00:00Z',
        'details': {'change_history': [
            {'public_timestamp': '2026-02-03T10:00:00Z', 'note': 'Updated labelling.'},
            {'public_timestamp': '2026-01-02T10:00:00Z', 'note': 'Updated registration.'},
            {'public_timestamp': '2020-01-01T00:00:00Z', 'note': 'First published.'},
        ]},
    }
    events = mhra.events_from_content(content, '2026-01-01')
    assert len(events) == 2
    assert len({e['doc_no'] for e in events}) == 2
    assert all(e['publish_date'] == '2020-01-01' for e in events)
    assert [e['change_date'] for e in events] == ['2026-02-03', '2026-01-02']
    assert events[0]['effective_date'] is None
    assert events[0]['source_updated_date'] == '2026-02-03'
    assert events[1]['source_updated_date'] == '2026-02-03'
    assert events[0]['collected_date']
    assert events[0]['revision_evidence']['sections'][0]['quote'] == 'Updated labelling.'


def test_search_paginates_filters_deduplicates_and_uses_event_date(monkeypatch):
    calls = []
    def api(path, params=None):
        calls.append((path, params))
        if path == '/api/search.json':
            if params['start'] == 0:
                return {'total': 3, 'results': [
                    {'link': '/guidance/one', 'title': 'Medical device labelling'},
                    {'link': '/guidance/drugs', 'title': 'Medicines safety classification'},
                ]}
            return {'total': 3, 'results': [{'link': '/guidance/one', 'title': 'Medical device labelling'}]}
        assert path == '/api/content/guidance/one'
        return {'base_path': '/guidance/one', 'title': 'Medical device labelling',
                'first_published_at': '2020-01-01T00:00:00Z',
                'details': {'change_history': [{'public_timestamp': '2026-03-01T12:00:00Z', 'note': 'Updated.'}]}}
    monkeypatch.setattr(mhra, '_api_get', api, raising=False)
    items, error = mhra.backfill('2026-01-01', page_size=2)
    assert error is None
    assert len(items) == 1
    assert items[0]['publish_date'] == '2020-01-01'
    assert items[0]['change_date'] == '2026-03-01'
    assert [c[1]['start'] for c in calls if c[0] == '/api/search.json'] == [0, 2]
    assert len([c for c in calls if c[0].startswith('/api/content/')]) == 1


def test_api_failure_is_not_successful_empty_run(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError('API failed')
    monkeypatch.setattr(mhra, '_api_get', fail, raising=False)
    items, error = mhra.backfill('2026-01-01')
    assert items == []
    assert error and 'API failed' in error.error


def test_request_budget_returns_partial_and_explicit_failure(monkeypatch):
    def api(path, params=None):
        if path == '/api/search.json':
            return {'total': 2, 'results': [{'link': '/guidance/a', 'title': 'Medical device A'}, {'link': '/guidance/b', 'title': 'Medical device B'}]}
        return {'base_path': path.replace('/api/content', ''), 'title': 'Medical device', 'first_published_at': '2026-03-01T00:00:00Z', 'details': {}}
    monkeypatch.setattr(mhra, '_api_get', api)
    items, err = mhra.backfill('2026-01-01', max_documents=1)
    assert len(items) == 1 and err and not err.ok
    assert '제한' in err.error


def test_first_publication_without_history_is_not_lost():
    content = {'base_path': '/guidance/new', 'title': 'Medical device',
               'first_published_at': '2026-03-01T08:00:00Z', 'details': {}}
    items = mhra.events_from_content(content, '2026-01-01')
    assert len(items) == 1
    assert items[0]['change_date'] == '2026-03-01'
    assert items[0]['revision_evidence']['status'] == 'discovery_incomplete'
    assert items[0]['effective_date'] is None


def test_medicines_article_with_incidental_device_description_is_not_classified():
    assert not mhra._relevant({'title': 'Medicines safety roundup',
                               'description': 'Updates to medicines and medical devices'})
    assert mhra._relevant({'title': 'Medical device registration', 'description': ''})


def test_missing_history_exposes_unverified_update_not_a_confirmed_revision():
    content = {'base_path': '/guidance/example', 'title': 'Medical device',
               'first_published_at': '2020-01-01T00:00:00Z',
               'public_updated_at': '2026-02-03T10:00:00Z', 'details': {}}
    events = mhra.events_from_content(content, '2026-01-01')
    assert len(events) == 1
    assert events[0]['change_date'] == '2026-02-03'
    assert events[0]['revision_evidence']['status'] == 'discovery_incomplete'


def test_untrusted_search_path_cannot_escape_content_api(monkeypatch):
    calls = []
    def api(path, params=None):
        calls.append(path)
        return {'total': 1, 'results': [{'link': '/guidance/../../private', 'title': 'Medical device'}]}
    monkeypatch.setattr(mhra, '_api_get', api)
    items, error = mhra.backfill('2026-01-01')
    assert items == [] and error is None
    assert calls == ['/api/search.json']
