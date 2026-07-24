from app_logic import filter_by_month
from collectors import pmda


def test_app_defaults_to_all_data():
    data = [{"search_month": "2026-01"}, {"search_month": "2026-02"}]
    assert filter_by_month(data) == data
    assert filter_by_month(data, "전체") == data


def test_app_can_filter_when_month_is_selected():
    data = [{"search_month": "2026-01"}, {"search_month": "2026-02"}]
    assert filter_by_month(data, "2026-02") == [{"search_month": "2026-02"}]


def test_pmda_extracts_year_from_pdf_title():
    assert pmda._extract_year("Tentative translation, as revised in 2021") == 2021


def test_pmda_skips_documents_older_than_collection_start():
    assert pmda._is_in_scope("Tentative translation, as revised in 2021", 2026) is False
    assert pmda._is_in_scope("PMDA guidance revised in 2026", 2026) is True


def test_pmda_skips_documents_without_a_date():
    assert pmda._is_in_scope("Standards for Re-manufactured Single-use Medical Devices", 2026) is False
