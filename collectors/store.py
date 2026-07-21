"""
data/regulations.json 읽기/쓰기 + 문서별 원문 스냅샷 저장(diff 비교용).

스냅샷을 쓰는 이유:
  같은 문서(reg_no)가 다음 달에 다시 개정되었을 때, "직전에 저장해둔 원문"과
  "이번에 새로 받은 원문"을 비교해야 진짜 Gap 분석(개정 전 vs 개정 후)이 가능하다.
  최초 수집 시점에는 비교할 과거본이 없으므로 N.A.(신규 제정)로 처리한다.
"""
import json
import os
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
DATA_PATH = os.path.join(BASE_DIR, "data", "regulations.json")
SNAPSHOT_DIR = os.path.join(BASE_DIR, "data", "snapshots")


def load_regulations():
    if not os.path.exists(DATA_PATH):
        return []
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_regulations(items):
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    # No. 재부여 (고시일 최신순, 문자열 비교라 YYYY-MM-DD 형식 가정)
    items = sorted(items, key=lambda x: (x.get("publish_date") or ""), reverse=True)
    for idx, it in enumerate(items, start=1):
        it["no"] = idx
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    return items


def upsert_regulations(new_items):
    """agency + doc_no 를 key 로 기존 항목을 갱신하거나 추가."""
    existing = load_regulations()
    by_key = {f"{it.get('publisher')}::{it.get('doc_no')}": it for it in existing}
    for it in new_items:
        key = f"{it.get('publisher')}::{it.get('doc_no')}"
        by_key[key] = it
    return save_regulations(list(by_key.values()))


def _snapshot_path(agency: str, doc_no: str) -> str:
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    safe = "".join(c if c.isalnum() else "_" for c in f"{agency}_{doc_no}")[:120]
    return os.path.join(SNAPSHOT_DIR, f"{safe}.txt")


def load_previous_snapshot(agency: str, doc_no: str):
    path = _snapshot_path(agency, doc_no)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def save_snapshot(agency: str, doc_no: str, text: str):
    if not text:
        return
    path = _snapshot_path(agency, doc_no)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
