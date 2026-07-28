from collectors.diff_engine import generate_document_gap, generate_gap, should_treat_as_new


def test_new_published_document_has_no_past_content():
    gap = generate_gap("", "가. 새로 게시된 내용\n나. 추가 단락")
    assert gap["past_text"] == "N.A. (신규 문서)"
    assert "새로 게시된 내용" in gap["present_text"]
    assert "과거 규격 내용 없음" in gap["diff_html"]


def test_gap_returns_only_changed_paragraphs():
    past = "공통 문단\n삭제된 문단\n변경 전 문단"
    present = "공통 문단\n추가된 문단\n변경 후 문단"
    gap = generate_gap(past, present)
    assert "공통 문단" not in gap["past_text"]
    assert "공통 문단" not in gap["present_text"]
    assert "삭제된 문단" in gap["past_text"]
    assert "변경 전 문단" in gap["past_text"]
    assert "추가된 문단" in gap["present_text"]
    assert "변경 후 문단" in gap["present_text"]
    assert "diff-del" in gap["diff_html"]
    assert "diff-add" in gap["diff_html"]


def test_identical_content_is_collapsed():
    gap = generate_gap("동일 문단", "동일 문단")
    assert gap["past_text"] == "변경된 내용 없음"
    assert gap["present_text"] == "변경된 내용 없음"
    assert "변경된 문단이 없습니다" in gap["diff_html"]


def test_enactment_or_news_keeps_full_current_content_even_with_snapshot():
    gap = generate_document_gap(
        "과거 snapshot 전체 내용",
        "제정된 현재 문서 전체 내용",
        title="의료기기법 시행규칙 제정",
        publisher="MFDS (Korea)",
    )
    assert gap["past_text"] == "비교 제외 (신규 제정·발표 문서)"
    assert gap["present_text"] == "비교 제외 (신규 제정·발표 문서)"
    assert "Gap 분석을 수행하지 않습니다" in gap["diff_html"]
    assert should_treat_as_new("News announcement", "현재 게시 내용")


def test_revision_overrides_news_skip_rule():
    assert not should_treat_as_new(
        "News announcement",
        "MDCG 2024-1 Rev. 2 — Revision history and changes to the document",
        "MDCG (EU)",
    )
