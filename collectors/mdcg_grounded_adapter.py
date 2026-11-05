"""Search candidates independently verified as MDCG predecessor PDFs.

Search is bounded and never exhaustive. Notified-body documents are
supplemental, never EU evidence.
"""
from dataclasses import dataclass
import re
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests

from collectors.grounded_discovery import discover_links
from collectors.mdcg_official_search import discover_official_links
from collectors.revision_evidence import DocumentVersion, pdf_pages

OFFICIAL = 'health.ec.europa.eu'
# Exact hosts only, no subdomains. NB sources must also be direct PDF URLs.
NOTIFIED_BODIES = frozenset({'www.bsigroup.com', 'www.tuvsud.com', 'www.tuv.com'})
_REF = re.compile(r'\bMDCG\s*(\d{4}-\d+)\s*(?:(?:rev\.?|revision)\s*(\d+))?(?![\w.-])', re.I)


@dataclass(frozen=True)
class DiscoveryResult:
    status: str
    official: tuple = ()
    supplemental: tuple = ()
    rejected: int = 0
    failed: int = 0
    exhaustive: bool = False
    detail: str = ''


def _host(url):
    try:
        p = urlsplit(url)
        if p.scheme != 'https' or not p.hostname or p.username is not None or p.password is not None or p.port not in (None, 443):
            return None
        return p.hostname
    except (TypeError, ValueError):
        return None


def _download(url):
    """No document or robots redirects; fail closed when robots cannot be read."""
    parsed = urlsplit(url)
    origin = 'https://' + parsed.netloc
    headers = {'User-Agent': 'RegulatoryWatchBot/1.0'}
    try:
        with requests.get(origin + '/robots.txt', headers=headers, timeout=10, allow_redirects=False, stream=True) as robots:
            if robots.status_code == 404:
                pass
            elif robots.status_code == 200:
                content = b''
                for chunk in robots.iter_content(65536):
                    content += chunk
                    if len(content) > 1024 * 1024:
                        raise ValueError('robots.txt too large')
                parser = RobotFileParser()
                parser.parse(content.decode('utf-8', errors='replace').splitlines())
                if not parser.can_fetch(headers['User-Agent'], url):
                    raise ValueError('robots.txt disallows URL')
            else:
                raise ValueError('robots.txt unavailable')
        with requests.get(url, headers=headers, timeout=25, allow_redirects=False, stream=True) as response:
            if response.status_code != 200:
                raise ValueError('document unavailable or redirected')
            content = b''
            for chunk in response.iter_content(65536):
                content += chunk
                if len(content) > 25 * 1024 * 1024:
                    raise ValueError('document too large')
            if not content.startswith(b'%PDF-'):
                raise ValueError('not a PDF')
            return content
    except requests.RequestException as exc:
        raise ValueError('network failure') from exc


def discover_previous(doc_no, *, include_notified_bodies=False, search=None, download=None, extract=None):
    """Discover immediate predecessor candidates; all evidence is fetched text.

    Status is verified, no_results, unavailable, or nonexhaustive. A successful
    empty search is still non-exhaustive; it never establishes absence. Injected
    download/extract/search functions are test seams and must be trusted.
    """
    match = _REF.fullmatch((doc_no or '').strip())
    if not match or not match.group(2) or int(match.group(2)) < 1:
        return DiscoveryResult('unavailable', detail='Invalid revised MDCG document identity')
    number, revision = match.group(1), int(match.group(2)) - 1
    query = f'"MDCG {number}" ' + (f'"rev {revision}"' if revision else 'original') + ' site:health.ec.europa.eu filetype:pdf'
    if include_notified_bodies:
        query = f'"MDCG {number}" previous version filetype:pdf (site:health.ec.europa.eu OR site:www.bsigroup.com OR site:www.tuvsud.com OR site:www.tuv.com)'
    try:
        links = (search or discover_links)(query)
        if not isinstance(links, (list, tuple)):
            raise ValueError('invalid discovery response')
    except Exception:
        if search is not None:
            return DiscoveryResult('unavailable', detail='Injected search unavailable')
        try:
            links = discover_official_links(number, revision)
        except Exception:
            return DiscoveryResult('unavailable', detail='Grounded and official search unavailable')
    if not links:
        return DiscoveryResult('no_results', detail='No allowed candidates returned; search is not exhaustive')
    official, supplemental = [], []
    failed = rejected = 0
    seen = set()
    for url in links:
        host = _host(url)
        if not host or host not in ({OFFICIAL} | (NOTIFIED_BODIES if include_notified_bodies else set())):
            rejected += 1
            continue
        if host != OFFICIAL and not urlsplit(url).path.lower().endswith('.pdf'):
            rejected += 1
            continue
        if url in seen:
            continue
        seen.add(url)
        try:
            pages = tuple((extract or pdf_pages)((download or _download)(url)))
            if not pages or any(not isinstance(p, str) or not p.strip() for p in pages):
                raise ValueError('empty PDF text')
            # Only the first page's header region, never arbitrary body mentions.
            header = '\n'.join(pages[0].splitlines()[:12])[:1500]
            refs = list(_REF.finditer(header))
            identities = {(m.group(1), int(m.group(2) or 0)) for m in refs}
            if (identities != {(number, revision)}
                    or not any(not header[header.rfind('\n', 0, m.start()) + 1:m.start()].strip() for m in refs)
                    or re.search(r'\bappendix\b', header, re.I)):
                raise ValueError('document header identity or revision ambiguous')
            version = DocumentVersion('MDCG ' + number, revision, url, pages)
            (official if host == OFFICIAL else supplemental).append(version)
        except Exception:
            failed += 1
    status = 'verified' if official else 'nonexhaustive'
    return DiscoveryResult(status, tuple(official), tuple(supplemental), rejected, failed, False,
                           'Search candidates are non-exhaustive; supplemental sources are not official evidence')
