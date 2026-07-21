"""TGA(호주) 수집기 — ARGMD 페이지 갱신일 확인"""
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from collectors.http_utils import fetch  # noqa: E402
from collectors.pipeline import build_item  # noqa: E402

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

ARGMD_URL = "https://www.tga.gov.au/products/medical-devices/overview/australian-regulatory-guidelines-medical-devices-argmd"


def run(since_year=2026, since_month=1):
    if BeautifulSoup is None:
        raise RuntimeError("beautifulsoup4 미설치")

    res = fetch(ARGMD_URL)
    if res.robots_disallowed:
        return [], res
    if not res.ok:
        return [], res

    item = build_item(
        agency_label="TGA (Australia)",
        title="Australian Regulatory Guidelines for Medical Devices (ARGMD)",
        url=ARGMD_URL, pub_date=None, doc_no="ARGMD",
    )
    return [item], None


if __name__ == "__main__":
    found, block = run()
    print(f"수집 {len(found)}건")
