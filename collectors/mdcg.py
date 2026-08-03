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
from urllib.parse import urlparse, parse_qs, urljoin

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from collectors.http_utils import fetch, fetch_binary  # noqa: E402
from collectors.file_extract import extract_text  # noqa: E402
from collectors.summarizer import summarize, guess_scope, guess_manufacturer_obligation  # noqa: E402
from collectors.diff_engine import generate_document_gap  # noqa: E402
from collectors.store import load_previous_snapshot, save_snapshot  # noqa: E402

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

BASE = "https://health.ec.europa.eu"
SCOPED_URL_TMPL = BASE + "/medical-devices-new-regulations/latest-updates_en?page={page}"
GENERAL_URL_TMPL = BASE + "/latest-updates_en?page={page}"
ENDORSED_URL = BASE + "/medical-devices-sector/new-regulations/guidance-mdcg-endorsed-documents-and-other-guidance_en"

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


def _extract_endorsed_items(html, since_year, since_month):
    """공식 MDCG endorsed-documents 표에서 번호 문서와 첨부 행을 추출한다."""
    if BeautifulSoup is None:
        return []
    soup = BeautifulSoup(html or "", "html.parser")
    items = []
    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue
        reference = cells[0].get_text(" ", strip=True)
        if not re.match(r"^MDCG\s+\d{4}-\d+", reference, re.IGNORECASE):
            continue
        publication = cells[2].get_text(" ", strip=True)
        match = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})", publication, re.IGNORECASE)
        if not match:
            continue
        month = MONTHS[match.group(1).capitalize()]
        year = int(match.group(2))
        if (year, month) < (since_year, since_month):
            continue
        link = cells[0].find("a", href=True)
        if not link:
            continue
        anchor = re.sub(r"[^a-z0-9]+", "-", reference.lower()).strip("-")
        body_title = cells[1].get_text(" ", strip=True)
        is_revision = bool(re.search(r"\brev\.?\s*\d+\b|revision|revised", reference, re.IGNORECASE))
        if not is_revision:
            body_title = re.sub(r"^Position Paper:\s*", "", body_title, flags=re.IGNORECASE)
        title = f"{reference}: {body_title}" if is_revision else f"New {reference} Position Paper: {body_title}"
        items.append({
            "title": title,
            "url": f"{ENDORSED_URL}#{anchor}",
            # The endorsed table exposes only "July 2026", not a day.
            # Never invent the first day of the month.
            "pub_date": f"{year:04d}-{month:02d}",
        })
    return items


def _crawl_endorsed_index(since_year, since_month):
    """최신 소식 피드에 없는 MDCG 번호 문서도 공식 목록에서 보완한다."""
    res = fetch(ENDORSED_URL, respect_robots=False)
    if not res.ok:
        print(f"[mdcg][DEBUG] endorsed 문서 목록 요청 실패: {res.error}")
        return []
    items = _extract_endorsed_items(res.text, since_year, since_month)
    print(f"[mdcg][DEBUG] endorsed 문서 목록에서 {len(items)}건 보완")
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

    endorsed = [] if today_only else _crawl_endorsed_index(since_year, since_month)
    seen_urls = set()
    seen_doc_numbers = set()
    seen_identities = {}
    all_candidates = []
    # 같은 문서가 뉴스 피드와 endorsed 표에 모두 있을 수 있다. 문서번호가
    # 뉴스 제목에 빠지는 경우가 있으므로 번호만으로 중복 제거하지 않는다.
    for c in endorsed + scoped + general:
        doc_no = _extract_mdcg_no(c["title"])
        if c["url"] in seen_urls:
            continue
        seen_urls.add(c["url"])
        if doc_no:
            if doc_no in seen_doc_numbers:
                continue
            seen_doc_numbers.add(doc_no)
        identity = _document_identity(c["title"])
        existing = seen_identities.get(identity)
        if existing is None:
            seen_identities[identity] = c
            all_candidates.append(c)
            continue

        # Prefer the candidate carrying the official document number/title,
        # but retain an exact news-feed day when the catalogue only has YYYY-MM.
        if doc_no and not _extract_mdcg_no(existing["title"]):
            existing["title"] = c["title"]
            existing["url"] = c["url"]
        if len(c.get("pub_date", "")) > len(existing.get("pub_date", "")):
            existing["pub_date"] = c["pub_date"]

    results = []
    for c in all_candidates:
        body_text, status = _fetch_detail(c["url"], c["title"])
        doc_no = _extract_mdcg_no(c["title"]) or c["title"][:40]

        prev = load_previous_snapshot("MDCG", doc_no)
        gap = generate_document_gap(
            prev,
            body_text or c["title"],
            title=c["title"],
            publisher="MDCG (EU)",
        )
        if body_text:
            save_snapshot("MDCG", doc_no, body_text)

        summary_source = body_text
        if body_text:
            summary = summarize(c["title"], body_text)
            summary_status = "pdf_extracted"
        else:
            summary = f"[요약 오류] PDF 원문을 확보·추출하지 못해 요약을 생성하지 않았습니다. ({status})"
            summary_status = "pdf_unavailable"
        results.append({
            "search_month": c["pub_date"][:7],
            "publish_date": c["pub_date"],
            "effective_date": None,
            "publisher": "MDCG (EU)",
            "doc_no": doc_no,
            "title": c["title"],
            "summary": summary,
            "summary_status": summary_status,
            "scope": guess_scope(c["title"] + " " + summary_source, title=c["title"], publisher="MDCG (EU)"),
            "manufacturer_obligation": "★" if body_text and guess_manufacturer_obligation(c["title"], body_text) else "",
            "url": c["url"],
            "gap_analysis": gap,
        })
    return results, None


