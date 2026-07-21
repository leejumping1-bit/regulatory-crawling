"""
FDA(US) 수집기 — eCFR Title 21 Part 820 (QMSR)
공식 Compare API를 사용한다: https://www.ecfr.gov/api/versioner/v1/comparison/...
"""
import sys
import os
from datetime import date

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from collectors.http_utils import fetch  # noqa: E402
from collectors.pipeline import build_item  # noqa: E402

PART = "title-21/chapter-I/subchapter-H/part-820"


def run(since_year=2026, since_month=1):
    d1 = date(since_year, since_month, 1).isoformat()
    d2 = date.today().isoformat()
    compare_url = f"https://www.ecfr.gov/compare/{d1}/to/{d2}/{PART}"

    # eCFR 자체 변경 여부 확인 (versioner API)
    api_url = f"https://www.ecfr.gov/api/versioner/v1/comparison/{d1}/{d2}/{PART}.json"
    res = fetch(api_url)
    if res.robots_disallowed:
        return [], res
    if not res.ok:
        return [], res

    # TODO(실사용 전 필수): API 응답 JSON 구조를 실제로 확인하여 changed=true 여부 정확히 판정
    # 여기서는 최소한 "현재 규정 버전"을 항목으로 등록하고, 상세 원문은 사람이 compare_url에서 확인하도록 안내
    item = build_item(
        agency_label="FDA (US)",
        title=f"21 CFR Part 820 (Quality Management System Regulation) 변경 여부 확인 필요 ({d1} → {d2})",
        url=compare_url,
        pub_date=d2,
        doc_no="21 CFR Part 820",
        fetch_detail=False,  # eCFR 페이지는 JS 렌더링 비중이 커 정적 파싱이 부정확할 수 있음 (TODO)
    )
    item["summary"] = (
        f"eCFR 비교 페이지({compare_url})에서 {d1} 대비 {d2} 시점 Part 820 변경 여부를 자동 판정하지 못했습니다. "
        "eCFR versioner API 응답 스키마를 확인해 실제 조항 diff를 파싱하는 로직 보완이 필요합니다 (TODO)."
    )
    return [item], None


if __name__ == "__main__":
    found, block = run()
    print(f"수집 {len(found)}건")
