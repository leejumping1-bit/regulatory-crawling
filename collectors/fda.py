"""FDA Part 820 collector using substantive eCFR amendments and official text."""
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from urllib.parse import urlencode, urlparse

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from collectors.http_utils import fetch  # noqa: E402
from collectors.summarizer import summarize, guess_manufacturer_obligation  # noqa: E402
from collectors.diff_engine import generate_gap  # noqa: E402
from collectors.store import load_previous_snapshot, save_snapshot  # noqa: E402

VERSIONS_API = "https://www.ecfr.gov/api/versioner/v1/versions/title-21.json?part=820"
FULL_API_TMPL = "https://www.ecfr.gov/api/versioner/v1/full/{date}/title-21.xml?part=820"
HUMAN_URL_TMPL = "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-820"
DOC_NO = "21 CFR Part 820"
# Retain the existing key for compatibility; its value is now an amendment date.
LAST_SEEN_KEY = "FDA_last_issue_date"

federal_register_fetch = fetch
FR_API = "https://www.federalregister.gov/api/v1/documents.json"
FR_FIELDS = ("document_number", "title", "type", "publication_date", "effective_on",
             "html_url", "abstract", "agencies", "action")


def discover_federal_register(since_year=2026, since_month=1, today_only=False):
    start = date.today() if today_only else date(since_year, since_month, 1)
    params = [("conditions[agencies][]", "food-and-drug-administration"),
              ("conditions[term]", "medical device"),
              ("conditions[publication_date][gte]", start.isoformat()),
              ("per_page", "100"), ("order", "newest")]
    if today_only:
        params.append(("conditions[publication_date][lte]", start.isoformat()))
    params.extend(("fields[]", field) for field in FR_FIELDS)
    rows = []
    for page in range(1, 21):
        res = federal_register_fetch(FR_API + "?" + urlencode(params + [("page", str(page))]))
        if not res.ok:
            raise RuntimeError("Federal Register 조회 실패: " + str(getattr(res, "error", "unknown")))
        try:
            data = json.loads(res.text)
            count = data["count"]
            total_pages = data.get("total_pages", 0 if count == 0 else None)
            results = data.get("results", [] if count == 0 else None)
            if (type(total_pages) is not int or total_pages < 0 or type(count) is not int or count < 0
                    or not isinstance(results, list)
                    or (count > 0 and (total_pages == 0 or not results))
                    or (count == 0 and (total_pages != 0 or results))):
                raise ValueError("invalid pagination")
            rows.extend(results)
        except (ValueError, TypeError, KeyError) as exc:
            raise RuntimeError("Federal Register 응답 파싱 실패") from exc
        if page >= total_pages:
            break
    else:
        raise RuntimeError("Federal Register 페이지 제한 초과; 기간을 나누어 재시도")
    items = []
    seen = set()
    for row in rows:
        title = row.get("title") or ""
        url = urlparse(row.get("html_url") or "")
        published = row.get("publication_date")
        try:
            valid_date = isinstance(published, str) and date.fromisoformat(published).isoformat() == published
        except ValueError:
            valid_date = False
        if (not valid_date or url.scheme != "https" or url.hostname != "www.federalregister.gov" or
            not url.path.startswith("/documents/") or
            not title or not row.get("document_number") or
            not any(a.get("slug") == "food-and-drug-administration" for a in row.get("agencies", [])) or
            not re.search(r"\bdevices?\b", title + " " + (row.get("abstract") or ""), re.I) or
            not (row.get("type") in ("Rule", "Proposed Rule") or
                 row.get("type") == "Notice" and re.search(r"\bguidance\b", title, re.I))):
            continue
        if row["document_number"] in seen:
            continue
        seen.add(row["document_number"])
        status_text = title + " " + (row.get("action") or "")
        status = "draft" if re.search(r"\bdraft\b", status_text, re.I) or row.get("type") == "Proposed Rule" else (
            "final" if re.search(r"\bfinal\b", status_text, re.I) or row.get("type") == "Rule" else "unknown")
        items.append({"search_month": row["publication_date"][:7], "publish_date": row["publication_date"],
                      "effective_date": row.get("effective_on") or "", "publisher": "FDA (US)",
                      "doc_no": row["document_number"], "title": title, "summary": ("[Federal Register 공식 초록 (영문)]\n" + row["abstract"]) if row.get("abstract") else "[공식 초록 없음] 문서 원문을 확인하세요.",
                      "scope": "종합", "manufacturer_obligation": "", "url": row["html_url"],
                      "document_status": status, "gap_analysis": None})
    return items


