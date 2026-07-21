"""
자동 수집 오케스트레이터.
MFDS는 robots.txt 정책상 자동 수집 대상에서 제외되어 있으며,
Streamlit 화면(app.py)의 "MFDS 수동 입력" 폼을 통해서만 등록됩니다.

실행:
  python crawler.py                      # 2026-01 부터 전체 자동 수집 기관 실행
  python crawler.py --since 2026-01
"""
import argparse
import importlib
import sys
import os

sys.path.append(os.path.dirname(__file__))
from collectors.store import upsert_regulations  # noqa: E402

AUTO_AGENCIES = ["mdcg", "fda", "mhra", "mdsap", "tga", "health_canada", "pmda"]


def run_crawler(since_year=2026, since_month=1, only=None):
    targets = only or AUTO_AGENCIES
    all_items = []
    summary = {}

    for key in targets:
        try:
            mod = importlib.import_module(f"collectors.{key}")
        except Exception as e:
            print(f"[ERROR] {key} 모듈 로드 실패: {e}")
            summary[key] = f"모듈 오류: {e}"
            continue

        try:
            items, block_info = mod.run(since_year, since_month)
        except Exception as e:
            print(f"[ERROR] {key} 실행 실패: {e}")
            summary[key] = f"실행 오류: {e}"
            continue

        if block_info is not None:
            if getattr(block_info, "robots_disallowed", False):
                print(f"[SKIP] {key}: robots.txt 차단 — {block_info.error}")
                summary[key] = "robots.txt 차단"
                continue
            if getattr(block_info, "blocked", False):
                print(f"[BLOCKED] {key}: {block_info.error}")
                summary[key] = "접속 차단"
                continue

        all_items.extend(items)
        summary[key] = f"{len(items)}건 수집"
        print(f"[OK] {key}: {len(items)}건")

    saved = upsert_regulations(all_items)
    print("\n=== 수집 요약 ===")
    for k, v in summary.items():
        print(f"  {k:16s}: {v}")
    print(f"\n총 {len(saved)}건 저장 완료 → data/regulations.json")
    return saved, summary


def run_crawler_module(agency_key: str, since_year=2026, since_month=1):
    """app.py의 '수동 업데이트' 버튼에서 단일 기관만 재실행할 때 사용."""
    return run_crawler(since_year, since_month, only=[agency_key])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", default="2026-01", help="YYYY-MM 형식, 기본 2026-01")
    parser.add_argument("--only", nargs="*", default=None)
    args = parser.parse_args()
    y, m = args.since.split("-")
    run_crawler(int(y), int(m), only=args.only)
