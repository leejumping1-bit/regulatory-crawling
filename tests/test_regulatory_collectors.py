from collectors import health_canada, mfds


def test_health_canada_dates_map_to_requested_fields():
    text = "Medical Devices Regulations last amended on 2026-01-01. Regulations are current to 2026-05-26."

    amended, current_to = health_canada._extract_dates(text)

    assert amended == "2026-01-01"
    assert current_to == "2026-05-26"


def test_mfds_is_limited_to_the_three_requested_boards():
    assert list(mfds.BOARDS) == [
        "법/시행령/시행규칙",
        "고시훈령예규(고시전문)",
        "제개정고시등",
    ]


def test_mfds_extracts_external_law_links_and_view_links():
    html = """
    <ul>
      <li><a class="title" href="https://www.law.go.kr/법령/의료기기법시행규칙">의료기기법 시행규칙 일부개정령</a><div>2026.7.1.</div></li>
      <li><a href="./view.do?seq=123">의료기기 고시 전문</a><div>2026.7.2.</div></li>
    </ul>
    """

    rows = mfds._extract_rows_from_html(
        html,
        board_name="법/시행령/시행규칙",
        board_url="https://www.mfds.go.kr/brd/m_203/list.do",
        keyword="의료기기",
        since_year=2026,
        since_month=1,
    )

    assert len(rows) == 2
    assert rows[0]["view_url"].startswith("https://www.law.go.kr/")
    assert rows[1]["view_url"].startswith("https://www.mfds.go.kr/brd/m_203/view.do")


def test_mfds_rejects_untrusted_external_links():
    assert mfds._safe_url(
        "https://www.mfds.go.kr/brd/m_203/list.do",
        "https://example.com/secret",
    ) is None
