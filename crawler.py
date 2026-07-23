"""
자동 수집 오케스트레이터.

두 가지 모드:
  1) 전체(since) 모드 — 2026-01부터 전체를 훑는다. 시간이 오래 걸릴 수 있으므로
     GitHub Actions(백그라운드, 타임아웃 여유 큼)의 매일 스케줄 실행이 이 모드를 담당한다.
     python crawler.py --since 2026-01

  2) 오늘자(today-only) 모드 — 오늘 날짜로 게시된 항목만 빠르게 확인한다.
     Streamlit 화면의 "지금 실행" 버튼이 이 모드를 사용한다(요청/응답 시간 제한이 있는
     플랫폼이라 오래 걸리는 전체 스캔은 부적합하기 때문).
     python crawler.py --today-only

각 기관 수집기(collectors/*.py)가 today_only 파라미터를 직접 지원하면 그걸 쓰고
(예: mdcg.py — 페이지네이션을 오늘 날짜에서 바로 멈춰 빠르다), 아직 지원하지 않는
수집기는 이번 달(since=이번달)로 조회 범위를 좁힌 뒤 결과를 오늘 날짜로 한 번 더
걸러내는 차선책을 쓴다(완벽히 빠르진 않지만 안전하게 동작한다).
"""
import argparse
import importlib
import inspect
import sys
import os
import time
from datetime import date

sys.path.append(os.path.dirname(__file__))
from collectors.store import upsert_regulations, load_regulations  # noqa: E402

# MFDS(가장 느림 — 게시판 7개 × 상세페이지 × 첨부다운로드)를 마지막 순서로 배치.
# 앞선 기관들이 먼저 저장을 마치면, MFDS 단계에서 시간이 오래 걸리거나
# 플랫폼 타임아웃으로 중단되더라도 이미 저장된 데이터는 보존된다.
AUTO_AGENCIES = ["mdcg", "fda", "mhra", "mdsap", "tga", "health_canada", "pmda", "mfds"]


def _run_agency(mod, since_year, since_month, today_only):
    """today_only를 기관 수집기가 지원하면 그대로 넘기고, 아니면 이번 달로 좁혀
    호출한 뒤 결과를 오늘 날짜로 재필터링한다."""
    if today_only and "today_only" in inspect.signature(mod.run).parameters:
        return mod.run(since_year, since_month, today_only=True)

    y = date.today().year if today_only else since_year
    m = date.today().month if today_only else since_month
    items, block_info = mod.run(y, m)

    if today_only and items:
        today_str = date.today().isoformat()
        items = [it for it in items if (it.get("publish_date") or "") == today_str]

    return items, block_info


def run_crawler(since_year=2026, since_month=1, only=None, progress_cb=None, today_only=False):
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
            items, block_info = _run_agency(mod, since_year, since_month, today_only)
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

        # 이 기관 결과를 즉시 저장 (부분 저장)
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
    parser.add_argument("--today-only", action="store_true", help="오늘 게시된 항목만 빠르게 조회")
    args = parser.parse_args()
    y, m = args.since.split("-")
    run_crawler(int(y), int(m), only=args.only, today_only=args.today_only)
