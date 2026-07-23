"""
MFDS(식품의약품안전처) 자동 수집기 — v2 (제목검색 방식)

이전 버전 문제: 게시판 최신글을 무작정 훑어서 상세페이지를 일일이 방문 → 느림.
이번 버전: MFDS 게시판이 자체 제공하는 "제목 검색" 기능을 그대로 사용한다.
  예) https://www.mfds.go.kr/brd/m_203/list.do?srchTp=0&srchWord=의료기기
사용자가 화면에서 확인해준 대로, 이 검색은 서버가 직접 필터링해서 결과를 돌려주므로
우리가 최신글을 판단할 필요 없이 "의료기기" 또는 "약전" 이 제목에 포함된 글만 정확히 받는다.

또한 board m_207(제개정고시등)처럼 첨부파일(PDF/HWPX) 링크가 목록 화면에 이미 노출되는
게시판은 상세페이지를 방문하지 않고 목록에서 바로 첨부파일을 받아 처리한다 — 훨씬 빠르다.
목록에 첨부가 없는 게시판만 상세페이지(view.do)를 방문해서 첨부를 찾는다.

법 자체가 통째로 갱신되는 「의료기기법」/「의료기기법 시행규칙」/「의료기기법 시행령」은
Gap 분석이 특히 중요하므로 SOP(★)를 항상 강제로 켠다.

※ robots.txt 우회에 대한 안내는 이전과 동일 — 사용자가 비상업적 사내 QA 모니터링 목적임을
확인하고 명시적으로 요청하여 respect_robots=False로 접근한다. 서버 부담 최소화를 위해
요청 사이에 딜레이를 둔다.
"""
import re
import sys
import os
import time

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from collectors.http_utils import fetch, fetch_binary  # noqa: E402
from collectors.file_extract import extract_text  # noqa: E402
from collectors.summarizer import summarize, guess_scope, guess_sop_flag  # noqa: E402
from collectors.diff_engine import generate_gap  # noqa: E402
from collectors.store import load_previous_snapshot, save_snapshot  # noqa: E402

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

BOARDS = {
    "법/시행령/시행규칙": "https://www.mfds.go.kr/brd/m_203/list.do",
    "고시훈령예규(전문)": "https://www.mfds.go.kr/brd/m_211/list.do",
    "게시판_212": "https://www.mfds.go.kr/brd/m_212/list.do",
    "고시훈령예규": "https://www.mfds.go.kr/brd/m_215/list.do",
    "제개정고시등": "https://www.mfds.go.kr/brd/m_207/list.do",
    "입법/행정예고": "https://www.mfds.go.kr/brd/m_209/list.do",
    "법률 제개정 현황": "https://www.mfds.go.kr/brd/m_1087/list.do",
}

# 제목에 이 키워드가 포함된 경우만 수집 대상으로 삼는다 (서버 검색 + 클라이언트 재확인 이중 체크)
TITLE_KEYWORDS = ["의료기기", "약전"]

# 이 문서들은 "법 원문 자체"가 통째로 교체되는 문서라 Gap 분석 중요도가 특히 높다 → SOP 강제 ★
FULL_LAW_PATTERNS = ["의료기기법 시행규칙", "의료기기법 시행령", "「의료기기법」"]

DATE_RE = re.compile(r"(20\d{2})[.\-](\d{1,2})[.\-](\d{1,2})")
DOC_NO_RE = re.compile(r"(제\s*20\d{2}-\d+\s*호|총리령\s*제\d+호|대통령령\s*제\d+호|법률\s*제\d+호)")
ATTACHMENT_EXTS = (".pdf", ".hwpx", ".hwp")

POLITENESS_DELAY = 1.0
LIST_TIMEOUT = 10
DETAIL_TIMEOUT = 10
FILE_TIMEOUT = 15
TIME_BUDGET_SECONDS = 150


def _normalize_date(text):
    m = DATE_RE.search(text or "")
    if not m:
        return None
    y, mo, d = m.groups()
    return f"{y}-{int(mo):02d}-{int(d):02d}"


def _is_full_law(title):
    return any(p.replace("「", "").replace("」", "") in title for p in FULL_LAW_PATTERNS)


def _search_board(board_name, board_url, keyword, since_year, since_month):
    """MFDS 게시판의 제목검색 기능을 이용한다. 다른 파라미터(board_id 등)는 게시판마다
    다를 수 있어 최소 파라미터(srchTp, srchWord)만 사용한다 — 서버가 기본값을 채워주는
    것으로 가정한다(사용자가 확인해준 실제 URL 기준)."""
    url = f"{board_url}?srchTp=0&srchWord={keyword}"
    res = fetch(url, respect_robots=False, politeness_delay=POLITENESS_DELAY, timeout=LIST_TIMEOUT)
    if not res.ok:
        return [], res
    if BeautifulSoup is None:
        raise RuntimeError("beautifulsoup4 미설치")

    soup = BeautifulSoup(res.text, "html.parser")
    rows = []
    for a in soup.select('a[href*="view.do"]'):
        title = a.get_text(strip=True)
        if not title or len(title) < 4:
            continue
        if not any(kw in title for kw in TITLE_KEYWORDS):
            continue  # 클라이언트 재확인

        href = a.get("href")
        view_url = href if href.startswith("http") else board_url.rsplit("/", 1)[0] + "/" + href.lstrip("./")

        block = a.find_parent("li") or a.find_parent("tr") or a.find_parent("div") or a
        block_text = block.get_text(" ", strip=True)
        pub_date = _normalize_date(block_text)
        if pub_date:
            y, mo = int(pub_date[:4]), int(pub_date[5:7])
            if (y, mo) < (since_year, since_month):
                continue

        # 목록 화면에 이미 노출된 첨부파일 링크가 있는지 확인 (있으면 상세페이지 스킵 가능)
        attachments = []
        for att_a in block.select('a[href$=".pdf"], a[href$=".hwpx"], a[href$=".hwp"]'):
            att_href = att_a.get("href")
            if not att_href:
                continue
            att_url = att_href if att_href.startswith("http") else board_url.rsplit("/", 1)[0] + "/" + att_href.lstrip("./")
            attachments.append(att_url)

        m_no = DOC_NO_RE.search(block_text)

        rows.append({
            "board": board_name,
            "title": title,
            "view_url": view_url,
            "pub_date": pub_date,
            "attachments": attachments,
            "doc_no": m_no.group(1) if m_no else None,
        })
    return rows, None


