"""Server-side GitHub Actions dispatch for durable regulatory updates."""

from collections.abc import Callable

import requests


DISPATCH_URL = (
    "https://api.github.com/repos/leejumping1-bit/regulatory-crawling/"
    "actions/workflows/scheduled_crawl.yml/dispatches"
)


def dispatch_today_update(
    token: str,
    *,
    post: Callable = requests.post,
) -> None:
    """Request the shared workflow in today-only mode.

    GitHub returns HTTP 204 when the request is accepted. That means queued,
    not persisted; completion remains the workflow's responsibility.
    """
    token = str(token or "").strip()
    if not token:
        raise ValueError("GITHUB_WORKFLOW_TOKEN is not configured")

    try:
        response = post(
            DISPATCH_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={"ref": "main", "inputs": {"mode": "today"}},
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        detail = f" (HTTP {status})" if status else ""
        raise RuntimeError(f"GitHub 영구 업데이트 요청 실패{detail}") from exc
