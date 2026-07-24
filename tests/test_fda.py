from collectors import fda


def test_versions_api_requests_part_820_directly():
    assert "?part=820" in fda.VERSIONS_API


def test_latest_issue_date_accepts_filtered_ecfr_response():
    payload = {
        "content_versions": [
            {"part": "820", "issue_date": "2024-02-02"},
            {"part": "820", "issue_date": "2026-02-04"},
        ],
        "meta": {"latest_issue_date": "2026-02-04"},
    }

    assert fda._extract_latest_issue_date(payload) == "2026-02-04"


def test_latest_issue_date_rejects_response_without_part_820():
    payload = {
        "content_versions": [
            {"part": "1", "issue_date": "2026-02-04"},
        ]
    }

    assert fda._extract_latest_issue_date(payload) is None
