"""Server-side GitHub Actions dispatch for durable regulatory updates."""

from collections.abc import Callable

import requests


DISPATCH_URL = (
    "https://api.github.com/repos/leejumping1-bit/regulatory-crawling/"
    "actions/workflows/scheduled_crawl.yml/dispatches"
)
RUNS_URL = DISPATCH_URL.removesuffix("/dispatches") + "/runs"


class UpdateAlreadyRunning(RuntimeError):
    """Raised when the durable update workflow already has active work."""


def dispatch_today_update(
    token: str,
    *,
    get: Callable = requests.get,
    post: Callable = requests.post,
) -> None:
    """Request the shared workflow in today-only mode.

    GitHub returns HTTP 204 when the request is accepted. That means queued,
    not persisted; completion remains the workflow's responsibility.
    """
    token = str(token or "").strip()
    if not token:
        raise ValueError("GITHUB_WORKFLOW_TOKEN is not configured")

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        runs_response = get(
            RUNS_URL,
            headers=headers,
            params={"per_page": 20},
            timeout=15,
        )
        runs_response.raise_for_status()
        workflow_runs = runs_response.json().get("workflow_runs", [])
        if any(run.get("status") in {"queued", "in_progress"} for run in workflow_runs):
            raise UpdateAlreadyRunning(
                "이미 영구 업데이트가 실행 중입니다. 완료 후 다시 확인해 주세요."
            )

        response = post(
            DISPATCH_URL,
            headers=headers,
            json={"ref": "main", "inputs": {"mode": "today"}},
            timeout=15,
        )
        response.raise_for_status()
    except UpdateAlreadyRunning:
        raise
    except requests.RequestException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        detail = f" (HTTP {status})" if status else ""
        raise RuntimeError(f"GitHub 영구 업데이트 요청 실패{detail}") from exc