def _extract_mdcg_no(title):
    m = re.search(r"MDCG\s*\d{4}-\d+(\s*rev\.?\s*\d+)?", title, re.IGNORECASE)
    return m.group(0) if m else None


def _fetch_detail(url, title=None):
    res = fetch(url, respect_robots=False)
    if not res.ok:
        return "", res.error or "상세 페이지 접속 실패"

    # 목록/모음 페이지에는 여러 문서의 PDF 링크가 함께 있다. 제목과 같은
    # 행의 첨부만 선택하고, 일치하지 않으면 다른 문서를 fallback으로 쓰지 않는다.
    if not _is_specific_detail_url(url):
        file_url = _find_matching_attachment(res.text, title or "", url)
        if not file_url:
            return "", "PDF 첨부파일을 찾지 못함"
        content = fetch_binary(file_url)
        if content:
            filename = parse_qs(urlparse(file_url).query).get("filename", ["file.pdf"])[0]
            text, extract_status = extract_text(content, filename)
            if text:
                return text, "OK (제목 일치 행의 첨부 원문)"
            return "", f"일치 첨부파일 추출 실패: {extract_status}"
        return "", "일치 첨부파일 다운로드 실패"

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

    return "", "PDF 첨부파일을 찾지 못함"


def _is_specific_detail_url(url):
    """문서 하나를 가리키는 URL인지 확인한다.

    MDCG 목록에는 외부 법령·뉴스·이벤트 URL도 섞여 있으므로 도메인/경로를
    과도하게 제한하지 않는다. 대신 여러 문서의 첨부가 함께 있는 known
    collection page만 차단해 제목과 무관한 첫 PDF를 집지 않도록 한다.
    """
    parsed = urlparse(url or "")
    path = parsed.path.lower()
    if parsed.scheme != "https" or not parsed.netloc:
        return False
    return not (
        parsed.netloc == "health.ec.europa.eu"
        and path.endswith("/medical-devices-sector/new-regulations/guidance-mdcg-endorsed-documents-and-other-guidance_en")
    )


def _normalize_title(text):
    value = re.sub(r"^new\s+", "", text or "", flags=re.I)
    value = re.sub(r"\bMDCG\s*\d{4}-\d+(?:\s*rev.?\s*\d+)?\b", "", value, flags=re.I)
    value = re.sub(r"\bMDCG\b", "", value, flags=re.I)
    return re.sub(r"[^a-z0-9가-힣]+", " ", value.lower()).strip()

def _document_identity(title):
    """Stable identity for the same MDCG document across feed/catalog titles."""
    return _normalize_title(title)


def _find_matching_attachment(html, title, page_url):
    """모음 페이지에서 전달된 제목과 같은 표 행의 첨부 URL만 반환한다."""
    if BeautifulSoup is None:
        return None
    soup = BeautifulSoup(html or "", "html.parser")
    target = _normalize_title(title)
    fragment = urlparse(page_url or "").fragment
    root = soup.find(id=fragment) if fragment else None
    rows = []
    if root:
        table = root.find_next("table")
        if table:
            rows.extend(table.find_all("tr"))
    if not rows:
        rows = soup.find_all("tr")

    for row in rows:
        row_text = _normalize_title(row.get_text(" ", strip=True))
        if not target or target not in row_text:
            continue
        link = row.find("a", href=re.compile(r"/document/download/"))
        if link and link.get("href"):
            return urljoin(page_url, link["href"])
    return None


def _visible_detail_text(html):
    """상세 HTML에서 사용자에게 보이는 본문만 추출한다."""
    if BeautifulSoup is not None:
        soup = BeautifulSoup(html or "", "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "nav", "header", "footer"]):
            tag.decompose()
        main = soup.find("main") or soup.find("article") or soup.body or soup
        return re.sub(r"\s+", " ", main.get_text(" ", strip=True)).strip()

    text_only = re.sub(r"<(script|style|noscript|svg|nav|header|footer)[^>]*>.*?</\1>", " ", html or "", flags=re.I | re.S)
    text_only = re.sub(r"<[^>]+>", " ", text_only)
    return re.sub(r"\s+", " ", text_only).strip()


if __name__ == "__main__":
    found, block = run(today_only=True)
    print(f"오늘자 수집 {len(found)}건")
    for f in found:
        print(" -", f["title"], f["url"])
