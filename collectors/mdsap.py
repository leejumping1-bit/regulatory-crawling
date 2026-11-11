"""MDSAP priority document and bounded supplemental document feed.

Jina Reader is a third-party text extraction service, not a PDF byte source.
"""
import re
from datetime import date
from urllib.parse import urljoin, urlsplit, unquote
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup
from collectors.http_utils import FetchResult, _robots_allowed
from collectors.store import load_regulations

LIBRARY_URL = 'https://www.mdsap.global/documents/library/audit-approach'
RSS_URL = 'https://www.mdsap.global/feeds/documents.xml'
NEWS_RSS_URL = 'https://www.mdsap.global/feeds/news.xml'
MAX_BYTES = 2_000_000


def _safe_url(url, pdf=False):
    try:
        if not isinstance(url, str) or len(url) > 2048 or any(ord(c) < 32 for c in url):
            return False
        p = urlsplit(url)
        if p.scheme != 'https' or p.netloc != 'www.mdsap.global' or p.username or p.password or p.fragment:
            return False
        if pdf:
            return p.path.startswith('/sites/default/files/') and p.path.lower().endswith('.pdf') and not p.query and '..' not in unquote(p.path).split('/')
        return True
    except ValueError:
        return False


def _get(url, *, reader=False, html=False):
    if not _safe_url(url) or not _robots_allowed(url):
        raise ValueError('official URL prohibited or invalid')
    target = 'https://r.jina.ai/' + url if reader else url
    headers = {'User-Agent': 'RegulatoryWatchBot/1.0', 'X-No-Cache': 'true'}
    if html:
        headers['X-Respond-With'] = 'html'
    with requests.get(target, headers=headers, timeout=(5, 60 if reader else 8), stream=True, allow_redirects=False) as r:
        r.raise_for_status()
        if r.status_code != 200:
            raise ValueError('unexpected HTTP status')
        chunks, size = [], 0
        for chunk in r.iter_content(65536):
            size += len(chunk)
            if size > MAX_BYTES:
                raise ValueError('response too large')
            chunks.append(chunk)
        return b''.join(chunks).decode('utf-8', errors='replace')


def _detail():
    try:
        text = _get(LIBRARY_URL)
        _attachment(text)
        return text
    except Exception:
        # Reader may return an HTTP-200 upstream error page. Retry once, but
        # retain the exact same validation and robots checks on every attempt.
        for attempt in range(2):
            try:
                text = _get(LIBRARY_URL, reader=True, html=True)
                _attachment(text)
                return text
            except Exception:
                if attempt == 1:
                    raise


def _attachment(html):
    matches = []
    soup = BeautifulSoup(html, 'html.parser')
    for block in soup.select('.file-collection__content'):
        header = block.select_one('.file-collection__header')
        m = re.search(r'MDSAP\s+AU\s+P0002\.(\d{3})\b', header.get_text(' ', strip=True) if header else '', re.I)
        if not m or 'audit approach' not in header.get_text(' ', strip=True).lower():
            continue
        for a in block.select('a[href]'):
            url = urljoin(LIBRARY_URL, a['href'])
            if _safe_url(url, pdf=True) and re.search(r'P0002\.' + m[1] + r'\b', unquote(url), re.I):
                matches.append((m[1], url))
    if len(matches) != 1:
        raise ValueError('priority version or exact official PDF link unavailable or ambiguous')
    return matches[0]


