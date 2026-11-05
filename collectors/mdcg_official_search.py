"""Bounded no-key discovery through the European Commission's public search.

Search and update pages are discovery only. The caller must fetch and validate
PDF contents independently. A result set is never an exhaustive archive search.
"""
import re
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

_AGENT = 'RegulatoryWatchBot/1.0'
_SEARCH = 'https://ec.europa.eu/search/'
_HEALTH = 'health.ec.europa.eu'
_REF = re.compile(r'\bMDCG\s*(\d{4}-\d+)\s*(?:(?:rev\.?|revision)\s*(\d+))?(?![\w.-])', re.I)


def _host(url):
    try:
        p = urlsplit(url)
        if p.scheme != 'https' or p.username is not None or p.password is not None or p.port not in (None, 443):
            return None
        return p.hostname
    except (TypeError, ValueError):
        return None


def _fetch_html(url):
    """Fetch HTML without redirects, checking robots first and bounding bytes."""
    p = urlsplit(url)
    if _host(url) not in ('ec.europa.eu', _HEALTH):
        raise ValueError('unapproved discovery host')
    headers = {'User-Agent': _AGENT}
    def get_bytes(target, limit):
        with requests.get(target, headers=headers, timeout=15, allow_redirects=False, stream=True) as response:
            if response.status_code != 200:
                raise ValueError('discovery request failed')
            content = bytearray()
            for chunk in response.iter_content(65536):
                content.extend(chunk)
                if len(content) > limit:
                    raise ValueError('discovery response too large')
            return bytes(content)
    robots = get_bytes('https://' + p.netloc + '/robots.txt', 1024 * 1024)
    parser = RobotFileParser()
    parser.parse(robots.decode('utf-8', 'replace').splitlines())
    if not parser.can_fetch(_AGENT, url):
        raise ValueError('robots.txt disallows discovery')
    return get_bytes(url, 3 * 1024 * 1024).decode('utf-8', 'replace')


def discover_official_links(number, revision, *, fetch=_fetch_html):
    """Find candidate PDFs linked by up to four matching issuer update pages."""
    if not re.fullmatch(r'\d{4}-\d+', number or '') or not isinstance(revision, int) or revision < 0:
        raise ValueError('invalid MDCG identity')
    url = _SEARCH + '?' + urlencode({'QueryText': 'MDCG ' + number})
    soup = BeautifulSoup(fetch(url), 'html.parser')
    main = soup.find('main')
    if main is None:
        raise ValueError('unrecognized search page')
    pages = []
    for a in main.find_all('a', href=True):
        link = urljoin(url, a['href'])
        path = urlsplit(link).path
        m = _REF.search(a.get_text(' ', strip=True))
        if (_host(link) == _HEALTH and path.startswith('/latest-updates/') and m
                and (m.group(1), int(m.group(2) or 0)) == (number, revision) and link not in pages):
            pages.append(link)
            if len(pages) == 4:
                break
    links = []
    for page in pages:
        result = BeautifulSoup(fetch(page), 'html.parser').find('main')
        if result is None:
            raise ValueError('unrecognized issuer page')
        for a in result.find_all('a', href=True):
            link = urljoin(page, a['href'])
            if _host(link) == _HEALTH and urlsplit(link).path.startswith('/document/download/') and link not in links:
                links.append(link)
                if len(links) == 8:
                    return links
    return links
