from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest
from scripts import mdsap_retry as retry


def test_retry_schedule_uses_first_attempt_for_both_deadlines():
    state = {'status': 'error', 'checked_at': '2026-11-11T00:00:00+00:00'}
    now = lambda h, m: datetime(2026, 11, 11, h, m, tzinfo=timezone.utc)
    marker, due = retry.plan_retry(state, None, now(0, 29))
    assert not due
    assert marker['next_retry_at'] == '2026-11-11T00:30:00+00:00'
    marker, due = retry.plan_retry(state, marker, now(0, 30))
    assert due
    marker['attempt'] = 1
    state['checked_at'] = '2026-11-11T01:00:00+00:00'
    marker['last_checked_at'] = state['checked_at']
    marker, due = retry.plan_retry(state, marker, now(1, 59))
    assert not due
    assert marker['next_retry_at'] == '2026-11-11T02:00:00+00:00'
    assert retry.plan_retry(state, marker, now(2, 0))[1]
    marker['attempt'] = 2
    marker, due = retry.plan_retry(state, marker, now(2, 1))
    assert marker['next_retry_at'] is None and not due


def test_new_daily_failure_resets_and_success_clears_marker():
    now = datetime(2026, 11, 11, 3, tzinfo=timezone.utc)
    old = {'first_attempt_at': '2026-11-11T00:00:00+00:00', 'last_checked_at': '2026-11-11T00:00:00+00:00', 'attempt': 2}
    state = {'status': 'error', 'checked_at': '2026-11-11T02:59:00+00:00'}
    marker, due = retry.plan_retry(state, old, now)
    assert marker['attempt'] == 0 and not due
    assert retry.plan_retry({'status': 'ok'}, marker, now) == (None, False)
    assert retry.plan_retry({'status': 'error', 'checked_at': 'bad'}, None, now) == (None, False)


def test_persist_rejects_changed_status(tmp_path, monkeypatch):
    status = tmp_path / 'status.json'
    marker = tmp_path / 'marker.json'
    data = tmp_path / 'data.json'
    monkeypatch.setattr(retry, 'STATUS', status)
    monkeypatch.setattr(retry, 'MARKER', marker)
    monkeypatch.setattr(retry, 'DATA', data)
    status.write_text(json.dumps({'status': 'ok', 'checked_at': 'new'}))
    calls = []
    monkeypatch.setattr(retry, 'git', lambda *args: calls.append(args) or '')
    retry.persist({'status': 'error', 'checked_at': 'old'}, None, None, {'status': 'ok'}, [], [])
    assert all(args[0] not in ('commit', 'push') for args in calls)
    assert json.loads(status.read_text())['checked_at'] == 'new'


def test_persist_rejects_concurrent_mdsap_record_change(tmp_path, monkeypatch):
    status, marker, data = (tmp_path / n for n in ('status', 'marker', 'data'))
    monkeypatch.setattr(retry, 'STATUS', status)
    monkeypatch.setattr(retry, 'MARKER', marker)
    monkeypatch.setattr(retry, 'DATA', data)
    state = {'status': 'error', 'checked_at': 'old'}
    status.write_text(json.dumps(state))
    row = {'publisher': 'MDSAP', 'doc_no': 'A', 'title': 'old'}
    data.write_text(json.dumps([dict(row, title='concurrent')]))
    calls = []
    monkeypatch.setattr(retry, 'git', lambda *args: calls.append(args) or '')
    retry.persist(state, None, None, state, [row], [dict(row, title='new')])
    assert all(args[0] != 'commit' for args in calls)
    assert json.loads(data.read_text())[0]['title'] == 'concurrent'


def test_semantic_merge_retries_rejected_push_without_touching_other_agencies(tmp_path, monkeypatch):
    from collectors import store
    status, marker, data = (tmp_path / n for n in ('status', 'marker', 'data'))
    monkeypatch.setattr(retry, 'STATUS', status)
    monkeypatch.setattr(retry, 'MARKER', marker)
    monkeypatch.setattr(retry, 'DATA', data)
    monkeypatch.setattr(store, 'DATA_PATH', str(data))
    state = {'status': 'error', 'checked_at': 'old'}
    old = {'publisher': 'MDSAP', 'doc_no': 'A', 'title': 'old'}
    new = dict(old, title='new')
    other = {'publisher': 'FDA', 'doc_no': 'B', 'title': 'latest'}
    operations = []
    def git(*args):
        operations.append(args)
        if args[0] == 'checkout':
            status.write_text(json.dumps(state))
            marker.unlink(missing_ok=True)
            data.write_text(json.dumps([old, other]))
        return 'data/regulations.json' if args == ('diff', '--cached', '--name-only') else ''
    monkeypatch.setattr(retry, 'git', git)
    results = iter([1, 0])
    monkeypatch.setattr(retry.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=next(results)))
    retry.persist(state, None, {'attempt': 1}, state, [old], [new])
    rows = json.loads(data.read_text())
    assert {(r['publisher'], r['title']) for r in rows} == {('MDSAP', 'new'), ('FDA', 'latest')}
    assert sum(op[0] == 'fetch' for op in operations) == 2
    assert sum(op[0] == 'commit' for op in operations) == 2
    assert not any('rebase' in op or '--force' in op for op in operations)
