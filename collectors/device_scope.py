"""Conservative explicit medical-device terminology, not generic devices."""
import re

_PATTERN = re.compile(r'\b(?:medical[\s-]+devices?|in[\s-]+vitro[\s-]+diagnostics?(?:[\s-]+(?:medical[\s-]+)?devices?)?|ivds?|investigational[\s-]+device[\s-]+exemptions?)\b', re.I)


def has_explicit_device_term(text):
    return isinstance(text, str) and bool(_PATTERN.search(text))
