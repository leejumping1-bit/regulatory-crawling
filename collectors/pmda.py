"""PMDA(일본) 수집기"""
import sys
import os
import re
from urllib.parse import urljoin, urlparse

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from collectors.http_utils import fetch  # noqa: E402
from collectors.pipeline import build_item  # noqa: E402

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

PMDA_URL = "https://www.pmda.go.jp/english/review-services/regulatory-info/0004.html"
ALLOWED_HOSTS = {"pmda.go.jp", "www.pmda.go.jp"}
YEAR_RE = re.compile(r"\b(20\d{2})\b")


def _extract_year(title):
    years = [int(value) for value in YEAR_RE.findall(title or "")]
    return max(years) if years else None


def _is_in_scope(title, since_year):
    year = _extract_year(title)
    return year is not None and year >= since_year


def _safe_pdf_url(href):
    url = urljoin(PMDA_URL, href or "")
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        return None
    if not parsed.path.lower().endswith(".pdf"):
        return None
    return url


def run(since_year=2026, since_month=1, max_items=10):
    if BeautifulSoup is None:
        raise RuntimeError("beautifulsoup4 미설치")

    res = fetch(PMDA_URL)
    if res.robots_disallowed:
        return [], res
    if not res.ok:
        return [], res

    soup = BeautifulSoup(res.text, "html.parser")
    results = []
    for a in soup.select('a[href$=".pdf"]'):
        title = a.get_text(strip=True)
        href = a.get("href")
        if not title or len(title) < 6 or not href:
            continue
        if not _is_in_scope(title, since_year):
            continue
        url = _safe_pdf_url(href)
        if not url:
            continue
        results.append(build_item(
            agency_label="PMDA (Japan)",
            title=title, url=url, pub_date=None, doc_no=title[:40],
        ))
        if len(results) >= max_items:
            break
    return results, None


if __name__ == "__main__":
    found, block = run()
    print(f"수집 {len(found)}건")
