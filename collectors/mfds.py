"""
MFDS(식품의약품안전처) 자동 수집기

※ 참고: mfds.go.kr 은 robots.txt로 자동화된 접근을 비권장(Disallow)하고 있습니다.
사용자가 개인/사내 QA 모니터링 목적(비상업적 이용)임을 확인하고, 이 신호를 의도적으로
우회하도록 요청하여 respect_robots=False 로 접근합니다. 서버 부담을 최소화하기 위해
요청 사이에 politeness_delay(기본 1.5초)를 두고, 페이지당 최신 게시물 소수만 확인합니다.
IP 차단·CAPTCHA 등 '기술적' 차단이 걸리는 경우는 우회하지 않고 실패로 처리합니다.
"""
import re
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from collectors.http_utils import fetch  # noqa: E402
from collectors.pipeline import build_item, is_medical_device_related  # noqa: E402

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

DATE_RE = re.compile(r"(20\d{2})[.\-](\d{1,2})[.\-](\d{1,2})")
POLITENESS_DELAY = 1.5  # 초 — 서버 부담 최소화


def _normalize_date(text):
    m = DATE_RE.search(text or "")
    if not m:
        return None
    y, mo, d = m.groups()
    return f"{y}-{int(mo):02d}-{int(d):02d}"


def _crawl_board(board_name, board_url, since_year, since_month, max_rows=10):
    res = fetch(board_url, respect_robots=False, politeness_delay=POLITENESS_DELAY)
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
        href = a.get("href")
        view_url = href if href.startswith("http") else board_url.rsplit("/", 1)[0] + "/" + href.lstrip("./")

        tr = a.find_parent("tr")
        row_text = tr.get_text(" ", strip=True) if tr else ""
        pub_date = _normalize_date(row_text)
        if pub_date:
            y, mo = int(pub_date[:4]), int(pub_date[5:7])
            if (y, mo) < (since_year, since_month):
                continue

        rows.append({"board": board_name, "title": title, "url": view_url, "pub_date": pub_date})
        if len(rows) >= max_rows:
            break
    return rows, None


def run(since_year=2026, since_month=1):
    all_candidates = []
    for name, url in BOARDS.items():
        rows, err = _crawl_board(name, url, since_year, since_month)
        if err:
            print(f"[mfds] '{name}' 게시판 접속 실패: {err.error}")
            continue
        all_candidates.extend(rows)

    results = []
    for c in all_candidates:
        detail_res = fetch(c["url"], respect_robots=False, politeness_delay=POLITENESS_DELAY)
        detail_text = ""
        doc_no = None
        effective_date = None
        if detail_res.ok and BeautifulSoup is not None:
            dsoup = BeautifulSoup(detail_res.text, "html.parser")
            page_text = dsoup.get_text(" ", strip=True)

            m_no = re.search(r"(제\s*\d{4}-\d+\s*호|총리령\s*제\d+호|법률\s*제\d+호)", page_text)
            doc_no = m_no.group(1) if m_no else None

            m_dates = DATE_RE.findall(page_text)
            if m_dates:
                dates_norm = [f"{y}-{int(mo):02d}-{int(d):02d}" for y, mo, d in m_dates]
                if not c["pub_date"] and dates_norm:
                    c["pub_date"] = dates_norm[0]

            for ext in (".pdf", ".hwpx", ".docx"):
                att = dsoup.select_one(f'a[href$="{ext}"]')
                if att:
                    href = att.get("href")
                    file_url = href if href.startswith("http") else c["url"].rsplit("/", 1)[0] + "/" + href.lstrip("./")
                    from collectors.http_utils import fetch_binary
                    content = fetch_binary(file_url, respect_robots=False)
                    if content:
                        from collectors.file_extract import extract_text
                        text, status = extract_text(content, f"file{ext}")
                        if text:
                            detail_text = text
                            break
            if not detail_text:
                main = dsoup.select_one("main") or dsoup.body
                detail_text = main.get_text("\n", strip=True) if main else ""

        combined_text = f"{c['title']} {detail_text}"
        if not is_medical_device_related(combined_text) and "의료기기" not in combined_text:
            continue

        item = build_item(
            agency_label="MFDS (Korea)",
            title=c["title"],
            url=c["url"],
            pub_date=c.get("pub_date"),
            effective_date=effective_date,
            doc_no=doc_no or c["board"],
            prefetched_text=detail_text,
        )
        results.append(item)

    return results, None


if __name__ == "__main__":
    found, block = run()
    print(f"수집 {len(found)}건")
