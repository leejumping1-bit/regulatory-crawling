"""Pure UI data-selection helpers used by the Streamlit app."""

import re


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
