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


def monthly_summary_excerpts(summary):
    """Select complete verbatim passages, never synthesize or truncate words.

    Prefer explicitly marked key/obligation sections; keep at most two complete
    bullet blocks, or two sentences in long prose. Otherwise keep short text
    intact or the first two complete sentences; if boundaries are unavailable,
    retain the whole text.
    """
    text = str(summary or "")
    if not text.strip():
        return [], False
    passages = []
    section = re.compile(r"(?m)^\s*\[(핵심 내용|제조업체 의무사항)\][^\S\r\n]*")
    heading = re.compile(r"(?m)^\s*\[[^\]\r\n]+\]")
    for match in section.finditer(text):
        end = heading.search(text, match.end())
        content = text[match.end():end.start() if end else len(text)]
        content = content.strip()
        if not content:
            continue
        bullets = list(re.finditer(r"(?m)^[ \t]*[-•*][ \t]+", content))
        if bullets and not content[:bullets[0].start()].strip():
            end_index = bullets[2].start() if len(bullets) > 2 else len(content)
            passages.append(content[:end_index].rstrip())
        elif len(content) > 240:
            ends = list(re.finditer(r"[.!?。！？](?=\s|$)", content))
            passages.append(content[:ends[min(1, len(ends)-1)].end()] if ends else content)
        else:
            passages.append(content)
    if not passages:
        clean = text.strip()
        if len(clean) <= 240:
            passages = [clean]
        else:
            ends = list(re.finditer(r"[.!?。！？](?=\s|$)", clean))
            passages = [clean[:ends[min(1, len(ends)-1)].end()]] if ends else [clean]
    return passages, len(passages) != 1 or passages[0] != text.strip()


def monthly_report_date(item):
    """Select an MHRA date only when its actual precision confirms the bucket."""
    from datetime import date

    publication = item.get("publish_date") or "-"
    if item.get("publisher") not in {"MHRA", "MHRA (UK)"}:
        return publication, ""
    month = item.get("search_month")

    def matches(value):
        if not isinstance(value, str) or not isinstance(month, str):
            return False
        if not re.fullmatch(r"\d{4}-\d{2}", month):
            return False
        if not re.fullmatch(r"\d{4}-\d{2}(?:-\d{2})?", value):
            return False
        try:
            date.fromisoformat(value if len(value) == 10 else value + "-01")
        except ValueError:
            return False
        return value[:7] == month

    for key in ("change_date", "revision_date"):
        value = item.get(key)
        if matches(value):
            return value, " (업데이트일)"
    if matches(item.get("publish_date")):
        return publication, ""
    return publication, " (해당 월 일치 미확인)"


def monthly_report_html(items, selected_month, selected_publisher):
    """Render the same filtered ledger as an escaped compact report table."""
    from html import escape
    from urllib.parse import urlsplit

    def e(value):
        return escape(str(value or ""), quote=True)

    labels = {"official_abstract": "공식 초록", "official_change_note": "공식 변경 설명", "third_party_extracted_official_revision_history": "공식 개정 이력(제3자 추출)", "official_document_excerpt": "공식 문서에서 추출한 내용", "official_announcement": "공식 공지·설명"}
    parts = [f'<div class="monthly-report"><h2>월별 업데이트 요약 보고서</h2><p>조회 월: {e(selected_month)} · 발행처: {e(selected_publisher)} · 총 {len(items)}건<br>월 기준: 대장 분류 월(search_month), 기관별로 고시·변경·개정일 기준이 다를 수 있음. 전체는 모든 월을 포함합니다.<br>Manufacturer obligation 빈칸은 의무가 없다는 뜻이 아님.</p><div class="monthly-table-container"><table class="monthly-table"><thead><tr><th>No.</th><th>고시일 / MHRA 업데이트일</th><th>발행처</th><th>제목</th><th>요약내용</th><th>Manufacturer obligation</th></tr></thead><tbody>']
    for item in items:
        excerpts, shortened = monthly_summary_excerpts(item.get("summary"))
        summary = '<br>'.join('<span class="monthly-excerpt">' + e(x).replace("\n", "<br>") + '</span>' for x in excerpts) or '요약 없음'
        if shortened:
            summary += '<div class="monthly-note">발췌 · 전체 내용은 아래 02</div>'
        source = item.get("summary_source") or {}
        kind = source.get("type")
        summary += f'<div class="monthly-note">요약 근거: {e(labels.get(kind, kind or "출처 정보 없음"))}'
        if kind in {"official_abstract", "official_change_note", "third_party_extracted_official_revision_history"}:
            summary += '. 문서 전체 요약이나 신구 대조 결과는 아닙니다.'
        elif kind in {"official_document_excerpt", "official_announcement"}:
            summary += '. 출처의 확인된 내용만 요약했습니다.'
        url = source.get("url") or ""
        parsed = urlsplit(url)
        if kind in {"official_document_excerpt", "official_announcement"} and parsed.scheme == "https" and parsed.hostname in {"health.ec.europa.eu", "ec.europa.eu", "eur-lex.europa.eu"}:
            summary += f' <a href="{e(url)}" target="_blank" rel="noopener noreferrer">요약 출처 열기</a>'
        summary += '</div>'
        if item.get("summary_status") == "summary_unavailable":
            summary += '<div class="monthly-warning">⚠ 한글 요약을 생성하지 못했습니다. 아래 내용은 공식 영문 원문입니다.</div>'
        if item.get("summary_retained_stale"):
            warning = "이번 원문의 한글 요약 생성이 실패하거나 미뤄져 이전 요약을 표시합니다. 현재 원문과 다를 수 있습니다." if item.get("summary_retained_stale_reason") == "generation_failed_or_deferred" else "원문 재조회에 실패해 이전에 저장한 요약을 표시합니다. 최신 여부는 확인되지 않았습니다."
            summary += f'<div class="monthly-warning">⚠ {warning}</div>'
        title = e(item.get("title") or "-")
        if item.get("document_status") in ("draft", "final"):
            title += '<div class="monthly-note">문서 상태: ' + ("초안" if item["document_status"] == "draft" else "최종 규칙·최종 안내") + '</div>'
        obligation = item.get("manufacturer_obligation", item.get("sop_required")) or "-"
        date, annotation = monthly_report_date(item)
        parts.append(f'<tr class="monthly-row"><td>{e(item["no"])}</td><td><span style="white-space:nowrap">{e(date)}</span>{e(annotation)}</td><td>{e(item.get("publisher") or "-")}</td><td>{title}</td><td>{summary}</td><td>{e(obligation)}</td></tr>')
    parts.append('</tbody></table></div></div>')
    return ''.join(parts)
