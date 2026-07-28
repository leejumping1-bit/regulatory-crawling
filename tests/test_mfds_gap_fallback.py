from collectors.mfds import _build_mfds_gap


def test_amendment_without_previous_history_uses_date_and_change_sections():
    body = (
        "의료기기법 시행규칙 일부개정령 공포\n"
        "개정이유 의료기기 관리 기준을 정비한다.\n"
        "주요내용 가. 허가 기준을 정비한다. 나. 보고 절차를 명확히 한다.\n"
        "신구조문대비표 제10조 중 일부를 개정한다.\n"
        "제1조 목적 이 규칙은 의료기기의 제조와 수입에 관한 사항을 정한다."
    )

    gap = _build_mfds_gap(
        None,
        body,
        "의료기기법 시행규칙 일부개정령 공포",
        "2026-07-01",
    )

    assert gap["past_text"] == "과거 이력 확인 실패"
    assert "개정일자: 2026-07-01" in gap["present_text"]
    assert "개정이유" in gap["present_text"]
    assert "주요내용" in gap["present_text"]
    assert "신구조문대비표" in gap["present_text"]
    assert "의료기기법 시행규칙 일부개정령 공포" not in gap["present_text"]
    assert "과거 이력 확인 실패" in gap["diff_html"]


def test_failed_history_links_to_the_official_amendment_notice():
    gap = _build_mfds_gap(
        None,
        "",
        "의료기기법 시행규칙 일부개정령 공포",
        "2026-07-01",
        "https://www.mfds.go.kr/brd/m_203/view.do?seq=123",
    )

    assert "https://www.mfds.go.kr/brd/m_203/view.do?seq=123" in gap["present_text"]
    assert "공식 MFDS 개정 공고 열기" in gap["diff_html"]


def test_amendment_without_body_does_not_use_title_as_current_text():
    gap = _build_mfds_gap(
        None,
        "",
        "의료기기법 시행규칙 일부개정령 공포",
        "2026-07-01",
    )

    assert gap["past_text"] == "과거 이력 확인 실패"
    assert gap["present_text"] == (
        "개정일자: 2026-07-01\n\n공식 개정 공고의 변경 내용을 확인하세요."
    )
    assert "의료기기법 시행규칙 일부개정령 공포" not in gap["present_text"]


def test_existing_previous_version_still_gets_normal_diff():
    gap = _build_mfds_gap(
        "제10조 허가 기준을 둔다.",
        "제10조 허가 기준을 강화한다.",
        "의료기기법 시행규칙 일부개정령 공포",
        "2026-07-01",
    )

    assert gap["past_text"] != "과거 이력 확인 실패"
    assert "허가 기준을 둔다." in gap["past_text"]
    assert "허가 기준을 강화한다." in gap["present_text"]
