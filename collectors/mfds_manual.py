"""
MFDS(식약처) 처리 모듈 — "수동 입력 보조" 방식

※ 왜 자동 크롤링이 아닌가:
  mfds.go.kr 은 robots.txt로 자동화된 접근(봇)을 명시적으로 차단하고 있는 것으로
  확인되었습니다. 이는 GitHub 서버 위치(해외 IP)의 문제가 아니라 사이트 운영정책이며,
  self-hosted runner를 한국에 두더라도 '자동화된 스크립트'라는 사실 자체는 바뀌지
  않으므로 robots.txt 를 우회하는 코드는 만들지 않습니다.

  대신, 사용자가 브라우저로 직접 확인/다운로드한 첨부파일(PDF·HWPX)을 이 도구에
  업로드하면 — 이건 로봇이 아니라 사람이 직접 내려받아 올리는 정상적인 사용 방식입니다 —
  텍스트 추출 → 자동요약 → Gap 분석까지는 자동으로 처리해 드립니다.
"""
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from collectors.file_extract import extract_text  # noqa: E402
from collectors.summarizer import summarize, guess_scope, guess_sop_flag  # noqa: E402
from collectors.diff_engine import generate_gap  # noqa: E402
from collectors.store import load_previous_snapshot, save_snapshot  # noqa: E402


def process_manual_entry(title, doc_no, publish_date, effective_date, url,
                          uploaded_bytes=None, uploaded_filename=None):
    """
    Streamlit 사이드바에서 사용자가 업로드한 파일 + 메타정보를 받아
    regulations.json 항목 하나를 생성한다.
    """
    body_text, status = ("", "첨부파일 없음")
    if uploaded_bytes and uploaded_filename:
        body_text, status = extract_text(uploaded_bytes, uploaded_filename)

    summary_source = body_text or title
    prev = load_previous_snapshot("MFDS", doc_no)
    gap = generate_gap(prev, body_text or title)
    if body_text:
        save_snapshot("MFDS", doc_no, body_text)

    summary = summarize(title, summary_source)
    if not body_text:
        summary += f"\n\n(원문 파일이 첨부되지 않아 제목만으로 생성된 요약입니다 — 상태: {status})"

    return {
        "search_month": (publish_date or "")[:7],
        "publish_date": publish_date,
        "effective_date": effective_date,
        "publisher": "MFDS (Korea)",
        "doc_no": doc_no,
        "title": title,
        "summary": summary,
        "scope": guess_scope(title + " " + summary_source),
        "sop_required": "★" if guess_sop_flag(title + " " + summary_source) else "",
        "url": url,
        "gap_analysis": gap,
    }