def _fetch_attachment_text(urls):
    for u in urls:
        content = fetch_binary(u, respect_robots=False, politeness_delay=POLITENESS_DELAY, timeout=FILE_TIMEOUT)
        if not content:
            continue
        filename = u.rsplit("/", 1)[-1]
        text, status = extract_text(content, filename)
        if text:
            return text, "OK (목록 첨부)"
    return "", "첨부 추출 실패 또는 없음"


def _fetch_detail_and_attachment(view_url):
    """목록에 첨부가 없을 때만 상세페이지를 방문한다."""
    res = fetch(view_url, respect_robots=False, politeness_delay=POLITENESS_DELAY, timeout=DETAIL_TIMEOUT)
    if not res.ok or BeautifulSoup is None:
        return "", None, (res.error if not res.ok else "beautifulsoup4 미설치")

    dsoup = BeautifulSoup(res.text, "html.parser")
    page_text = dsoup.get_text(" ", strip=True)
    m_no = DOC_NO_RE.search(page_text)

    for ext in ATTACHMENT_EXTS:
        att = dsoup.select_one(f'a[href$="{ext}"]')
        if not att:
            continue
        href = att.get("href")
        file_url = href if href.startswith("http") else view_url.rsplit("/", 1)[0] + "/" + href.lstrip("./")
        content = fetch_binary(file_url, respect_robots=False, politeness_delay=POLITENESS_DELAY, timeout=FILE_TIMEOUT)
        if content:
            text, status = extract_text(content, f"file{ext}")
            if text:
                return text, (m_no.group(1) if m_no else None), "OK (상세페이지 첨부)"

    main = dsoup.select_one("main") or dsoup.body
    fallback_text = main.get_text("\n", strip=True) if main else ""
    return fallback_text, (m_no.group(1) if m_no else None), "OK (첨부 없음 — 본문 텍스트)"


def run(since_year=2026, since_month=1, today_only=False):
    start = time.time()
    if today_only:
        from datetime import date
        since_year, since_month = date.today().year, date.today().month

    all_rows = {}
    for board_name, board_url in BOARDS.items():
        if time.time() - start > TIME_BUDGET_SECONDS:
            print("[mfds] 시간 예산 초과 — 목록 검색 단계에서 중단")
            break
        for kw in TITLE_KEYWORDS:
            rows, err = _search_board(board_name, board_url, kw, since_year, since_month)
            if err:
                print(f"[mfds] '{board_name}'({kw}) 검색 실패: {err.error}")
                continue
            for r in rows:
                all_rows[r["view_url"]] = r  # URL 기준 중복 제거

    if today_only:
        from datetime import date
        today_str = date.today().isoformat()
        all_rows = {k: v for k, v in all_rows.items() if v.get("pub_date") == today_str}

    results = []
    for c in all_rows.values():
        if time.time() - start > TIME_BUDGET_SECONDS:
            print(f"[mfds] 시간 예산 초과 — 남은 {len(all_rows) - len(results)}건 건너뜀")
            break
        try:
            if c["attachments"]:
                body_text, status = _fetch_attachment_text(c["attachments"])
                doc_no = c["doc_no"]
            else:
                body_text, doc_no_from_detail, status = _fetch_detail_and_attachment(c["view_url"])
                doc_no = c["doc_no"] or doc_no_from_detail

            doc_no = doc_no or c["board"]
            prev = load_previous_snapshot("MFDS", doc_no)
            gap = generate_gap(prev, body_text or c["title"])
            if body_text:
                save_snapshot("MFDS", doc_no, body_text)

            summary_source = body_text or c["title"]
            forced_sop = _is_full_law(c["title"])

            results.append({
                "search_month": (c["pub_date"] or "")[:7],
                "publish_date": c["pub_date"],
                "effective_date": None,
                "publisher": "MFDS (Korea)",
                "doc_no": doc_no,
                "title": c["title"],
                "summary": summarize(c["title"], summary_source) + (
                    "" if body_text else f"\n\n(원문 확보 실패: {status})") + (
                    "\n\n⚠ 법 원문 전체가 교체되는 문서입니다 — 아래 Gap 분석을 반드시 확인하세요."
                    if forced_sop else ""
                ),
                "scope": guess_scope(c["title"] + " " + summary_source),
                "sop_required": "★" if (forced_sop or guess_sop_flag(c["title"] + " " + summary_source)) else "",
                "url": c["view_url"],
                "gap_analysis": gap,
            })
        except Exception as e:
            print(f"[mfds] 후보 처리 중 오류(건너뜀): {c.get('title')} — {e}")
            continue

    return results, None


if __name__ == "__main__":
    found, block = run(today_only=True)
    print(f"오늘자 수집 {len(found)}건")
    for f in found:
        print(" -", f["title"], f["url"])
