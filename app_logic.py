"""Pure UI data-selection helpers used by the Streamlit app."""

import re


def mdsap_status_is_stale(timestamp, now=None):
    from datetime import datetime, timezone, timedelta
    try:
        checked = datetime.fromisoformat(timestamp)
        if checked.utcoffset() is None:
            return True
        age = (now or datetime.now(timezone.utc)) - checked
        return age < timedelta(0) or age > timedelta(hours=48)
    except (ValueError, TypeError, OverflowError):
        return True


def display_doc_no(item):
    """Suppress MHRA's synthetic event identifier, not real document numbers."""
    number = (item.get("doc_no") or "").replace("\n", " ")
    if item.get("publisher") == "MHRA (UK)" and re.fullmatch(r"MHRA-[0-9a-f]{24}", number):
        return ""
    return number


def permanent_update_workflow_url():
    """Return the authenticated GitHub UI for a durable manual update.

    The public Streamlit app must not carry a repository write token. GitHub's
    own workflow page performs authentication and exposes the existing
    ``workflow_dispatch`` action to authorized repository users.
    """
    return (
        "https://github.com/leejumping1-bit/regulatory-crawling/"
        "actions/workflows/scheduled_crawl.yml"
    )


def effective_month(item):
    """Return the stored month bucket, or UNKNOWN when it is unavailable."""
    return item.get("search_month") or "UNKNOWN"


def filter_by_month(data, selected_month="전체"):
    """Return all data by default, filtering only when a month is selected."""
    if not selected_month or selected_month == "전체":
        return list(data)
    return [item for item in data if effective_month(item) == selected_month]


def effective_publisher(item):
    """Return the stored publisher, or UNKNOWN when it is unavailable."""
    return item.get("publisher") or "UNKNOWN"


def filter_by_publisher(data, selected_publisher="전체"):
    """Return all data by default, filtering only when a publisher is selected."""
    if not selected_publisher or selected_publisher == "전체":
        return list(data)
    return [item for item in data if effective_publisher(item) == selected_publisher]

def extract_core_content(summary):
    """Return only the ``[핵심 내용]`` section from an auto-generated summary.

    Export files should not repeat the purpose/scope/caveat sections in the
    Manufacturer obligation cell.  If the summary has no structured marker,
    return an empty string. Exporting the entire unstructured summary would
    reintroduce purpose/scope/caveat sections that the export contract
    explicitly excludes.
    """
    text = str(summary or "").strip()
    if not text:
        return ""

    marker = "[핵심 내용]"
    start = text.find(marker)
    if start < 0:
        return ""

    content = text[start + len(marker):]
    next_section = re.search(r"(?m)^\s*\[[^\]\r\n]+\]", content)
    if next_section:
        content = content[:next_section.start()]
    return content.strip(" \t\r\n:-")


def estimate_export_row_height(values, column_widths):
    """Estimate a wrapped Excel row height for the export layout.

    XlsxWriter can wrap text but Excel does not reliably calculate row height
    for every generated workbook.  Estimate it here so long core-content cells
    are visible immediately instead of being hidden behind a one-line row.
    """
    max_lines = 1
    for value, width in zip(values, column_widths):
        text = str(value or "")
        if not text:
            continue
        chars_per_line = max(1, int(width * 1.6))
        lines = sum(max(1, (len(line) + chars_per_line - 1) // chars_per_line)
                    for line in text.splitlines())
        max_lines = max(max_lines, lines)
    return min(240, max(18, 6 + max_lines * 13))


def monthly_report_html(items, selected_month, selected_publisher):
    """Render the already-filtered ledger rows, without changing saved content."""
    from html import escape
    from urllib.parse import urlsplit

    def e(value):
        return escape(str(value or ""), quote=True)

    parts = [f'<div class="monthly-report"><h2>월별 업데이트 요약 보고서</h2><p>조회 월: {e(selected_month)} · 발행처: {e(selected_publisher)} · 총 {len(items)}건<br>월 기준: 대장 분류 월(search_month), 기관별로 고시·변경·개정일 기준이 다를 수 있음. 전체는 모든 월을 포함합니다.<br>Manufacturer obligation 빈칸은 의무가 없다는 뜻이 아님.</p>']
    for item in items:
        summary = e(item.get("summary")).replace("\n", "<br>") or "요약 없음"
        obligation = item.get("manufacturer_obligation", item.get("sop_required")) or "-"
        parts.append(f'<article class="monthly-item"><h3>No. {e(item["no"])} · {e(item.get("title") or "-")}</h3>'
                     f'<p>고시일: {e(item.get("publish_date") or "-")}</p>'
                     f'<p>발행처: {e(item.get("publisher") or "-")} · Manufacturer obligation: {e(obligation)}</p>'
                     f'<p class="monthly-summary"><b>[요약 내용]</b><br>{summary}</p>')
        if item.get("document_status") in ("draft", "final"):
            parts.append('<p>문서 상태: ' + ("초안" if item["document_status"] == "draft" else "최종 규칙·최종 안내") + '</p>')
        source = item.get("summary_source") or {}
        kind = source.get("type")
        labels = {"official_abstract": "공식 초록", "official_change_note": "공식 변경 설명", "third_party_extracted_official_revision_history": "공식 개정 이력(제3자 추출)", "official_document_excerpt": "공식 문서에서 추출한 내용", "official_announcement": "공식 공지·설명"}
        if kind in labels:
            caveat = "문서 전체 요약이나 신구 대조 결과는 아닙니다." if kind in {"official_abstract", "official_change_note", "third_party_extracted_official_revision_history"} else "출처의 확인된 내용만 요약했습니다."
            parts.append(f'<p>요약 근거: {labels[kind]}. {caveat}</p>')
            url = source.get("url") or ""
            parsed = urlsplit(url)
            if kind in {"official_document_excerpt", "official_announcement"} and parsed.scheme == "https" and parsed.hostname in {"health.ec.europa.eu", "ec.europa.eu", "eur-lex.europa.eu"}:
                parts.append(f'<p><a href="{e(url)}" target="_blank" rel="noopener noreferrer">요약 출처 열기</a></p>')
        if item.get("summary_status") == "summary_unavailable":
            parts.append('<p class="monthly-warning">⚠ 한글 요약을 생성하지 못했습니다. 아래 내용은 공식 영문 원문입니다.</p>')
        if item.get("summary_retained_stale"):
            warning = "이번 원문의 한글 요약 생성이 실패하거나 미뤄져 이전 요약을 표시합니다. 현재 원문과 다를 수 있습니다." if item.get("summary_retained_stale_reason") == "generation_failed_or_deferred" else "원문 재조회에 실패해 이전에 저장한 요약을 표시합니다. 최신 여부는 확인되지 않았습니다."
            parts.append(f'<p class="monthly-warning">⚠ {warning}</p>')
        parts.append('</article>')
    parts.append('</div>')
    return ''.join(parts)
