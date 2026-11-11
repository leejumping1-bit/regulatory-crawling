from datetime import datetime, timezone
import json

from scripts import mdsap_retry as retry


def test_structured_priority_failure_starts_and_rss_only_does_not():
    now = datetime(2026, 11, 11, 0, 30, tzinfo=timezone.utc)
    state = {'status': 'error', 'checked_at': '2026-11-11T00:00:00+00:00',
             'sources': {'p0002': 'error', 'documents_rss': 'ok', 'news_rss': 'ok'}}
    marker, due = retry.plan_retry(state, None, now)
    assert due and marker['attempt'] == 0
    state['sources']['p0002'] = 'ok'
    state['sources']['documents_rss'] = 'error'
    assert retry.plan_retry(state, marker, now) == (None, False)


def test_retry_does_not_clobber_newer_different_mdsap_revision(tmp_path, monkeypatch):
    status, marker, data = (tmp_path / n for n in ('status', 'marker', 'data'))
    monkeypatch.setattr(retry, 'STATUS', status)
    monkeypatch.setattr(retry, 'MARKER', marker)
    monkeypatch.setattr(retry, 'DATA', data)
    state = {'status': 'error', 'checked_at': 'old'}
    status.write_text(json.dumps(state))
    old = {'publisher': 'MDSAP', 'doc_no': 'P.001', 'title': 'old'}
    newer = {'publisher': 'MDSAP', 'doc_no': 'P.002', 'title': 'verified'}
    data.write_text(json.dumps([old, newer]))
    calls = []
    from collectors import store
    monkeypatch.setattr(store, 'DATA_PATH', str(data))
    monkeypatch.setattr(retry, 'git', lambda *args: calls.append(args) or ('data/regulations.json' if args == ('diff', '--cached', '--name-only') else ''))
    monkeypatch.setattr(retry.subprocess, 'run', lambda *a, **k: type('Result', (), {'returncode': 0})())
    retry.persist(state, None, None, state, [old], [dict(old, title='stale')])
    assert not any(args[0] == 'commit' for args in calls)


def test_due_worker_clears_cycle_when_priority_recovers_but_rss_fails(tmp_path, monkeypatch):
    import crawler
    status, marker, data = (tmp_path / n for n in ('status', 'marker', 'data'))
    monkeypatch.setattr(retry, 'STATUS', status)
    monkeypatch.setattr(retry, 'MARKER', marker)
    monkeypatch.setattr(retry, 'DATA', data)
    initial = {'status': 'error', 'checked_at': '2026-01-01T00:00:00+00:00',
               'sources': {'p0002': 'error'}}
    recovered = {'status': 'error', 'checked_at': '2026-01-01T00:31:00+00:00',
                 'sources': {'p0002': 'ok', 'documents_rss': 'error'}}
    status.write_text(json.dumps(initial))
    data.write_text('[]')
    monkeypatch.setattr(retry, 'git', lambda *args: '')
    monkeypatch.setattr(retry.subprocess, 'run', lambda *a, **k: type('Result', (), {'returncode': 0})())
    def collect(**kwargs):
        assert kwargs == {'only': ['mdsap']}
        status.write_text(json.dumps(recovered))
    monkeypatch.setattr(crawler, 'run_crawler', collect)
    calls = []
    monkeypatch.setattr(retry, 'persist', lambda *args: calls.append(args))
    retry.main()
    assert len(calls) == 1
    assert calls[0][0:4] == (initial, None, None, recovered)


def test_workflows_share_concurrency_and_commit_status_with_data():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    daily = (root / '.github/workflows/scheduled_crawl.yml').read_text()
    worker = (root / '.github/workflows/mdsap_retry.yml').read_text()
    for workflow in (daily, worker):
        import re
        block = re.search(r'(?m)^concurrency:\n((?:[ \t]+[^\n]*\n)+)', workflow)
        assert block is not None
        assert re.search(r'(?m)^  group: regulatory-data-update\s*$', block[1])
        assert re.search(r'(?m)^  cancel-in-progress: false\s*$', block[1])
        assert re.search(r'(?m)^  queue: max\s*$', block[1])
    assert 'data/mdsap_status.json' in daily and 'data/regulations.json' in daily
    assert 'UTC' in worker


