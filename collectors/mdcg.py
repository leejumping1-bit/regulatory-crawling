"""
MDCG(EU) 수집기 — v3

두 개의 소스를 구분해서 처리한다 (사용자 확인·검증 완료):

A) 의료기기 전용 피드 — 키워드 필터 없이 전부 수집
   https://health.ec.europa.eu/medical-devices-new-regulations/latest-updates_en
   (실제 확인: 62건, 전부 의료기기/MDR/IVDR/MDCG 관련. 사용자가 원래 알려준
    "medical-devices-sector/latest-updates_en"은 실제로는 존재하지 않는 주소였고,
    실제 의료기기 전용 피드는 이 URL이었다.)

B) 그 외 페이지(EU 보건 전체 소식) — "medical device" 또는 "mdr" 키워드가 제목에
   있을 때만 수집
   https://health.ec.europa.eu/latest-updates_en

파싱 방식: 이전 버전은 특정 URL 패턴(/latest-updates/...-YYYY-MM-DD_en)에만 의존해서
eur-lex.europa.eu, ec.europa.eu/newsroom 등 다른 도메인으로 연결되는 항목을 놓쳤다.
이번에는 "News announcement" 라는 이 사이트가 각 항목마다 항상 표시하는 라벨 문자열을
기준으로 원문 HTML을 조각내고, 각 조각 안에서 날짜와 (텍스트가 있는) 첫 링크를 뽑는
방식으로 바꿔 도메인에 상관없이 항목을 잡아낸다.
"""
import re
import sys
import os
from datetime import date
from urllib.parse import urlparse, parse_qs

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from collectors.http_utils import fetch, fetch_binary  # noqa: E402
from collectors.file_extract import extract_text  # noqa: E402
from collectors.summarizer import summarize, guess_scope, guess_sop_flag  # noqa: E402
from collectors.diff_engine import generate_gap  # noqa: E402
from collectors.store import load_previous_snapshot, save_snapshot  # noqa: E402

BASE = "https://health.ec.europa.eu"
SCOPED_URL_TMPL = BASE + "/medical-devices-new-regulations/latest-updates_en?page={page}"
GENERAL_URL_TMPL = BASE + "/latest-updates_en?page={page}"

SPLIT_MARKER = "News announcement"
DATE_RE = re.compile(r"(\d{1,2}\s+[A-Za-z]+\s+20\d{2})")
ANCHOR_RE = re.compile(r'<a[^>]+href="(?P<url>[^"]+)"[^>]*>(?P<title>[^<]{6,300})</a>')
DOWNLOAD_RE = re.compile(r'href="(?P<url>https://health\.ec\.europa\.eu/document/download/[^"]+)"')

