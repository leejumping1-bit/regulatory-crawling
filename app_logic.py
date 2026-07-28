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
