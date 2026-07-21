"""Health Canada 수집기 — SOR/98-282 Medical Devices Regulations"""
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from collectors.http_utils import fetch  # noqa: E402
from collectors.pipeline import build_item  # noqa: E402

REGULATION_URL = "https://laws-lois.justice.gc.ca/eng/regulations/sor-98-282/"


def run(since_year=2026, since_month=1):
    res = fetch(REGULATION_URL)
    if res.robots_disallowed:
        return [], res
    if not res.ok:
        return [], res

    item = build_item(
        agency_label="Health Canada",
        title="Medical Devices Regulations (SOR/98-282)",
        url=REGULATION_URL, pub_date=None, doc_no="SOR/98-282",
    )
    return [item], None


if __name__ == "__main__":
    found, block = run()
    print(f"수집 {len(found)}건")
