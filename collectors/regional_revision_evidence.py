"""Evidence from explicitly bounded issuer-authored web-page change descriptions.

Never uses snapshot differences, titles, guessed attachments, or search snippets.
Only an exact non-redirected source response is accepted; unsupported layouts and
unavailable sources remain incomplete, not evidence of no change.
"""
import re
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup
from collectors.http_utils import DEFAULT_HEADERS, _robots_allowed

_HOSTS = {
    'mhra': {'www.gov.uk'},
    'mfds': {'www.mfds.go.kr', 'mfds.go.kr'},
    'health_canada': {'laws-lois.justice.gc.ca'},
}


def _official(kind, url):
    try:
        p = urlsplit(url)
        return (p.scheme == 'https' and p.hostname in _HOSTS.get(kind, set())
                and not p.username and not p.password and p.port in (None, 443)
                and not p.fragment)
    except (ValueError, TypeError):
        return False


def _incomplete(url, detail):
    return {'status': 'discovery_incomplete', 'current_url': url, 'detail': detail}


def parse_revision_history(kind, url, html):
    """Parse only recognized, explicit sections from verified current-page HTML."""
    if not _official(kind, url) or not isinstance(html, str) or not html:
        return _incomplete(url, 'Official current URL or original text unavailable')
    soup = BeautifulSoup(html, 'html.parser')
    sections = []
    if kind == 'mhra':
        history = soup.select('#full-publication-update-history')
        if len(history) == 1:
            entries = history[0].select(':scope > li.gem-c-metadata__change-history-item')
            if entries:
                dates = entries[0].select('time.gem-c-metadata__change-date')
                notes = entries[0].select('p.gem-c-metadata__change-note')
                if len(dates) == len(notes) == 1:
                    title, quote = dates[0].get_text().strip(), notes[0].get_text()
                    if title and quote.strip() and quote.strip().lower() not in ('first published.', 'first published'):
                        sections.append({'title': title, 'quote': quote})
    elif kind == 'mfds' and urlsplit(url).path == '/brd/m_207/view.do':
        bodies = soup.select('.bv_cont')
        if len(bodies) == 1:
            # A sequence of paragraphs gives explicit section boundaries. Refuse
            # nested or other body structures rather than accidentally quote them.
            body = bodies[0]
            nodes = [x for x in body.children if getattr(x, 'name', None) not in (None, 'br')
                     and (x.name == 'p' or x.get_text().strip())]
            if nodes and all(x.name == 'p' for x in nodes):
                heading = re.compile(r'^\s*\d+\s*\.\s*(개정\s*이유|주요\s*내용)\s*$')
                boundary = re.compile(r'^\s*\d+\s*\.\s*\S')
                i = 0
                while i < len(nodes):
                    match = heading.fullmatch(nodes[i].get_text())
                    if not match:
                        i += 1
                        continue
                    j = i + 1
                    while j < len(nodes) and not boundary.match(nodes[j].get_text()):
                        j += 1
                    quotes = [n.get_text() for n in nodes[i + 1:j] if n.get_text().strip()]
                    if quotes:
                        sections.append({'title': nodes[i].get_text().strip(), 'quote': '\n'.join(quotes)})
                    i = j
                # Generic "major contents" alone also occurs in new notices;
                # require a verified revision-reason section for context.
                if not any(re.search(r'개정\s*이유', s['title']) for s in sections):
                    sections = []
    if not sections:
        return _incomplete(url, 'Explicit revision explanation not verified; previous-version discovery incomplete')
    return {'status': 'revision_history', 'current_url': url, 'sections': sections}


def _get_exact(url, kind):
    # The shared fetch helper does not return the final redirect URL. Do not use
    # its body as a quotation attributed to the requested URL after a redirect.
    if kind != 'mfds' and not _robots_allowed(url):
        return None
    response = requests.get(url, headers=DEFAULT_HEADERS, timeout=15, allow_redirects=False)
    if response.status_code != 200 or response.url != url:
        return None
    if 'html' not in response.headers.get('Content-Type', '').lower():
        return None
    response.encoding = response.apparent_encoding or response.encoding
    return response.text


def collect_revision_evidence(kind, url, *, getter=None):
    if not _official(kind, url):
        return _incomplete(url, 'Official current URL unavailable')
    if kind == 'health_canada':
        return _incomplete(url, 'Explicit revision history and official predecessor not yet verified')
    try:
        html = (getter or _get_exact)(url, kind)
        return parse_revision_history(kind, url, html)
    except Exception:
        return _incomplete(url, 'Official current source retrieval or extraction failed')
