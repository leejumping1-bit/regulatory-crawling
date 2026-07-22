"""
MDCG(EU) 수집기
- 목록: https://health.ec.europa.eu/latest-updates_en (DG SANTE 전체 소식 — 의료기기 키워드로 필터링)
- 이 사이트는 robots.txt 상 접근이 허용되는 정부(EU기구) 공개정보 사이트로 확인됨.
"""
import re
import sys
import os

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

LATEST_UPDATES_URL = "https://health.ec.europa.eu/latest-updates_en"

MONTHS = {m: i + 1 for i, m in enumerate(
    ["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
     "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"])}
DATE_RE = re.compile(r"(\d{1,2})\s+([A-Z]+)\s+(20\d{2})")

MD_KEYWORDS = ["medical device", "in vitro diagnostic", "ivdr", " mdr ", "mdcg",
               "notified bod", "eudamed", "udi", "emdn"]


def _parse_date(text):
    m = DATE_RE.search((text or "").upper())
    if not m:
        return None
    d, mon, y = m.groups()
    mo = MONTHS.get(mon)
    return f"{y}-{mo:02d}-{int(d):02d}" if mo else None


def _is_md_related(text):
    t = (text or "").lower()
    return any(kw in t for kw in MD_KEYWORDS)


def run(since_year=2026, since_month=1, max_items=15):
    if BeautifulSoup is None:
        raise RuntimeError("beautifulsoup4 미설치")

    res = fetch(LATEST_UPDATES_URL)
    if res.robots_disallowed:
        print(f"[mdcg] robots.txt 차단: {res.error}")
        return [], res
    if not res.ok:
        return [], res

    soup = BeautifulSoup(res.text, "html.parser")
    items = []
    for a in soup.select("a[href]"):
        title = a.get_text(strip=True)
        href = a.get("href")
        if not title or len(title) < 8 or not href:
            continue
        container_text = a.find_parent().get_text(" ", strip=True) if a.find_parent() else ""
        if not (_is_md_related(title) or _is_md_related(container_text)):
            continue
        pub_date = _parse_date(container_text) or _parse_date(title)
        if not pub_date:
            continue
        y, mo = int(pub_date[:4]), int(pub_date[5:7])
        if (y, mo) < (since_year, since_month):
            continue

        url = href if href.startswith("http") else "https://health.ec.europa.eu" + href
        items.append({"title": title, "url": url, "pub_date": pub_date})
        if len(items) >= max_items:
            break

    results = []
    for it in items:
        body_text, attach_status = _fetch_detail_text(it["url"])
        doc_no = _extract_mdcg_no(it["title"]) or it["title"][:40]

        prev = load_previous_snapshot("MDCG", doc_no)
        gap = generate_gap(prev, body_text or it["title"])
        if body_text:
            save_snapshot("MDCG", doc_no, body_text)

        summary_source = body_text or it["title"]
        results.append({
            "search_month": it["pub_date"][:7],
            "publish_date": it["pub_date"],
            "effective_date": None,
            "publisher": "MDCG (EU)",
            "doc_no": doc_no,
            "title": it["title"],
            "summary": summarize(it["title"], summary_source) + (
                "" if body_text else f"\n\n(첨부 원문 확보 실패: {attach_status})"),
            "scope": guess_scope(it["title"] + " " + summary_source),
            "sop_required": "★" if guess_sop_flag(it["title"] + " " + summary_source) else "",
            "url": it["url"],
            "gap_analysis": gap,
        })
    return results, None


def _extract_mdcg_no(title):
    m = re.search(r"MDCG\s*\d{4}-\d+(\s*rev\.?\s*\d+)?", title, re.IGNORECASE)
    return m.group(0) if m else None


def _fetch_detail_text(url):
    res = fetch(url)
    if res.robots_disallowed:
        return "", f"robots.txt 차단"
    if not res.ok:
        return "", res.error or "접속 실패"

    if BeautifulSoup is None:
        return "", "beautifulsoup4 미설치"
    soup = BeautifulSoup(res.text, "html.parser")

    pdf_link = None
    for a in soup.select('a[href$=".pdf"]'):
        pdf_link = a.get("href")
        break
    if pdf_link:
        pdf_url = pdf_link if pdf_link.startswith("http") else "https://health.ec.europa.eu" + pdf_link
        content = fetch_binary(pdf_url)
        if content:
            text, status = extract_text(content, "file.pdf")
            if text:
                return text, "OK"

    main = soup.select_one("main") or soup.select_one("article") or soup.body
    text = main.get_text("\n", strip=True) if main else ""
    return text, "OK (본문 HTML)" if text else "본문을 찾지 못함"


if __name__ == "__main__":
    found, block = run()
    print(f"수집 {len(found)}건")
