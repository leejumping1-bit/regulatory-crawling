from app_logic import (
    estimate_export_row_height,
    extract_core_content,
    filter_by_month,
    filter_by_publisher,
)
from collectors import pmda


def test_app_defaults_to_all_data():
    data = [{"search_month": "2026-01"}, {"search_month": "2026-02"}]
    assert filter_by_month(data) == data
    assert filter_by_month(data, "전체") == data


def test_app_can_filter_when_month_is_selected():
    data = [{"search_month": "2026-01"}, {"search_month": "2026-02"}]
    assert filter_by_month(data, "2026-02") == [{"search_month": "2026-02"}]


def test_app_defaults_to_all_publishers():
    data = [{"publisher": "MDCG (EU)"}, {"publisher": "MFDS (Korea)"}]
    assert filter_by_publisher(data) == data
    assert filter_by_publisher(data, "전체") == data


def test_app_can_filter_when_publisher_is_selected():
    data = [{"publisher": "MDCG (EU)"}, {"publisher": "MFDS (Korea)"}]
    assert filter_by_publisher(data, "MFDS (Korea)") == [{"publisher": "MFDS (Korea)"}]


def test_export_summary_keeps_only_core_content_section():
    summary = (
        "[문서 목적] 발행 목적\n"
        "[핵심 내용]\n- 첫 번째 핵심사항\n- 두 번째 핵심사항\n"
        "[적용 범위] 의료기기 전반\n"
        "[확인 필요 사항] 원문 확인"
    )
    assert extract_core_content(summary) == "첫 번째 핵심사항\n- 두 번째 핵심사항"


def test_export_summary_falls_back_when_no_structured_core_marker():
    assert extract_core_content("핵심 변경사항만 있는 요약") == "핵심 변경사항만 있는 요약"


def test_export_row_height_grows_for_multiline_core_content():
    short = estimate_export_row_height(["1", "짧은 제목"], [6, 48])
    long = estimate_export_row_height(["1", "핵심내용\n" + "가" * 180], [6, 58])
    assert short == 19
    assert long > short


def test_pmda_extracts_year_from_pdf_title():
    assert pmda._extract_year("Tentative translation, as revised in 2021") == 2021


def test_pmda_skips_documents_older_than_collection_start():
    assert pmda._is_in_scope("Tentative translation, as revised in 2021", 2026) is False
    assert pmda._is_in_scope("PMDA guidance revised in 2026", 2026) is True


def test_pmda_skips_documents_without_a_date():
    assert pmda._is_in_scope("Standards for Re-manufactured Single-use Medical Devices", 2026) is False


def test_pmda_accepts_only_official_https_pdf_urls():
    assert pmda._safe_pdf_url("/files/000248602.pdf") == "https://www.pmda.go.jp/files/000248602.pdf"
    assert pmda._safe_pdf_url("https://example.com/evil.pdf") is None
    assert pmda._safe_pdf_url("http://www.pmda.go.jp/files/old.pdf") is None