def test_retry_data_status_and_attempt_are_in_one_commit(tmp_path, monkeypatch):
    import subprocess
    from collectors import store
    root = tmp_path / 'checkout'
    root.mkdir()
    def run(*args):
        return subprocess.run(args, cwd=root, check=True, text=True, capture_output=True).stdout.strip()
    run('git', 'init', '-b', 'main')
    run('git', 'config', 'user.email', 'test@example.invalid')
    run('git', 'config', 'user.name', 'Test')
    (root / 'data').mkdir()
    status = root / 'data/mdsap_status.json'
    data = root / 'data/regulations.json'
    marker = root / 'data/mdsap_retry.json'
    old_status = {'status': 'error', 'checked_at': 'old'}
    old_row = {'publisher': 'MDSAP', 'doc_no': 'A', 'title': 'old'}
    status.write_text(json.dumps(old_status))
    data.write_text(json.dumps([old_row]))
    run('git', 'add', 'data')
    run('git', 'commit', '-m', 'baseline')
    run('git', 'update-ref', 'FETCH_HEAD', 'HEAD')
    monkeypatch.setattr(retry, 'ROOT', root)
    monkeypatch.setattr(retry, 'STATUS', status)
    monkeypatch.setattr(retry, 'MARKER', marker)
    monkeypatch.setattr(retry, 'DATA', data)
    monkeypatch.setattr(store, 'DATA_PATH', str(data))
    real_git = retry.git
    monkeypatch.setattr(retry, 'git', lambda *args: '' if args[0] == 'fetch' else real_git(*args))
    real_run = subprocess.run
    def no_push(args, **kwargs):
        if args[:2] == ['git', 'push']:
            return type('Result', (), {'returncode': 0})()
        return real_run(args, **kwargs)
    monkeypatch.setattr(retry.subprocess, 'run', no_push)
    retry.persist(old_status, None, {'attempt': 1}, {'status': 'error', 'checked_at': 'new'},
                  [old_row], [dict(old_row, title='new')])
    files = set(run('git', 'show', '--format=', '--name-only', 'HEAD').splitlines())
    assert files == {'data/mdsap_retry.json', 'data/mdsap_status.json', 'data/regulations.json'}
    assert json.loads(run('git', 'show', 'HEAD:data/mdsap_retry.json'))['attempt'] == 1
    assert json.loads(run('git', 'show', 'HEAD:data/mdsap_status.json'))['checked_at'] == 'new'
    assert json.loads(run('git', 'show', 'HEAD:data/regulations.json'))[0]['title'] == 'new'


def test_retry_rejects_index_worktree_cancellation_without_losing_changes(tmp_path, monkeypatch):
    import subprocess
    import pytest
    root = tmp_path
    def run(*args):
        return subprocess.run(args, cwd=root, check=True, text=True, capture_output=True).stdout
    run('git', 'init', '-b', 'main')
    run('git', 'config', 'user.email', 'test@example.invalid')
    run('git', 'config', 'user.name', 'Test')
    (root / 'data').mkdir()
    path = root / 'data/other.json'
    path.write_text('original')
    run('git', 'add', '.')
    run('git', 'commit', '-m', 'baseline')
    path.write_text('staged valuable data')
    run('git', 'add', str(path))
    path.write_text('original')
    monkeypatch.setattr(retry, 'ROOT', root)
    monkeypatch.setattr(retry, 'MARKER', root / 'data/mdsap_retry.json')
    monkeypatch.setattr(retry, 'STATUS', root / 'data/mdsap_status.json')
    monkeypatch.setattr(retry, 'DATA', root / 'data/regulations.json')
    with pytest.raises(RuntimeError, match='changes'):
        retry.main()
    assert path.read_text() == 'original'
    assert run('git', 'show', ':data/other.json') == 'staged valuable data'


def test_retry_rejects_untracked_checkout_files(tmp_path, monkeypatch):
    import subprocess
    import pytest
    subprocess.run(['git', 'init', '-b', 'main'], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(['git', '-c', 'user.name=Test', '-c', 'user.email=t@example.invalid', 'commit', '--allow-empty', '-m', 'baseline'], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / 'valuable.txt').write_text('keep')
    monkeypatch.setattr(retry, 'ROOT', tmp_path)
    monkeypatch.setattr(retry, 'STATUS', tmp_path / 'status.json')
    monkeypatch.setattr(retry, 'DATA', tmp_path / 'data.json')
    monkeypatch.setattr(retry, 'MARKER', tmp_path / 'marker.json')
    with pytest.raises(RuntimeError, match='changes'):
        retry.main()
    assert (tmp_path / 'valuable.txt').read_text() == 'keep'


def test_persist_refuses_unrelated_changes_without_restoring_them(tmp_path, monkeypatch):
    import subprocess
    import pytest
    def run(*args):
        return subprocess.run(args, cwd=tmp_path, check=True, capture_output=True, text=True).stdout
    run('git', 'init', '-b', 'main')
    run('git', 'config', 'user.name', 'Test')
    run('git', 'config', 'user.email', 't@example.invalid')
    (tmp_path / 'data').mkdir()
    for name in ('regulations.json', 'mdsap_status.json', 'other.json'):
        (tmp_path / 'data' / name).write_text('{}')
    run('git', 'add', '.')
    run('git', 'commit', '-m', 'baseline')
    other = tmp_path / 'data/other.json'
    other.write_text('keep')
    monkeypatch.setattr(retry, 'ROOT', tmp_path)
    with pytest.raises(RuntimeError, match='changes'):
        retry.persist(None, None, None, None, [], [])
    assert other.read_text() == 'keep'
