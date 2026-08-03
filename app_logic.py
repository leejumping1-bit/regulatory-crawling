"""Pure UI data-selection helpers used by the Streamlit app."""


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
    retain it as a conservative fallback rather than exporting an empty cell.
    """
    text = str(summary or "").strip()
    if not text:
        return ""

    marker = "[핵심 내용]"
    start = text.find(marker)
    if start < 0:
        return text

    content = text[start + len(marker):]
    next_section = content.find("[")
    if next_section >= 0:
        content = content[:next_section]
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
