from pathlib import Path

from app_logic import permanent_update_workflow_url


ROOT = Path(__file__).resolve().parents[1]


def test_permanent_update_points_to_manual_github_workflow():
    assert permanent_update_workflow_url() == (
        "https://github.com/leejumping1-bit/regulatory-crawling/"
        "actions/workflows/scheduled_crawl.yml"
    )


def test_app_shows_only_refresh_link_and_ignores_stale_preview(monkeypatch):
    from streamlit.testing.v1 import AppTest
    import requests

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return []

    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: Response())
    app = AppTest.from_file(str(ROOT / "app.py"))
    app.session_state["manual_data"] = [{"title": "stale preview"}]
    app.run(timeout=30)

    assert not app.exception
    links = app.get("link_button")
    refresh = [link for link in links if link.proto.label == "갱신"]
    assert len(refresh) == 1
    assert refresh[0].proto.url == permanent_update_workflow_url()
    assert all("미리보기" not in button.label for button in app.button)
    assert all("임시" not in caption.value for caption in app.caption)
    assert all("stale preview" not in element.value for element in app.markdown)
    assert all("지금 실행" not in info.value for info in app.info)


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