def _extract_issue_dates(data):
    """Return valid amendment dates only for explicitly substantive Part 820 rows."""
    candidates = data.get("content_versions") or data.get("versions") or []
    dates = set()
    for version in candidates:
        if not isinstance(version, dict) or str(version.get("part")) != "820" or version.get("substantive") is not True:
            continue
        value = version.get("amendment_date")
        try:
            if isinstance(value, str) and date.fromisoformat(value).isoformat() == value:
                dates.add(value)
        except ValueError:
            continue
    return sorted(dates)


def _extract_latest_issue_date(data):
    dates = _extract_issue_dates(data)
    return dates[-1] if dates else None


def _get_latest_issue_date():
    res = fetch(VERSIONS_API)
    if not res.ok:
        return None, res
    try:
        latest = _extract_latest_issue_date(json.loads(res.text))
    except (ValueError, TypeError, AttributeError):
        return None, "버전 API 응답 파싱 실패"
    return (latest, None) if latest else (None, "Part 820 버전 정보를 찾지 못했습니다")


def _part_text(xml_text):
    """Reject error pages and malformed XML, and normalize visible part text."""
    try:
        root = ET.fromstring(xml_text)
    except (ET.ParseError, ValueError, TypeError):
        return None
    if root.tag != "DIV5" or root.get("TYPE") != "PART" or root.get("N") != "820":
        return None
    return re.sub(r"\s+", " ", " ".join(root.itertext())).strip() or None


def _run_part_820(since_year=2026, since_month=1, today_only=False):
    latest_date, err = _get_latest_issue_date()
    if latest_date is None:
        raise RuntimeError(f"FDA 버전 확인 실패: {getattr(err, 'error', err)}")

    prev_seen = load_previous_snapshot("FDA", LAST_SEEN_KEY)
    if prev_seen and prev_seen.strip() >= latest_date:
        return [], None
    if today_only and latest_date != date.today().isoformat():
        return [], None
    if not today_only and (int(latest_date[:4]), int(latest_date[5:7])) < (since_year, since_month):
        return [], None

    # Compare the actual official text immediately before the amendment, never a
    # potentially stale or unrelated local snapshot. Failure remains retryable.
    prior_date = (date.fromisoformat(latest_date) - timedelta(days=1)).isoformat()
    current_res = fetch(FULL_API_TMPL.format(date=latest_date))
    prior_res = fetch(FULL_API_TMPL.format(date=prior_date))
    if not current_res.ok or not prior_res.ok:
        errors = [str(getattr(res, "error", "조회 실패")) for res in (current_res, prior_res) if not res.ok]
        raise RuntimeError("공식 개정 전/후 원문 조회 실패: " + "; ".join(errors))
    plain_text = _part_text(current_res.text)
    prev_text = _part_text(prior_res.text)
    if not plain_text or not prev_text:
        raise RuntimeError("공식 개정 전/후 원문 형식 확인 실패")
    if plain_text == prev_text:
        return [], None

    gap = generate_gap(prev_text, plain_text)
    summary = summarize(f"{DOC_NO} — {latest_date} 개정 반영", plain_text)
    title = f"21 CFR Part 820 (Quality Management System Regulation) — {latest_date} 개정 반영"
    item = {
        "search_month": latest_date[:7],
        "publish_date": "",  # amendment date is not a verified publication date
        "effective_date": "",
        "publisher": "FDA (US)",
        "doc_no": DOC_NO,
        "title": title,
        "summary": summary,
        "scope": "종합",
        "manufacturer_obligation": "★" if guess_manufacturer_obligation(title, plain_text) else "",
        "url": HUMAN_URL_TMPL,
        "gap_analysis": gap,
    }
    save_snapshot("FDA", DOC_NO, plain_text)
    save_snapshot("FDA", LAST_SEEN_KEY, latest_date)
    return [item], None


def run(since_year=2026, since_month=1, today_only=False):
    from collectors.http_utils import FetchResult
    discovered, part_items, errors = [], [], []
    try:
        discovered = discover_federal_register(since_year, since_month, today_only)
    except Exception as exc:
        errors.append(f'Federal Register 확인 실패: {exc}')
    try:
        part_items, block = _run_part_820(since_year, since_month, today_only)
        if block is not None:
            errors.append(f'Part 820 확인 실패: {getattr(block, "error", block)}')
    except Exception as exc:
        errors.append(f'Part 820 확인 실패: {exc}')
    return part_items + discovered, FetchResult(False, error='; '.join(errors)) if errors else None


if __name__ == "__main__":
    found, block = run()
    print(f"수집 {len(found)}건")
