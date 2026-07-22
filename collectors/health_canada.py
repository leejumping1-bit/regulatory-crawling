"""
Health Canada 수집기 — SOR/98-282 Medical Devices Regulations

페이지 상단에 항상 다음 형식의 문구가 있다 (실제 확인됨):
  "Regulations are current to 2026-03-17 and last amended on 2026-01-01."
'last amended on' 날짜를 개정일(publish_date)로 사용한다.
"""
import re
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from collectors.http_utils import fetch  # noqa: E402
from collectors.pipeline import build_item  # noqa: E402

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

REGULATION_URL = "https://laws-lois.justice.gc.ca/eng/regulations/sor-98-282/"
AMENDED_RE = re.compile(r"last amended on (\d{4}-\d{2}-\d{2})", re.IGNORECASE)
CURRENT_TO_RE = re.compile(r"current to (\d{4}-\d{2}-\d{2})", re.IGNORECASE)


def run(since_year=2026, since_month=1):
    res = fetch(REGULATION_URL)
    if res.robots_disallowed:
        return [], res
    if not res.ok:
        return [], res

    page_text = res.text
    if BeautifulSoup is not None:
        page_text = BeautifulSoup(res.text, "html.parser").get_text(" ", strip=True)

    amended_m = AMENDED_RE.search(page_text)
    current_to_m = CURRENT_TO_RE.search(page_text)

    last_amended = amended_m.group(1) if amended_m else None
    current_to = current_to_m.group(1) if current_to_m else None

    if not last_amended:
        print("[health_canada] 'last amended on' 문구를 찾지 못했습니다. 페이지 구조가 바뀌었을 수 있습니다.")
        return [], None

    y, mo = int(last_amended[:4]), int(last_amended[5:7])
    if (y, mo) < (since_year, since_month):
        return [], None

    item = build_item(
        agency_label="Health Canada",
        title=f"Medical Devices Regulations (SOR/98-282) — {last_amended} 개정 반영본",
        url=REGULATION_URL,
        pub_date=last_amended,
        effective_date=last_amended,
        doc_no="SOR/98-282",
    )
    if current_to:
        item["summary"] += f"\n\n(페이지 기준 현행화 시점: {current_to})"
    return [item], None


if __name__ == "__main__":
    found, block = run()
    print(f"수집 {len(found)}건")