def parse_priority(html, text):
    version, url = _attachment(html)
    if len(text) > MAX_BYTES:
        raise ValueError('extracted text too large')
    cover = text[:8000]
    source = re.search(r'^URL Source:\s*(\S+)\s*$', cover, re.M)
    if source and source[1] != url:
        raise ValueError('reader source URL mismatch')
    if not re.search(r'policy\s+title\s*:\s*MDSAP\s+AUDIT\s+APPROACH', cover, re.I):
        raise ValueError('cover title mismatch')
    if not re.search(r'document\s+no\s*:\s*MDSAP\s+AU\s+P0002\.\s*' + version + r'\b', cover, re.I):
        raise ValueError('cover version mismatch')
    dm = re.search(r'revision\s+date\s*:\s*(?:#\s*)?(\d{4}-\d{2}-\d{2})', cover, re.I)
    if not dm:
        raise ValueError('cover revision date missing')
    date.fromisoformat(dm[1])
    headings = list(re.finditer(r'^\s*#\s*Summary of Changes from Prior Revisions\s*$', text, re.I | re.M))
    if not headings:
        raise ValueError('revision history missing')
    history = text[headings[-1].end():]
    sections = list(re.finditer(r'^\s*Changes from version\s+(\d{3})\s+to\s+(\d{3})\s*$', history, re.I | re.M))
    if not sections or sections[0][2] != version or len(sections) < 2:
        raise ValueError('current revision history not verified')
    quote = history[sections[0].start():sections[1].start()].strip()
    if len(quote) < 45 or len(quote) > 15000:
        raise ValueError('revision history empty or too large')
    number = 'MDSAP AU P0002.' + version
    return {'publisher': 'MDSAP', 'doc_no': number, 'title': 'Audit Approach – ' + number,
            'url': LIBRARY_URL, 'publish_date': None, 'effective_date': None,
            'revision_date': dm[1], 'search_month': dm[1][:7], 'scope': '', 'manufacturer_obligation': '',
            'summary': 'MDSAP Audit Approach. 원문 개정 이력은 아래 근거 참조 (Jina Reader 제3자 텍스트 추출).',
            'summary_status': 'source_extracted', 'gap_analysis': '',
            'revision_evidence': {'status': 'revision_history', 'current_url': url,
                'sections': [{'title': 'Summary of Changes from Prior Revisions — Jina Reader 제3자 추출 텍스트 (PDF 바이트 미검증)', 'quote': quote}]}}


def _feed(url):
    def parse(text):
        entries = ET.fromstring(text).findall('./channel/item')
        if not entries:
            raise ValueError('document feed empty or invalid')
        return entries[:10]

    try:
        return parse(_get(url))
    except Exception:
        for attempt in range(2):
            try:
                return parse(_get(url, reader=True, html=True))
            except Exception:
                if attempt == 1:
                    raise


def run_detailed(since_year=2026, since_month=1, max_items=10, today_only=False):
    items, errors = [], []
    sources = {'p0002': 'error', 'documents_rss': 'error', 'news_rss': 'error'}
    try:
        html = _detail()
        _, pdf = _attachment(html)
        text = _get(pdf, reader=True)
        items.append(parse_priority(html, text))
        sources['p0002'] = 'ok'
    except Exception as exc:
        errors.append('P0002 현재 확인 실패: ' + str(exc)[:200])
        # Only mark an existing identified record stale; never invent a version.
        for old in load_regulations():
            if old.get('publisher') == 'MDSAP' and re.fullmatch(r'MDSAP AU P0002\.\d{3}', old.get('doc_no', '')) and old.get('url') == LIBRARY_URL:
                stale = dict(old)
                stale['revision_evidence'] = {'status': 'discovery_incomplete', 'current_url': LIBRARY_URL, 'detail': errors[-1]}
                stale['summary_status'] = 'source_unavailable'
                items.append(stale)
    # Both RSS feeds are supplemental checks, not independently verified
    # regulatory changes. Never add their unverified entries to the ledger.
    for source, feed_url in (('documents_rss', RSS_URL), ('news_rss', NEWS_RSS_URL)):
        try:
            entries = _feed(feed_url)
            sources[source] = 'ok'
            if feed_url == NEWS_RSS_URL and items and items[0].get('revision_evidence', {}).get('status') == 'revision_history':
                current = int(items[0]['doc_no'].rsplit('.', 1)[-1])
                for entry in entries:
                    title = entry.findtext('title') or ''
                    match = re.search(r'\brevision\s+(\d{1,3})\b.*\baudit\s+approach\b', title, re.I)
                    if match and int(match[1]) > current:
                        errors.append(f'RSS 신규 개정 {match[1]} 발견: 상세 문서와 불일치')
                        sources[source] = 'error'
        except Exception as exc:
            sources[source] = 'error'
            errors.append('RSS 확인 실패 (' + feed_url + '): ' + str(exc)[:120])
    return items, FetchResult(False, error='; '.join(errors)) if errors else None, sources


def run(since_year=2026, since_month=1, max_items=10, today_only=False):
    """Keep the established two-value collector interface."""
    items, error, _ = run_detailed(since_year, since_month, max_items, today_only)
    return items, error
