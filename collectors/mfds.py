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
import html
import re
import sys
import os
import time
from urllib.parse import urlencode, urljoin, urlparse

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from collectors.http_utils import fetch, fetch_binary  # noqa: E402
from collectors.file_extract import extract_text  # noqa: E402
from collectors.summarizer import summarize, guess_scope, guess_manufacturer_obligation  # noqa: E402
from collectors.diff_engine import generate_gap  # noqa: E402
from collectors.store import load_previous_snapshot, save_snapshot  # noqa: E402

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

BOARDS = {
    "법/시행령/시행규칙": "https://www.mfds.go.kr/brd/m_203/list.do",
    "고시훈령예규(고시전문)": "https://www.mfds.go.kr/brd/m_211/list.do",
    "제개정고시등": "https://www.mfds.go.kr/brd/m_207/list.do",
}

BOARD_KEYWORDS = {
    "법/시행령/시행규칙": ["의료기기", "약전"],
    "고시훈령예규(고시전문)": ["의료기기", "약전"],
    "제개정고시등": ["의료기기", "약전"],
}

BOARD_QUERY_PARAMS = {
    "법/시행령/시행규칙": {"data_stts_gubun": "C1004"},
    "고시훈령예규(고시전문)": {},
    "제개정고시등": {},
}

# 제목에 이 키워드가 포함된 경우만 수집 대상으로 삼는다 (서버 검색 + 클라이언트 재확인 이중 체크)
TITLE_KEYWORDS = ["의료기기", "약전"]

# 이 문서들은 "법 원문 자체"가 통째로 교체되는 문서라 Gap 분석 중요도가 특히 높다 → SOP 강제 ★
FULL_LAW_PATTERNS = ["의료기기법 시행규칙", "의료기기법 시행령", "「의료기기법」"]
AMENDMENT_PATTERNS = (
    "일부개정", "전부개정", "개정령", "개정고시", "개정안", "개정 공포",
    "개정내용", "개정 내용", "amended", "amendment", "revision",
)

DATE_RE = re.compile(r"(20\d{2})[.\-](\d{1,2})[.\-](\d{1,2})")
DOC_NO_RE = re.compile(r"(제\s*20\d{2}-\d+\s*호|총리령\s*제\d+호|대통령령\s*제\d+호|법률\s*제\d+호)")
ATTACHMENT_EXTS = (".pdf", ".hwpx", ".hwp")
ALLOWED_HOSTS = {"mfds.go.kr", "www.mfds.go.kr", "law.go.kr", "www.law.go.kr"}

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


def _safe_url(base_url, href):
    """MFDS가 공식적으로 연결하는 HTTPS 상세/첨부 호스트만 허용한다."""
    candidate = urljoin(base_url, href or "")
    parsed = urlparse(candidate)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        return None
    return candidate


def _is_attachment_href(href):
    path = urlparse(href or "").path.lower()
    return path.endswith(ATTACHMENT_EXTS) or path.endswith("/down.do") or "/down.do/" in path


def _attachment_filenames(content):
    """MFDS download.do 응답의 실제 포맷을 바이트 시그니처로 추정한다."""
    if content.startswith(b"%PDF"):
        return ["attachment.pdf"]
    if content.startswith(b"PK\x03\x04"):
        return ["attachment.hwpx", "attachment.docx"]
    return ["attachment.hwp"]


def _visible_detail_text(html):
    """MFDS 상세 페이지에서 게시글 본문만 추출한다."""
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "header", "footer"]):
        tag.decompose()
    content = soup.select_one(".bv_cont") or soup.select_one("main") or soup.body or soup
    return content.get_text("\n", strip=True)


def _has_major_content(text):
    normalized = re.sub(r"\s+", "", text or "")
    return "주요내용" in normalized or "주요사항" in normalized


def _is_amendment_notice(title, text=""):
    haystack = f"{title or ''}\n{text or ''}".lower()
    return any(pattern.lower() in haystack for pattern in AMENDMENT_PATTERNS)


def _extract_amendment_sections(text):
    """MFDS 개정 공고에서 Gap에 표시할 변경 설명만 추출한다.

    과거 전문을 확보하지 못한 경우에도 현재 법령 전문 전체를 반복 표시하지
    않도록, 공고의 개정 이유·주요 내용·신구조문대비표 등 변경 관련 절만 남긴다.
    """
    source = re.sub(r"\s+", " ", text or "").strip()
    if not source:
        return ""
    labels = (
        "개정이유", "개정 이유", "주요내용", "주요 내용", "주요사항",
        "신구조문대비표", "신·구조문대비표", "신구조문 대비표", "개정문",
    )
    label_re = re.compile("|".join(re.escape(label) for label in labels), re.IGNORECASE)
    matches = list(label_re.finditer(source))
    sections = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else min(len(source), start + 3500)
        section = source[start:end].strip(" :-")
        if section and section not in sections:
            sections.append(section)
    return "\n\n".join(sections[:4])


