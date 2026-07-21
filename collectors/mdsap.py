"""MDSAP 수집기 — 문서 라이브러리 (갱신 빈도 낮음, 정적 목록 파싱)"""
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from collectors.http_utils import fetch  # noqa: E402
from collectors.pipeline import build_item, is_medical_device_related  # noqa: E402

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

LIBRARY_URL = "https://www.mdsap.global/documents/library/audit-approach"


def run(since_year=2026, since_month=1, max_items=10):
    if BeautifulSoup is None:
        raise RuntimeError("beautifulsoup4 미설치")

    res = fetch(LIBRARY_URL)
    if res.robots_disallowed:
        return [], res
    if not res.ok:
        return [], res

    soup = BeautifulSoup(res.text, "html.parser")
    results = []
    for a in soup.select('a[href$=".pdf"], a[href*="document"]'):
        title = a.get_text(strip=True)
        href = a.get("href")
        if not title or len(title) < 6 or not href:
            continue
        # MDSAP은 문서 전체가 의료기기 심사 프로그램이므로 별도 키워드 필터 없이 전부 대상
        url = href if href.startswith("http") else "https://www.mdsap.global" + href
        results.append(build_item(
            agency_label="MDSAP",
            title=title, url=url, pub_date=None, doc_no=title[:40],
        ))
        if len(results) >= max_items:
            break
    return results, None


if __name__ == "__main__":
    found, block = run()
    print(f"수집 {len(found)}건")
