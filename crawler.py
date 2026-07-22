"""
자동 수집 오케스트레이터.

실행:
  python crawler.py                      # 2026-01 부터 전체 자동 수집 기관 실행
  python crawler.py --since 2026-01
  python crawler.py --only mdcg fda      # 특정 기관만
"""
import argparse
import importlib
import sys
import os
import time

sys.path.append(os.path.dirname(__file__))
from collectors.store import upsert_regulations, load_regulations  # noqa: E402

# MFDS(가장 느림 — 게시판 7개 × 상세페이지 × 첨부다운로드)를 마지막 순서로 배치.
# 앞선 기관들이 먼저 저장을 마치면, MFDS 단계에서 시간이 오래 걸리거나
# 플랫폼 타임아웃으로 중단되더라도 이미 저장된 데이터는 보존된다.
AUTO_AGENCIES = ["mdcg", "fda", "mhra", "mdsap", "tga", "health_canada", "pmda", "mfds"]


def run_crawler(since_year=2026, since_month=1, only=None, progress_cb=None):
    """
    기관별로 수집이 끝나는 즉시 그 결과를 저장한다(부분 저장).
    전체가 다 끝나야만 저장하는 방식이면, 뒤쪽 기관에서 타임아웃/오류가 났을 때
    앞서 끝난 기관들의 데이터까지 통째로 사라지므로 이를 방지하기 위함이다.

    progress_cb(agency_key, status_str) 를 넘기면 기관 처리 직후 호출된다
    (Streamlit 쪽에서 진행상황을 실시간으로 보여줄 때 사용).
    """
    targets = only or AUTO_AGENCIES
    summary = {}

    for key in targets:
        try:
            mod = importlib.import_module(f"collectors.{key}")
        except Exception as e:
            msg = f"모듈 오류: {e}"
            print(f"[ERROR] {key} 모듈 로드 실패: {e}")
            summary[key] = msg
            if progress_cb:
                progress_cb(key, msg)
            continue

        t0 = time.time()
        try:
            items, block_info = mod.run(since_year, since_month)
        except Exception as e:
            msg = f"실행 오류: {e}"
            print(f"[ERROR] {key} 실행 실패: {e}")
            summary[key] = msg
            if progress_cb:
                progress_cb(key, msg)
            continue
        elapsed = time.time() - t0

        if block_info is not None:
            if getattr(block_info, "robots_disallowed", False):
                msg = "robots.txt 차단"
                print(f"[SKIP] {key}: {block_info.error}")
                summary[key] = msg
                if progress_cb:
                    progress_cb(key, msg)
                continue
            if getattr(block_info, "blocked", False):
                msg = "접속 차단"
                print(f"[BLOCKED] {key}: {block_info.error}")
                summary[key] = msg
                if progress_cb:
                    progress_cb(key, msg)
                continue

        # 이 기관 결과를 즉시 저장 (부분 저장 — 핵심 수정 사항)
        if items:
            upsert_regulations(items)

        msg = f"{len(items)}건 수집 ({elapsed:.0f}초)"
        summary[key] = msg
        print(f"[OK] {key}: {msg}")
        if progress_cb:
            progress_cb(key, msg)

    saved = load_regulations()
    print("\n=== 수집 요약 ===")
    for k, v in summary.items():
        print(f"  {k:16s}: {v}")
    print(f"\n총 {len(saved)}건 저장 완료 → data/regulations.json")
    return saved, summary


def run_crawler_module(agency_key: str, since_year=2026, since_month=1):
    """단일 기관만 재실행할 때 사용."""
    return run_crawler(since_year, since_month, only=[agency_key])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", default="2026-01", help="YYYY-MM 형식, 기본 2026-01")
    parser.add_argument("--only", nargs="*", default=None)
    args = parser.parse_args()
    y, m = args.since.split("-")
    run_crawler(int(y), int(m), only=args.only)
