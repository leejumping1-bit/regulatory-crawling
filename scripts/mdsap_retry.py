"""Scheduled MDSAP-only retries, coordinated through durable crawl status."""
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
STATUS = ROOT / 'data/mdsap_status.json'
MARKER = ROOT / 'data/mdsap_retry.json'
DATA = ROOT / 'data/regulations.json'


def read(path, default=None):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return default


def timestamp(value):
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError('timestamp must have a timezone')
    return parsed.astimezone(timezone.utc)


def priority_failed(status):
    if not isinstance(status, dict):
        return False
    sources = status.get('sources')
    if isinstance(sources, dict) and sources.get('p0002') in ('ok', 'error'):
        return sources['p0002'] == 'error'
    # Legacy or interrupted checks have no source breakdown; fail closed.
    return status.get('status') == 'error'


def plan_retry(status, marker, now):
    if not priority_failed(status):
        return None, False
    try:
        checked = timestamp(status['checked_at'])
        if checked > now:
            return None, False
        if not isinstance(marker, dict) or marker.get('last_checked_at') != status['checked_at']:
            marker = {'first_attempt_at': status['checked_at'], 'last_checked_at': status['checked_at'], 'attempt': 0}
        attempt = marker['attempt']
        if attempt not in (0, 1, 2):
            raise ValueError('invalid attempt')
        first = timestamp(marker['first_attempt_at'])
        if first > now:
            raise ValueError('future initial attempt')
        marker = dict(marker)
        marker['next_retry_at'] = (first + timedelta(minutes=30 if attempt == 0 else 120)).isoformat() if attempt < 2 else None
        return marker, bool(marker['next_retry_at'] and now >= timestamp(marker['next_retry_at']))
    except (KeyError, TypeError, ValueError):
        return None, False


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, check=True, text=True, stdout=subprocess.PIPE).stdout


def write(path, value):
    if value is None:
        path.unlink(missing_ok=True)
    else:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def persist(base_status, base_marker, marker, result_status, before, after):
    """Reapply only changed MDSAP rows to latest data; reject stale observations."""
    from collectors import store
    old = {(x.get('publisher'), x.get('doc_no')): x for x in before if x.get('publisher') == 'MDSAP'}
    changed = [x for x in after if x.get('publisher') == 'MDSAP' and old.get((x.get('publisher'), x.get('doc_no'))) != x]
    # Only the crawler's two outputs may be dirty; never restore other data or
    # accidentally include a staged change in the retry commit.
    if (git('diff', '--cached', '--name-only', '--', '.').strip() or
            git('diff', '--name-only', '--', '.', ':(exclude)data/regulations.json',
                ':(exclude)data/mdsap_status.json').strip()):
        raise RuntimeError('checkout contains unexpected changes after collection')
    git('restore', '--worktree', '--', 'data/regulations.json', 'data/mdsap_status.json')
    for attempt in range(3):
        git('fetch', 'origin', 'main')
        git('checkout', '--detach', 'FETCH_HEAD')
        if read(STATUS) != base_status or read(MARKER) != base_marker:
            print('MDSAP status or retry marker changed; discarding stale retry result')
            return
        latest = {(x.get('publisher'), x.get('doc_no')): x for x in read(DATA, []) if x.get('publisher') == 'MDSAP'}
        # A newer revision may have a different doc_no; guard the whole MDSAP
        # set, ignoring the presentation-only row numbers changed by sorting.
        clean = lambda rows: {k: {f: v for f, v in row.items() if f != 'no'} for k, row in rows.items()}
        if clean(latest) != clean(old):
            print('MDSAP records changed concurrently; discarding stale retry result')
            return
        if changed:
            store.upsert_regulations(changed)
        write(STATUS, result_status)
        write(MARKER, marker)
        git('add', '-A', '--', 'data/regulations.json', 'data/mdsap_status.json')
        if MARKER.exists() or base_marker is not None:
            git('add', '-A', '--', 'data/mdsap_retry.json')
        if not git('diff', '--cached', '--name-only').strip():
            return
        git('commit', '-m', 'chore: retry MDSAP collection [skip ci]')
        pushed = subprocess.run(['git', 'push', 'origin', 'HEAD:main'], cwd=ROOT)
        if pushed.returncode == 0:
            return
        print(f'Push attempt {attempt + 1} failed; reapplying to latest data')
    raise RuntimeError('Unable to push retry data after three attempts')


def main():
    # Check index and worktree separately: their changes can cancel in diff HEAD.
    for args in (['diff', '--quiet'], ['diff', '--cached', '--quiet']):
        if subprocess.run(['git', *args], cwd=ROOT).returncode:
            raise RuntimeError('checkout contains pre-existing changes')
    if git('ls-files', '--others', '--exclude-standard').strip():
        raise RuntimeError('checkout contains untracked changes')
    if MARKER.exists() and not git('ls-files', '--', 'data/mdsap_retry.json').strip():
        raise RuntimeError('retry marker is untracked')
    status, original_marker = read(STATUS), read(MARKER)
    marker, due = plan_retry(status, original_marker, datetime.now(timezone.utc))
    before = read(DATA, [])
    if due:
        import crawler
        crawler.run_crawler(only=['mdsap'])
        result = read(STATUS)
        if not isinstance(result, dict) or result.get('status') not in ('ok', 'error'):
            raise ValueError('missing MDSAP result status')
        if not priority_failed(result):
            marker = None
        else:
            marker['attempt'] += 1
            marker['last_checked_at'] = result['checked_at']
            marker, _ = plan_retry(result, marker, datetime.now(timezone.utc))
    else:
        result = status
    after = read(DATA, [])
    persist(status, original_marker, marker, result, before, after)


if __name__ == '__main__':
    main()
