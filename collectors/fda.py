"""
FDA(US) 수집기 — v2 (eCFR 공식 API 기반, 실제 변경이 있을 때만 수집)

사용자 요청: eCFR 비교 페이지(Comparing the eCFR in effect on X to what was
previously in effect on Y)처럼, 실제로 조문이 바뀐 경우에만 수집하고 싶다.

이번 버전은 화면(JS 렌더링) 대신 eCFR이 공개 제공하는 API를 사용한다(키 불필요):
  1) 버전 이력 조회: /api/versioner/v1/versions/title-21.json
     → Part 820 관련 항목들의 최신 "issue_date"(개정 반영일)를 구한다.
  2) 우리가 마지막으로 확인한 issue_date와 다르면 "변경 있음"으로 판단하고,
     전문 텍스트를 가져온다: /api/versioner/v1/full/{issue_date}/title-21.xml?part=820
  3) XML에서 텍스트만 추출해 우리가 저장해둔 이전 전문 스냅샷과 diff_engine으로 비교한다.

한계(정직하게 명시): 이 API의 정확한 JSON 응답 스키마(필드명 등)를 이 환경에서
실제로 호출해 검증하지 못했다. 아래 파싱 코드는 eCFR 개발자 문서에 기술된 구조를
기반으로 작성했으며, 실제 배포 후 응답 구조가 다르면 조정이 필요할 수 있다 —
그 경우를 대비해 실패 시 예외를 던지지 않고 안내 메시지를 담은 결과를 반환하도록
방어적으로 작성했다.
"""
import re
import sys
import os
from datetime import date

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from collectors.http_utils import fetch  # noqa: E402
from collectors.summarizer import summarize  # noqa: E402
from collectors.diff_engine import generate_gap  # noqa: E402
from collectors.store import load_previous_snapshot, save_snapshot  # noqa: E402

VERSIONS_API = "https://www.ecfr.gov/api/versioner/v1/versions/title-21.json"
FULL_API_TMPL = "https://www.ecfr.gov/api/versioner/v1/full/{date}/title-21.xml?part=820"
HUMAN_URL_TMPL = "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-820"
DOC_NO = "21 CFR Part 820"

# 마지막으로 확인한 issue_date를 기억해두는 상태 파일 (data/snapshots 아래에 저장)
LAST_SEEN_KEY = "FDA_last_issue_date"


def _get_latest_issue_date():
    res = fetch(VERSIONS_API)
    if not res.ok:
        print(f"[fda][DEBUG] 버전 API 요청 실패: {res.error}")
        return None, res
    print(f"[fda][DEBUG] 버전 API 응답 {len(res.text)}자")
    try:
        import json
        data = json.loads(res.text)
    except Exception as e:
        print(f"[fda][DEBUG] JSON 파싱 실패, 응답 앞부분: {res.text[:300]!r}")
        return None, f"버전 API 응답 파싱 실패: {e}"

    print(f"[fda][DEBUG] 최상위 키: {list(data.keys())}")

    # 응답 스키마 후보 여러 개를 시도한다 (실제 구조 미검증에 대한 방어적 처리)
    candidates = data.get("content_versions") or data.get("versions") or []
    print(f"[fda][DEBUG] content_versions/versions 항목 수: {len(candidates)}")
    if candidates:
        print(f"[fda][DEBUG] 첫 항목 예시: {candidates[0]}")

    part_versions = [v for v in candidates if str(v.get("part")) == "820"]
    if not part_versions:
        return None, "Part 820 버전 정보를 응답에서 찾지 못했습니다 (스키마 확인 필요)"

    dates = [v.get("issue_date") or v.get("amendment_date") for v in part_versions]
    dates = [d for d in dates if d]
    if not dates:
        return None, "issue_date 필드를 찾지 못했습니다 (스키마 확인 필요)"

    return max(dates), None


def run(since_year=2026, since_month=1, today_only=False):
    latest_date, err = _get_latest_issue_date()
    if latest_date is None:
        print(f"[fda] 버전 확인 실패: {err}")
        return [], None

    prev_seen = load_previous_snapshot("FDA", LAST_SEEN_KEY)
    if prev_seen and prev_seen.strip() == latest_date:
        # 마지막 확인 이후 변경 없음 — 사용자 요청대로 이 경우 수집하지 않는다
        return [], None

    if today_only and latest_date != date.today().isoformat():
        return [], None
    if not today_only:
        y, mo = int(latest_date[:4]), int(latest_date[5:7])
        if (y, mo) < (since_year, since_month):
            return [], None

    full_res = fetch(FULL_API_TMPL.format(date=latest_date))
    if not full_res.ok:
        print(f"[fda] 전문 텍스트 조회 실패: {full_res.error}")
        return [], None

    xml_text = full_res.text
    plain_text = re.sub(r"<[^>]+>", " ", xml_text)
    plain_text = re.sub(r"\s+", " ", plain_text).strip()

    prev_text = load_previous_snapshot("FDA", DOC_NO)
    gap = generate_gap(prev_text, plain_text)
    save_snapshot("FDA", DOC_NO, plain_text)
    save_snapshot("FDA", LAST_SEEN_KEY, latest_date)

    summary = summarize(f"{DOC_NO} — {latest_date} 개정 반영", plain_text)
    if not prev_text:
        summary += "\n\n(※ 이번이 최초 수집이라 개정 전/후 비교는 다음 개정부터 가능합니다.)"

    item = {
        "search_month": latest_date[:7],
        "publish_date": latest_date,
        "effective_date": latest_date,
        "publisher": "FDA (US)",
        "doc_no": DOC_NO,
        "title": f"21 CFR Part 820 (Quality Management System Regulation) — {latest_date} 개정 반영",
        "summary": summary,
        "scope": "종합",
        "sop_required": "★",  # 법 원문 전체 문서 — 항상 SOP 검토 대상
        "url": HUMAN_URL_TMPL,
        "gap_analysis": gap,
    }
    return [item], None


if __name__ == "__main__":
    found, block = run()
    print(f"수집 {len(found)}건")
