"""MHRA collection via GOV.UK Search and Content APIs.

The legacy fixed-page parser remains available for compatibility; run() uses
organisation-filtered Search and issuer-authored Content API history instead.
"""
import re
import sys
import os
from datetime import date

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from collectors.http_utils import fetch, fetch_binary  # noqa: E402
from collectors.file_extract import extract_text  # noqa: E402
from collectors.summarizer import summarize, guess_scope, guess_manufacturer_obligation  # noqa: E402
from collectors.diff_engine import generate_document_gap  # noqa: E402
from collectors.store import load_previous_snapshot, save_snapshot  # noqa: E402
from collectors.regional_revision_evidence import collect_revision_evidence  # noqa: E402

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

SOURCES = {
    "MHRA-medical-devices-uk": "https://www.gov.uk/guidance/regulating-medical-devices-in-the-uk",
    "MHRA-vigilance-manufacturers": "https://www.gov.uk/government/collections/medical-devices-guidance-for-manufacturers-on-vigilance",
}

LAST_UPDATED_RE = re.compile(r"Last updated:?\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})")
DATE_HEADING_RE = re.compile(r"(?:^|\n)(\d{1,2}\s+[A-Za-z]+\s+\d{4})\n")
MONTHS = {m: i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"])}


def _to_iso(date_text):
    parts = date_text.split()
    if len(parts) != 3:
        return None
    d, mon, y = parts
    mo = MONTHS.get(mon)
    if not mo:
        return None
    try:
        return f"{y}-{mo:02d}-{int(d):02d}"
    except ValueError:
        return None


def _extract_changelog(text):
    matches = list(DATE_HEADING_RE.finditer(text))
    entries = []
    for i, m in enumerate(matches):
        date_str = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else min(len(text), start + 800)
        desc = text[start:end].strip()
        if desc:
            entries.append((date_str, desc))
    return entries


def _extract_attachment_text(soup, page_url):
    for ext in (".pdf", ".docx"):
        a = soup.select_one(f'a[href$="{ext}"]')
        if not a:
            continue
        href = a.get("href")
        file_url = href if href.startswith("http") else "https://www.gov.uk" + href
        content = fetch_binary(file_url)
        if content:
            filename = file_url.rsplit("/", 1)[-1]
            text, status = extract_text(content, filename)
            if text:
                return text
    return ""


def _process_source(doc_no, url, today_only):
    res = fetch(url)
    if res.robots_disallowed:
        return None, res
    if not res.ok:
        return None, res
    if BeautifulSoup is None:
        raise RuntimeError("beautifulsoup4 미설치")

    soup = BeautifulSoup(res.text, "html.parser")
    page_text = soup.get_text("\n", strip=True)

    m_last = LAST_UPDATED_RE.search(page_text)
    last_updated_text = m_last.group(1) if m_last else None
    last_updated_iso = _to_iso(last_updated_text) if last_updated_text else None

    if today_only:
        if not last_updated_iso or last_updated_iso != date.today().isoformat():
            return None, None

    entries = _extract_changelog(page_text)
    changelog_text = "\n\n".join(f"[{d}]\n{desc}" for d, desc in entries) or "(변경이력 없음 — 페이지 구조 확인 필요)"

    attachment_text = _extract_attachment_text(soup, url)
    full_snapshot_text = changelog_text + (
        f"\n\n[첨부파일 원문]\n{attachment_text}" if attachment_text else ""
    )

    prev = load_previous_snapshot(doc_no, doc_no)
    if not prev and len(entries) >= 2:
        # GOV.UK가 공개한 직전 changelog를 공식 과거 상태로 사용한다.
        prev = "\n\n".join(f"[{d}]\n{desc}" for d, desc in entries[1:])
    gap = generate_document_gap(prev, full_snapshot_text, title=doc_no, publisher="MHRA (UK)")
    save_snapshot(doc_no, doc_no, full_snapshot_text)

    title_prefix = soup.title.get_text(strip=True) if soup.title else doc_no
    latest_entry_desc = entries[0][1] if entries else ""
    summary = summarize(title_prefix, latest_entry_desc or changelog_text)
    if not prev:
        summary += "\n\n(※ 이번이 최초 수집이라 개정 전/후 비교는 다음 업데이트부터 가능합니다.)"

    item = {
        "search_month": (last_updated_iso or "")[:7],
        "publish_date": last_updated_iso,
        "effective_date": None,
        "publisher": "MHRA (UK)",
        "doc_no": doc_no,
        "title": f"{title_prefix} — 변경이력 업데이트 ({last_updated_text or '날짜 미확인'})",
        "summary": summary,
        "scope": guess_scope(title_prefix + " " + changelog_text, title=title_prefix, publisher="MHRA (UK)"),
        "manufacturer_obligation": "★" if guess_manufacturer_obligation(title_prefix, changelog_text) else "",
        "url": url + "#full-publication-update-history",
        "revision_evidence": collect_revision_evidence("mhra", url),
        "gap_analysis": gap,
    }
    return item, None


def events_from_content(content, since):
    """Emit issuer-described publication/update events, not inferred amendments."""
    import hashlib
    from datetime import datetime
    path = content.get("base_path", "")
    if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
        return []
    title = content.get("title") or ""
    url = "https://www.gov.uk" + path
    published = (content.get("first_published_at") or "")[:10] or None
    events = []
    history = list((content.get("details") or {}).get("change_history") or [])
    has_history = bool(history)
    first_at = content.get("first_published_at")
    if first_at and not any(isinstance(e, dict) and str(e.get("note", "")).strip().rstrip(".").lower() == "first published" for e in history):
        history.append({"public_timestamp": first_at, "note": "First published."})
    updated_at = content.get("public_updated_at")
    if updated_at and updated_at != first_at and not has_history:
        history.append({"public_timestamp": updated_at, "note": "Official update timestamp; change description unavailable.", "unverified": True})
    for entry in history:
        if not isinstance(entry, dict):
            continue
        timestamp, note = entry.get("public_timestamp"), entry.get("note")
        if not isinstance(timestamp, str) or not isinstance(note, str) or not note.strip():
            continue
        try:
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            continue
        day = timestamp[:10]
        if day < since:
            continue
        first = note.strip().rstrip(".").lower() == "first published"
        key = hashlib.sha256((path + "\0" + timestamp + "\0" + note).encode()).hexdigest()[:24]
        evidence = ({"status": "discovery_incomplete", "current_url": url,
                     "detail": ("Official update description unavailable" if entry.get("unverified") else "First publication; prior version not established")} if first or entry.get("unverified") else
                    {"status": "revision_history", "current_url": url,
                     "sections": [{"title": day, "quote": note}]})
        events.append({"search_month": day[:7], "publish_date": published,
                       "change_date": day, "source_updated_date": (content.get("public_updated_at") or "")[:10] or None,
                       "collected_date": date.today().isoformat(), "effective_date": None,
                       "publisher": "MHRA (UK)", "doc_no": "MHRA-" + key,
                       "title": title, "summary": "[MHRA 공식 변경 설명 (영문)]\n" + note, "scope": "",
                       "manufacturer_obligation": "", "url": url,
                       "revision_evidence": evidence})
    return events


def _api_get(path, params=None):
    import json
    from urllib.parse import urlencode
    url = "https://www.gov.uk" + path
    if params:
        url += "?" + urlencode(params)
    response = fetch(url, timeout=8, retries=1, backoff=1.0, allowed_hosts={"www.gov.uk"})
    if not response.ok:
        raise RuntimeError(response.error or "GOV.UK API request failed")
    try:
        result = json.loads(response.text)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("Invalid GOV.UK API JSON") from exc
    if not isinstance(result, dict):
        raise RuntimeError("Unexpected GOV.UK API response")
    return result


def _relevant(row):
    # Explicit phrases only; generic 'classification', MDR and quality-system
    # terms also describe medicines and must not classify them as devices.
    text = str(row.get("title") or "")
    return bool(re.search(r"\b(?:medical[ -]devices?|in[ -]vitro diagnostics?|ivds?)\b", text, re.I))


def backfill(since, *, page_size=100, max_pages=None, today_only=False, max_documents=80, max_seconds=120):
    """Return events and error status without writing snapshots or the ledger.

    Search is organisation-filtered, descending by public timestamp. Coverage is
    limited to indexed records and explicit device phrases in titles.
    """
    from datetime import date as _date
    from collectors.http_utils import FetchResult
    from urllib.parse import urlsplit
    _date.fromisoformat(since)
    if not 1 <= page_size <= 1000 or (max_pages is not None and max_pages < 1):
        raise ValueError("invalid pagination limit")
    import time
    started = time.monotonic()
    found, seen_paths, seen_events = [], set(), set()
    start = 0
    try:
        while True:
            if time.monotonic() - started >= max_seconds:
                raise RuntimeError('MHRA 시간 제한 도달: 부분 수집')
            if max_pages is not None and start // page_size >= max_pages:
                raise RuntimeError("Search page limit reached; results incomplete")
            data = _api_get('/api/search.json', {'filter_organisations': 'medicines-and-healthcare-products-regulatory-agency',
                            'count': page_size, 'start': start, 'order': '-public_timestamp'})
            rows, total = data.get('results'), data.get('total')
            if not isinstance(rows, list) or not isinstance(total, int):
                raise RuntimeError('Invalid search results')
            if not rows:
                if start < total:
                    raise RuntimeError('Search pagination ended prematurely')
                break
            older = False
            for row in rows:
                if not isinstance(row, dict):
                    raise RuntimeError('Invalid search result')
                stamp = row.get('public_timestamp')
                if isinstance(stamp, str) and stamp[:10] < since:
                    older = True
                    continue
                if not _relevant(row):
                    continue
                path = row.get('link')
                if not isinstance(path, str):
                    continue
                parsed = urlsplit(path)
                if (parsed.scheme or parsed.netloc or parsed.query or parsed.fragment
                        or not path.startswith('/') or path.startswith('//')
                        or '%' in path or '\\' in path
                        or any(part in ('.', '..') for part in path.split('/'))):
                    continue
                if path in seen_paths:
                    continue
                if len(seen_paths) >= max_documents or time.monotonic() - started >= max_seconds:
                    raise RuntimeError('MHRA 요청·시간 제한 도달: 부분 수집')
                seen_paths.add(path)
                content = _api_get('/api/content' + path)
                if content.get('base_path') != path:
                    raise RuntimeError('Content API path mismatch: ' + path)
                for item in events_from_content(content, since):
                    if today_only and item['change_date'] != _date.today().isoformat():
                        continue
                    if item['doc_no'] not in seen_events:
                        found.append(item)
                        seen_events.add(item['doc_no'])
            start += len(rows)
            if older or start >= total:
                break
    except Exception as exc:
        return found, FetchResult(False, error=str(exc))
    return found, None


def run(since_year=2026, since_month=1, today_only=False):
    since = date.today().isoformat() if today_only else date(since_year, since_month, 1).isoformat()
    return backfill(since, today_only=today_only)


if __name__ == "__main__":
    found, block = run()
    print(f"수집 {len(found)}건")
    for f in found:
        print(" -", f["title"])