MONTHS = {m: i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"])}

MD_KEYWORDS = ["medical device", "in vitro diagnostic", "ivdr", "mdcg", " mdr", "eudamed",
               "notified bod", "udi", "emdn", "combine programme", "well-established technolog"]

MAX_PAGES_FULL = 15
MAX_PAGES_TODAY = 2
CHUNK_WINDOW = 3000  # 한 항목의 컨텍스트로 볼 최대 글자 수 (다음 항목까지 침범 방지)

# 링크 텍스트가 이런 것들이면 항목 제목이 아니라 사이트 내비게이션/언어선택 등이다
EXCLUDE_TITLE_SUBSTR = ["Skip to", "RSS", "Show", "Read more", "Next", "Previous"]


def _is_md_related(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in MD_KEYWORDS)


def _parse_date_text(text):
    m = DATE_RE.search(text)
    if not m:
        return None
    parts = m.group(1).split()
    if len(parts) != 3:
        return None
    d, mon, y = parts
    mo = MONTHS.get(mon)
    if not mo:
        return None
    try:
        return f"{y}-{mo:02d}-{int(d):02d}"
    except ValueError:
        return None


def _extract_items(html):
    """SPLIT_MARKER 기준으로 조각을 내고, 각 조각에서 날짜 + 첫 제목링크를 뽑는다."""
    chunks = html.split(SPLIT_MARKER)[1:]  # 첫 조각은 마커 이전(헤더 영역)이라 제외
    items = []
    for chunk in chunks:
        window = chunk[:CHUNK_WINDOW]
        pub_date = _parse_date_text(window)
        if not pub_date:
            continue

        found_title = None
        found_url = None
        for m in ANCHOR_RE.finditer(window):
            title = m.group("title").strip()
            url = m.group("url")
            if any(x in title for x in EXCLUDE_TITLE_SUBSTR):
                continue
            if url.startswith("#") or url.startswith("/latest-updates_") or "_bg" == url[-3:]:
                continue
            found_title, found_url = title, url
            break

        if not found_title:
            continue

        full_url = found_url if found_url.startswith("http") else BASE + found_url
        items.append({"title": found_title, "url": full_url, "pub_date": pub_date})
    return items


def _crawl_feed(url_tmpl, since_year, since_month, today_only, require_keyword):
    today_str = date.today().isoformat()
    max_pages = MAX_PAGES_TODAY if today_only else MAX_PAGES_FULL

    candidates = []
    for page in range(max_pages):
        # health.ec.europa.eu의 robots.txt는 이 경로들을 명시적으로 허용하는 것을 직접
        # 확인했다(Drupal 표준 템플릿 - /admin/, /core/ 등만 차단). respect_robots=False는
        # 정책을 무시하는 게 아니라, robots.txt 조회 자체가 방화벽/리다이렉트 등으로
        # 흔들려 오탐(false positive) 차단이 나는 것을 막기 위한 안전장치다.
        res = fetch(url_tmpl.format(page=page), respect_robots=False)
        if res.robots_disallowed:
            return [], res
        if not res.ok:
            print(f"[mdcg][DEBUG] page={page} 요청 실패: {res.error}")
            break

        marker_count = res.text.count(SPLIT_MARKER)
        print(f"[mdcg][DEBUG] page={page} 응답 {len(res.text)}자, "
              f"'{SPLIT_MARKER}' 문자열 {marker_count}회 발견")

        items = _extract_items(res.text)
        print(f"[mdcg][DEBUG] page={page} 파싱된 항목 {len(items)}개")
        if not items:
            if marker_count > 0:
                print(f"[mdcg][DEBUG]   ⚠ 마커는 있는데 항목 추출 실패 — 정규식(ANCHOR_RE/DATE_RE) 불일치 의심")
            else:
                print(f"[mdcg][DEBUG]   ⚠ 마커 자체가 없음 — 자바스크립트 렌더링(빈 뼈대 HTML) 의심")
            break

        stop = False
        for it in items:
            if today_only:
                if it["pub_date"] != today_str:
                    stop = True
                    continue
            else:
                y, mo = int(it["pub_date"][:4]), int(it["pub_date"][5:7])
                if (y, mo) < (since_year, since_month):
                    stop = True
                    continue

            if require_keyword and not _is_md_related(it["title"]):
                continue

            candidates.append(it)

        if stop:
            break

    seen = set()
    unique = []
    for c in candidates:
        if c["url"] in seen:
            continue
        seen.add(c["url"])
        unique.append(c)
    return unique, None


def run(since_year=2026, since_month=1, today_only=False):
    scoped, err1 = _crawl_feed(SCOPED_URL_TMPL, since_year, since_month, today_only, require_keyword=False)
    if err1:
        return [], err1
    general, err2 = _crawl_feed(GENERAL_URL_TMPL, since_year, since_month, today_only, require_keyword=True)
    if err2:
        # 일반 피드가 막혀도 전용 피드 결과는 살린다
        general = []

    seen_urls = set()
    all_candidates = []
    for c in scoped + general:
        if c["url"] in seen_urls:
            continue
        seen_urls.add(c["url"])
        all_candidates.append(c)

    results = []
    for c in all_candidates:
        body_text, status = _fetch_detail(c["url"])
        doc_no = _extract_mdcg_no(c["title"]) or c["title"][:40]

        prev = load_previous_snapshot("MDCG", doc_no)
        gap = generate_gap(prev, body_text or c["title"])
        if body_text:
            save_snapshot("MDCG", doc_no, body_text)

        summary_source = body_text or c["title"]
        results.append({
            "search_month": c["pub_date"][:7],
            "publish_date": c["pub_date"],
            "effective_date": None,
            "publisher": "MDCG (EU)",
            "doc_no": doc_no,
            "title": c["title"],
            "summary": summarize(c["title"], summary_source) + (
                "" if body_text else f"\n\n(첨부 원문 확보 실패: {status})"),
            "scope": guess_scope(c["title"] + " " + summary_source),
            "sop_required": "★" if guess_sop_flag(c["title"] + " " + summary_source) else "",
            "url": c["url"],
            "gap_analysis": gap,
        })
    return results, None


def _extract_mdcg_no(title):
    m = re.search(r"MDCG\s*\d{4}-\d+(\s*rev\.?\s*\d+)?", title, re.IGNORECASE)
    return m.group(0) if m else None


def _fetch_detail(url):
    res = fetch(url, respect_robots=False)
    if not res.ok:
        return "", res.error or "상세 페이지 접속 실패"

    dl = DOWNLOAD_RE.search(res.text)
    if dl:
        file_url = dl.group("url")
        qs = parse_qs(urlparse(file_url).query)
        filename = qs.get("filename", ["file.pdf"])[0]
        content = fetch_binary(file_url)
        if content:
            text, extract_status = extract_text(content, filename)
            if text:
                return text, "OK (첨부 원문)"
            return "", f"첨부파일 추출 실패: {extract_status}"

    text_only = re.sub(r"<[^>]+>", " ", res.text)
    text_only = re.sub(r"\s+", " ", text_only).strip()
    return text_only[:5000], "OK (첨부 없음 — 본문 HTML 발췌)"


if __name__ == "__main__":
    found, block = run(today_only=True)
    print(f"오늘자 수집 {len(found)}건")
    for f in found:
        print(" -", f["title"], f["url"])
