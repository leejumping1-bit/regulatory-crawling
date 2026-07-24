from collectors import mfds
from collectors.summarizer import summarize


def test_mfds_extracts_down_do_attachment_links():
    html = """
    <div class="bbs_view01">
      <a href="/brd/m_207/view.do?seq=15181">의료기기 고시 제목</a>
      <a href="/brd/m_207/down.do?brd_id=data0008&amp;seq=15181&amp;data_tp=A&amp;file_seq=1">다운받기</a>
    </div>
    """
    rows = mfds._extract_rows_from_html(
        html,
        board_name="제개정고시등",
        board_url="https://www.mfds.go.kr/brd/m_207/list.do",
        keyword="의료기기",
        since_year=2026,
        since_month=1,
    )
    assert len(rows) == 1
    assert rows[0]["attachments"] == [
        "https://www.mfds.go.kr/brd/m_207/down.do?brd_id=data0008&seq=15181&data_tp=A&file_seq=1"
    ]


def test_mfds_detail_prefers_visible_bv_content_over_site_navigation():
    html = """
    <html><body><nav>법률 제·개정 현황</nav>
      <div class="bbs_view01"><div class="bv_cont">
        <p>「의료기기법」에 따른 지정 유효기간 및 갱신 절차를 정비합니다.</p>
        <p>&lt; 주요내용 &gt; 정기 지도·점검 범위를 합리화합니다.</p>
      </div></div>
    </body></html>
    """
    text = mfds._visible_detail_text(html)
    assert "지정 유효기간" in text
    assert "법률 제·개정 현황" not in text


def test_mfds_attachment_format_candidates_detect_pdf():
    assert mfds._attachment_filenames(b"%PDF-1.7\n...") == ["attachment.pdf"]


def test_mfds_uses_page_summary_when_major_content_exists():
    assert mfds._has_major_content("본문입니다. < 주요내용 > 가. 지정 절차를 정비합니다.") is True
    assert mfds._has_major_content("고시 전문을 첨부파일로 게시합니다.") is False


def test_legal_document_summary_uses_structure_and_is_detailed():
    result = summarize(
        "「의료기기 제조 및 품질관리 관련 기관 지정 등에 관한 규정」(제2026-47호)",
        "제1장 총칙\n제1조 목적 이 규정은 의료기기 제조 및 품질관리 관련 기관의 지정 등에 필요한 사항을 정함을 목적으로 한다.\n제2장 지정\n제5조 모집공고 지정 신청과 평가 절차를 정한다.\n부칙 이 고시는 고시한 날부터 시행한다.",
    )
    assert "적용 범위" in result
    assert "구성" in result
    assert "시행" in result
    assert len(result) >= 500
