from pathlib import Path

from app_logic import permanent_update_workflow_url


ROOT = Path(__file__).resolve().parents[1]


def test_permanent_update_points_to_manual_github_workflow():
    assert permanent_update_workflow_url() == (
        "https://github.com/leejumping1-bit/regulatory-crawling/"
        "actions/workflows/scheduled_crawl.yml"
    )


def test_app_separates_preview_from_permanent_update():
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "임시 미리보기" in app_source
    assert "영구 업데이트 실행" in app_source
    assert "st.link_button" in app_source


def test_scheduled_and_manual_updates_are_serialized():
    workflow = (
        ROOT / ".github" / "workflows" / "scheduled_crawl.yml"
    ).read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "concurrency:" in workflow
    assert "group: regulatory-data-update" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "permissions:" in workflow
    assert "contents: write" in workflow