def _build_mfds_gap(prev_text, body_text, title, publish_date):
    """MFDS 개정본의 과거 이력 부재를 안전하게 표현한다."""
    current = body_text or ""
    if prev_text and current:
        return generate_gap(prev_text, current)
    if not _is_amendment_notice(title, current):
        if current:
            return generate_gap(None, current)
        return {
            "past_text": "비교 제외 (원문 미확보)",
            "present_text": "비교 제외 (원문 미확보)",
            "diff_html": '<div class="diff-omit">원문을 확보하지 못해 Gap 분석을 수행하지 않았습니다.</div>',
        }

    changed = _extract_amendment_sections(current)
    date_label = publish_date or "개정일자 미확인"
    present = f"개정일자: {date_label}\n\n{changed}" if changed else (
        f"개정일자: {date_label}\n\n공식 개정 공고의 변경 내용을 확인하세요."
    )
    escaped = html.escape(present).replace("\n", "<br>")
    return {
        "past_text": "과거 이력 확인 실패",
        "present_text": present,
        "diff_html": (
            '<div class="diff-del">과거 이력 확인 실패</div>\n'
            f'<div class="diff-add">{escaped}</div>'
        ),
    }


def _extract_major_content(text):
    """상세 페이지의 공식 <주요내용>에서 가·나·다 항목만 추출한다."""
    source = text or ""
    marker = re.search(r"<\s*주요내용\s*>|<\s*주요사항\s*>|주요내용|주요사항", source, re.IGNORECASE)
    if not marker:
        return ""

    section = source[marker.end():]
    # 다음 꺾쇠 제목이나 별도 안내 섹션부터는 주요내용으로 보지 않는다.
    section = re.split(r"<\s*(?:참고사항|첨부|붙임|문의|향후계획|담당부서)\s*>", section, maxsplit=1, flags=re.IGNORECASE)[0]
    section = re.sub(r"\s+", " ", section).strip()
    item_re = re.compile(
        r"([가-힣])\s*\.\s*(.+?)(?=\s+[가-힣]\s*\.\s+|\Z)",
        re.IGNORECASE,
    )
    items = []
    for match in item_re.finditer(section):
        content = re.sub(r"\s+", " ", match.group(2)).strip(" -")
        if content:
            items.append(f"{match.group(1)}. {content}")
    if not items:
        return ""
    return "[주요내용]\n" + "\n".join(f"- {item}" for item in items)


def _extract_rows_from_html(html, board_name, board_url, keyword, since_year, since_month):
    soup = BeautifulSoup(html, "html.parser")
    all_links = soup.select('a[href*="view.do"], a.title[href]')
    rows = []
    seen_urls = set()
    for a in all_links:
        title = a.get_text(" ", strip=True)
        href = a.get("href")
        if not title or len(title) < 4 or not href:
            continue
        if not any(kw in title for kw in BOARD_KEYWORDS.get(board_name, [keyword])):
            continue

        view_url = _safe_url(board_url, href)
        if not view_url:
            continue
        if view_url in seen_urls:
            continue
        seen_urls.add(view_url)

        block = a.find_parent("li") or a.find_parent("tr") or a.find_parent("div") or a
        block_text = block.get_text(" ", strip=True)
        pub_date = _normalize_date(block_text)
        if pub_date:
            y, mo = int(pub_date[:4]), int(pub_date[5:7])
            if (y, mo) < (since_year, since_month):
                continue

        attachments = []
        for att_a in block.find_all("a", href=True):
            att_href = att_a.get("href")
            if not _is_attachment_href(att_href):
                continue
            att_url = _safe_url(board_url, att_href)
            if att_url:
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
    return rows


