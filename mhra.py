"""
MHRA(UK) 수집기 — gov.uk 뉴스/공지 검색 (MHRA 필터)
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

SEARCH_URL = ("https://www.gov.uk/search/news-and-communications"
              "?organisations%5B%5D=medicines-and-healthcare-products-regulatory-agency"
              "&order=updated-newest")
DATE_RE = re.compile(r"(20\d{2})-(\d{2})-(\d{2})")


def run(since_year=2026, since_month=1, max_items=10):
    if BeautifulSoup is None:
        raise RuntimeError("beautifulsoup4 미설치")

    res = fetch(SEARCH_URL)
    if res.robots_disallowed:
        return [], res
    if not res.ok:
        return [], res

    soup = BeautifulSoup(res.text, "html.parser")
    results = []
    for li in soup.select("li.gem-c-document-list__item, div.gem-c-document-list__item"):
        a = li.select_one("a")
        if not a:
            continue
        title = a.get_text(strip=True)
        href = a.get("href")
        if not title or not href or not is_medical_device_related(title + " " + li.get_text(" ")):
            continue
        time_tag = li.select_one("time")
        pub_date = None
        if time_tag and time_tag.get("datetime"):
            m = DATE_RE.search(time_tag["datetime"])
            if m:
                pub_date = "-".join(m.groups())
        if not pub_date:
            continue
        y, mo = int(pub_date[:4]), int(pub_date[5:7])
        if (y, mo) < (since_year, since_month):
            continue

        url = href if href.startswith("http") else "https://www.gov.uk" + href
        results.append(build_item(
            agency_label="MHRA (UK)",
            title=title, url=url, pub_date=pub_date, doc_no=title[:40],
        ))
        if len(results) >= max_items:
            break

    return results, None


if __name__ == "__main__":
    found, block = run()
    print(f"수집 {len(found)}건")
