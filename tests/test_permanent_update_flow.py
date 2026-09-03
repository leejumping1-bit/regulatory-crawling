from pathlib import Path

import pytest

from workflow_dispatch import dispatch_today_update


ROOT = Path(__file__).resolve().parents[1]


class FakeResponse:
    status_code = 204

    def raise_for_status(self):
        return None


def test_dispatch_today_update_uses_server_side_token_and_today_mode():
    captured = {}

    def fake_post(url, *, headers, json, timeout):
        captured.update(url=url, headers=headers, json=json, timeout=timeout)
        return FakeResponse()

    dispatch_today_update("secret-token", post=fake_post)

    assert captured["url"].endswith(
        "/repos/leejumping1-bit/regulatory-crawling/"
        "actions/workflows/scheduled_crawl.yml/dispatches"
    )
    assert captured["headers"]["Authorization"] == "Bearer secret-token"
    assert captured["json"] == {"ref": "main", "inputs": {"mode": "today"}}
    assert captured["timeout"] == 15


def test_dispatch_today_update_rejects_missing_token():
    with pytest.raises(ValueError, match="GITHUB_WORKFLOW_TOKEN"):
        dispatch_today_update("")


def test_app_has_only_the_durable_update_path():
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "지금 실행 (오늘자 영구 업데이트)" in app_source
    assert "dispatch_today_update" in app_source
    assert 'st.secrets["GITHUB_WORKFLOW_TOKEN"]' in app_source
    assert "manual_data" not in app_source
    assert "run_crawler" not in app_source
    assert "임시 미리보기" not in app_source
    assert "st.link_button" not in app_source


def test_manual_workflow_collects_today_while_schedule_collects_full_history():
    workflow = (
        ROOT / ".github" / "workflows" / "scheduled_crawl.yml"
    ).read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "mode:" in workflow
    assert "default: today" in workflow
    assert "${{ github.event_name }}' == 'workflow_dispatch'" in workflow
    assert "${{ inputs.mode }}' == 'today'" in workflow
    assert "python crawler.py --today-only" in workflow
    assert "python crawler.py --since 2026-01" in workflow
    assert "group: regulatory-data-update" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "contents: write" in workflow