def _search_board(board_name, board_url, keyword, since_year, since_month):
    """MFDS 게시판의 제목검색 기능을 이용한다. 다른 파라미터(board_id 등)는 게시판마다
    다를 수 있어 최소 파라미터(srchTp, srchWord)만 사용한다 — 서버가 기본값을 채워주는
    것으로 가정한다(사용자가 확인해준 실제 URL 기준)."""
    query = {"srchTp": "0", "srchWord": keyword}
    query.update(BOARD_QUERY_PARAMS.get(board_name, {}))
    url = f"{board_url}?{urlencode(query)}"
    res = fetch(
        url,
        respect_robots=False,
        politeness_delay=POLITENESS_DELAY,
        timeout=LIST_TIMEOUT,
        allowed_hosts=ALLOWED_HOSTS,
    )
    if not res.ok:
        print(f"[mfds][DEBUG] '{board_name}'({keyword}) 요청 실패: {res.error}")
        return [], res
    if BeautifulSoup is None:
        raise RuntimeError("beautifulsoup4 미설치")

    soup = BeautifulSoup(res.text, "html.parser")
    all_view_links = soup.select('a[href*="view.do"], a.title[href]')
    print(f"[mfds][DEBUG] '{board_name}'({keyword}) 응답 {len(res.text)}자, "
          f"view.do 링크 {len(all_view_links)}개 발견")
    if all_view_links:
        sample_titles = [a.get_text(strip=True)[:30] for a in all_view_links[:3]]
        print(f"[mfds][DEBUG]   샘플 제목: {sample_titles}")

    rows = _extract_rows_from_html(
        res.text, board_name, board_url, keyword, since_year, since_month
    )
    return rows, None


def _fetch_attachment_text(urls):
    for u in urls:
        content = fetch_binary(u, respect_robots=False, politeness_delay=POLITENESS_DELAY, timeout=FILE_TIMEOUT)
        if not content:
            continue
        for filename in _attachment_filenames(content):
            text, status = extract_text(content, filename)
            if text:
                return text, f"OK (목록 첨부: {filename})"
    return "", "첨부 추출 실패 또는 없음"


def _fetch_detail_and_attachment(view_url):
    """목록에 첨부가 없을 때만 상세페이지를 방문한다."""
    res = fetch(
        view_url,
        respect_robots=False,
        politeness_delay=POLITENESS_DELAY,
        timeout=DETAIL_TIMEOUT,
        allowed_hosts=ALLOWED_HOSTS,
    )
    if not res.ok or BeautifulSoup is None:
        return "", None, (res.error if not res.ok else "beautifulsoup4 미설치")

    dsoup = BeautifulSoup(res.text, "html.parser")
    page_text = _visible_detail_text(res.text)
    m_no = DOC_NO_RE.search(page_text)

    # 제개정고시등(m_207)은 본문에 식약처가 정리한 <주요내용>이 있으므로
    # 전문 PDF보다 사람이 읽기 쉬운 공식 요약 본문을 우선 사용한다.
    if _has_major_content(page_text) and "/m_207/" in view_url:
        major_content = _extract_major_content(page_text)
        if major_content:
            return major_content, (m_no.group(1) if m_no else None), "OK (본문 주요내용 항목)"

    for att in dsoup.find_all("a", href=True):
        href = att.get("href")
        if not _is_attachment_href(href):
            continue
        file_url = _safe_url(view_url, href)
        if not file_url:
            continue
        content = fetch_binary(
            file_url,
            respect_robots=False,
            politeness_delay=POLITENESS_DELAY,
            timeout=FILE_TIMEOUT,
            allowed_hosts=ALLOWED_HOSTS,
        )
        if content:
            for filename in _attachment_filenames(content):
                text, status = extract_text(content, filename)
                if text:
                    return text, (m_no.group(1) if m_no else None), f"OK (상세페이지 첨부: {filename})"

    return page_text, (m_no.group(1) if m_no else None), "OK (첨부 없음 — 본문 텍스트)"


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
        for kw in BOARD_KEYWORDS.get(board_name, TITLE_KEYWORDS):
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
            # m_207은 PDF보다 상세 페이지의 공식 <주요내용>(가·나·다)을 우선한다.
            if c["board"] == "제개정고시등":
                body_text, doc_no_from_detail, status = _fetch_detail_and_attachment(c["view_url"])
                doc_no = c["doc_no"] or doc_no_from_detail
            elif c["attachments"]:
                body_text, status = _fetch_attachment_text(c["attachments"])
                doc_no = c["doc_no"]
            else:
                body_text, doc_no_from_detail, status = _fetch_detail_and_attachment(c["view_url"])
                doc_no = c["doc_no"] or doc_no_from_detail

            doc_no = doc_no or c["board"]
            prev = load_previous_snapshot("MFDS", doc_no)
            gap = _build_mfds_gap(prev, body_text, c["title"], c["pub_date"])
            if body_text:
                save_snapshot("MFDS", doc_no, body_text)

            summary_source = body_text or c["title"]
            full_law = _is_full_law(c["title"])

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
                    if full_law else ""
                ),
                "scope": guess_scope(c["title"] + " " + summary_source, title=c["title"], publisher="MFDS (Korea)"),
                "manufacturer_obligation": "★" if guess_manufacturer_obligation(c["title"], summary_source) else "",
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
