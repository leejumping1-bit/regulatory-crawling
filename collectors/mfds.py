"""
MFDS(식품의약품안전처) 자동 수집기

※ 참고: mfds.go.kr 은 robots.txt로 자동화된 접근을 비권장(Disallow)하고 있습니다.
사용자가 개인/사내 QA 모니터링 목적(비상업적 이용)임을 확인하고, 이 신호를 의도적으로
우회하도록 요청하여 respect_robots=False 로 접근합니다. 서버 부담을 최소화하기 위해
요청 사이에 politeness_delay를 두고, 게시판당 최신 게시물 소수만 확인합니다.
IP 차단·CAPTCHA 등 '기술적' 차단이 걸리는 경우는 우회하지 않고 실패로 처리합니다.

※ 시간 예산: Streamlit Cloud 등 호스팅 플랫폼은 너무 오래 걸리는 요청을 강제
종료시킬 수 있다. 이를 대비해 전체 처리 시간이 TIME_BUDGET_SECONDS를 넘으면
남은 후보는 건너뛰고 그때까지 모은 결과만 반환한다(부분 결과라도 유실 방지).
"""
import re
import sys
import os
import time

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from collectors.http_utils import fetch, fetch_binary  # noqa: E402
from collectors.file_extract import extract_text  # noqa: E402
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
POLITENESS_DELAY = 1.0       # 초 — 서버 부담 최소화
MAX_ROWS_PER_BOARD = 5       # 게시판당 최신 N건만 (기존 10 → 5)
MAX_TOTAL_CANDIDATES = 20    # 상세페이지까지 확인할 전체 후보 상한
TIME_BUDGET_SECONDS = 150    # 이 함수 전체가 넘지 않도록 하는 시간 예산 (약 2.5분)
LIST_TIMEOUT = 10
DETAIL_TIMEOUT = 10
FILE_TIMEOUT = 15


def _normalize_date(text):
    m = DATE_RE.search(text or "")
    if not m:
        return None
    y, mo, d = m.groups()
    return f"{y}-{int(mo):02d}-{int(d):02d}"


def _crawl_board(board_name, board_url, since_year, since_month, max_rows=MAX_ROWS_PER_BOARD):
    res = fetch(board_url, respect_robots=False, politeness_delay=POLITENESS_DELAY, timeout=LIST_TIMEOUT)
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


def _process_candidate(c):
    """실패해도 예외를 밖으로 던지지 않고 None을 반환 — 후보 하나의 오류가
    이미 처리된 다른 후보들의 결과까지 날려버리지 않도록 한다."""
    try:
        detail_res = fetch(c["url"], respect_robots=False,
                            politeness_delay=POLITENESS_DELAY, timeout=DETAIL_TIMEOUT)
        detail_text = ""
        doc_no = None

        if detail_res.ok and BeautifulSoup is not None:
            dsoup = BeautifulSoup(detail_res.text, "html.parser")
            page_text = dsoup.get_text(" ", strip=True)

            m_no = re.search(r"(제\s*\d{4}-\d+\s*호|총리령\s*제\d+호|법률\s*제\d+호)", page_text)
            doc_no = m_no.group(1) if m_no else None

            if not c.get("pub_date"):
                m_dates = DATE_RE.findall(page_text)
                if m_dates:
                    y, mo, d = m_dates[0]
                    c["pub_date"] = f"{y}-{int(mo):02d}-{int(d):02d}"

            for ext in (".pdf", ".hwpx", ".docx"):
                att = dsoup.select_one(f'a[href$="{ext}"]')
                if not att:
                    continue
                href = att.get("href")
                file_url = href if href.startswith("http") else c["url"].rsplit("/", 1)[0] + "/" + href.lstrip("./")
                content = fetch_binary(file_url, respect_robots=False,
                                        politeness_delay=POLITENESS_DELAY, timeout=FILE_TIMEOUT)
                if content:
                    text, status = extract_text(content, f"file{ext}")
                    if text:
                        detail_text = text
                        break

            if not detail_text:
                main = dsoup.select_one("main") or dsoup.body
                detail_text = main.get_text("\n", strip=True) if main else ""

        combined_text = f"{c['title']} {detail_text}"
        if "의료기기" not in combined_text and not is_medical_device_related(combined_text):
            return None

        return build_item(
            agency_label="MFDS (Korea)",
            title=c["title"],
            url=c["url"],
            pub_date=c.get("pub_date"),
            effective_date=None,
            doc_no=doc_no or c["board"],
            prefetched_text=detail_text,
        )
    except Exception as e:
        print(f"[mfds] 후보 처리 중 오류(건너뜀): {c.get('title')} — {e}")
        return None


def run(since_year=2026, since_month=1):
    start = time.time()
    all_candidates = []

    for name, url in BOARDS.items():
        if time.time() - start > TIME_BUDGET_SECONDS:
            print(f"[mfds] 시간 예산 초과로 남은 게시판 건너뜀 (목록 수집 단계)")
            break
        rows, err = _crawl_board(name, url, since_year, since_month)
        if err:
            print(f"[mfds] '{name}' 게시판 접속 실패: {err.error}")
            continue
        all_candidates.extend(rows)

    all_candidates = all_candidates[:MAX_TOTAL_CANDIDATES]

    results = []
    for c in all_candidates:
        if time.time() - start > TIME_BUDGET_SECONDS:
            print(f"[mfds] 시간 예산 초과로 남은 {len(all_candidates) - len(results)}건 건너뜀 "
                  f"(지금까지 {len(results)}건은 보존됨)")
            break
        item = _process_candidate(c)
        if item:
            results.append(item)

    return results, None


if __name__ == "__main__":
    found, block = run()
    print(f"수집 {len(found)}건")
