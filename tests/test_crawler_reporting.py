from types import SimpleNamespace
import crawler


def test_federal_register_failure_still_checks_part820(monkeypatch):
    from collectors import fda
    def fail(*args):
        raise RuntimeError('FR unavailable')
    monkeypatch.setattr(fda, 'discover_federal_register', fail)
    monkeypatch.setattr(fda, '_run_part_820', lambda *args: ([{'doc_no':'21 CFR Part 820'}], None))
    items, error = fda.run()
    assert len(items) == 1 and error and not error.ok
    assert 'FR unavailable' in error.error


def test_part820_failure_keeps_federal_register_results(monkeypatch):
    from collectors import fda
    expected = {'doc_no': '2026-12345'}
    monkeypatch.setattr(fda, 'discover_federal_register', lambda *args: [expected])
    def fail(*args):
        raise RuntimeError('820 unavailable')
    monkeypatch.setattr(fda, '_run_part_820', fail)
    items, error = fda.run()
    assert items == [expected]
    assert error and error.ok is False and '820 unavailable' in error.error


def test_failed_fetch_not_reported_as_zero_success(monkeypatch):
    module = SimpleNamespace(run=lambda y, m: ([], SimpleNamespace(ok=False, blocked=False, robots_disallowed=False, error='timeout')))
    monkeypatch.setattr(crawler.importlib, 'import_module', lambda _: module)
    monkeypatch.setattr(crawler, 'load_regulations', lambda: [])
    _, summary = crawler.run_crawler(only=['mdsap'])
    assert '실패' in summary['mdsap']
    assert '0건 수집' not in summary['mdsap']
