import json
from types import SimpleNamespace
from datetime import datetime

import crawler


def test_mdsap_logs_known_failure_without_exposing_secrets(tmp_path, monkeypatch, capsys):
    path = tmp_path / 'mdsap_status.json'
    monkeypatch.setattr(crawler, 'MDSAP_STATUS_PATH', path)
    monkeypatch.setattr(crawler, 'load_regulations', lambda: [])
    detail = ('P0002 현재 확인 실패: priority version or exact official PDF link unavailable or ambiguous; '
              'RSS 확인 실패 (https://www.mdsap.global/feeds/documents.xml): token=supersecret')
    block = SimpleNamespace(ok=False, error=detail)
    monkeypatch.setattr(crawler.importlib, 'import_module', lambda _: SimpleNamespace(run=lambda y, m: ([], block)))
    crawler.run_crawler(only=['mdsap'])
    output = capsys.readouterr().out
    assert 'priority version or exact official PDF link unavailable or ambiguous' in output
    assert 'supersecret' not in output
    assert 'supersecret' not in path.read_text()
    assert json.loads(path.read_text())['status'] == 'error'


def test_mdsap_unexpected_exception_does_not_leak_to_log(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(crawler, 'MDSAP_STATUS_PATH', tmp_path / 'status.json')
    monkeypatch.setattr(crawler, 'load_regulations', lambda: [])
    def fail(y, m):
        raise RuntimeError('token=supersecret')
    monkeypatch.setattr(crawler.importlib, 'import_module', lambda _: SimpleNamespace(run=fail))
    crawler.run_crawler(only=['mdsap'])
    assert 'supersecret' not in capsys.readouterr().out
    assert 'supersecret' not in (tmp_path / 'status.json').read_text()


def test_mdsap_status_freshness():
    from datetime import datetime, timezone, timedelta
    from app_logic import mdsap_status_is_stale
    now = datetime(2026, 11, 6, tzinfo=timezone.utc)
    assert not mdsap_status_is_stale('2026-11-05T00:00:00+00:00', now)
    assert mdsap_status_is_stale('2026-11-03T00:00:00+00:00', now)
    assert mdsap_status_is_stale('2099-01-01T00:00:00+00:00', now)


def test_mdsap_success_writes_durable_status(tmp_path, monkeypatch):
    path = tmp_path / 'data' / 'mdsap_status.json'
    monkeypatch.setattr(crawler, 'MDSAP_STATUS_PATH', path, raising=False)
    monkeypatch.setattr(crawler.importlib, 'import_module', lambda _: SimpleNamespace(run=lambda y, m: ([{'title': 'priority'}], None)))
    monkeypatch.setattr(crawler, 'load_regulations', lambda: [])
    monkeypatch.setattr(crawler, 'upsert_regulations', lambda items: None)
    crawler.run_crawler(only=['mdsap'])
    status = json.loads(path.read_text())
    assert status['status'] == 'ok'
    assert datetime.fromisoformat(status['checked_at']).utcoffset() is not None


def test_partial_and_exception_overwrite_success_with_error(tmp_path, monkeypatch):
    path = tmp_path / "mdsap_status.json"
    monkeypatch.setattr(crawler, "MDSAP_STATUS_PATH", path)
    monkeypatch.setattr(crawler, "load_regulations", lambda: [])
    saved = []
    monkeypatch.setattr(crawler, "upsert_regulations", lambda items: saved.extend(items))
    block = SimpleNamespace(ok=False, blocked=False, robots_disallowed=False, error="secret should not be persisted")
    mod = SimpleNamespace(run=lambda y, m: ([{"title": "partial"}], block))
    monkeypatch.setattr(crawler.importlib, "import_module", lambda _: mod)
    crawler.run_crawler(only=["mdsap"])
    assert saved == [{"title": "partial"}]
    assert json.loads(path.read_text())["status"] == "error"
    assert "secret" not in path.read_text()
    mod.run = lambda y, m: ([{"title": "priority"}], None)
    crawler.run_crawler(only=["mdsap"])
    assert json.loads(path.read_text())["status"] == "ok"
    def fail(y, m):
        raise RuntimeError("secret")
    mod.run = fail
    crawler.run_crawler(only=["mdsap"])
    assert json.loads(path.read_text())["status"] == "error"
    assert "secret" not in path.read_text()


def test_app_renders_remote_status_and_rerun(monkeypatch):
    import requests
    from streamlit.testing.v1 import AppTest
    class Response:
        def __init__(self, payload): self.payload = payload
        def raise_for_status(self): pass
        def json(self): return self.payload
    from datetime import timezone
    checked_at = datetime.now(timezone.utc).isoformat()
    state = {"status": "error", "checked_at": checked_at}
    def get(url, **kwargs):
        return Response(state if url.endswith("mdsap_status.json") else [])
    monkeypatch.setattr(requests, "get", get)
    import streamlit as st
    st.cache_data.clear()
    from pathlib import Path
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run(timeout=90)
    assert not app.exception
    assert any("MDSAP" in x.value and "실패" in x.value and checked_at in x.value for x in app.caption)
    state["status"] = "ok"
    import streamlit as st
    st.cache_data.clear()
    app.run(timeout=90)
    assert not app.exception
    assert not any("MDSAP" in x.value and ("완료" in x.value or "실패" in x.value) for x in app.caption)
    assert any("MDSAP AU P0002 마지막 저장 버전" in x.value for x in app.caption)


def test_workflow_stages_status_even_when_crawler_fails():
    from pathlib import Path
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/scheduled_crawl.yml").read_text()
    commit_step = workflow.split("- name: Commit and push if updated", 1)[1]
    assert "if: ${{ !cancelled() }}" in commit_step
    assert "git add data/mdsap_status.json" in commit_step


def test_empty_result_is_unverified_not_success(tmp_path, monkeypatch):
    path = tmp_path / "mdsap_status.json"
    monkeypatch.setattr(crawler, "MDSAP_STATUS_PATH", path)
    monkeypatch.setattr(crawler, "load_regulations", lambda: [])
    monkeypatch.setattr(crawler.importlib, "import_module", lambda _: SimpleNamespace(run=lambda y, m: ([], None)))
    crawler.run_crawler(only=["mdsap"])
    assert json.loads(path.read_text())["status"] == "error"


def test_today_only_does_not_overwrite_durable_status(tmp_path, monkeypatch):
    path = tmp_path / "mdsap_status.json"
    path.write_text('{"status":"ok","checked_at":"2026-01-01T00:00:00+00:00"}')
    monkeypatch.setattr(crawler, "MDSAP_STATUS_PATH", path)
    monkeypatch.setattr(crawler, "load_regulations", lambda: [])
    monkeypatch.setattr(crawler.importlib, "import_module", lambda _: SimpleNamespace(run=lambda y, m: ([], None)))
    crawler.run_crawler(only=["mdsap"], today_only=True)
    assert json.loads(path.read_text())["status"] == "ok"


def test_app_shows_unknown_when_remote_status_unavailable(monkeypatch):
    import requests
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    import streamlit as st
    class Response:
        def raise_for_status(self): pass
        def json(self): return []
    def get(url, **kwargs):
        if url.endswith("mdsap_status.json"):
            raise requests.ConnectionError("offline")
        return Response()
    monkeypatch.setattr(requests, "get", get)
    st.cache_data.clear()
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run(timeout=90)
    assert not app.exception
    assert any("MDSAP" in x.value and "확인 불가" in x.value for x in app.caption)
