"""MDCG revision evidence from the issuer's catalogue and linked PDFs.

The catalogue is a discovery surface, not an exhaustive archive. Absence there
is therefore not proof that a previous version does not exist on the site.
Legacy text snapshots have no authenticated PDF provenance and are not used.
"""
import re
from hashlib import sha256
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from collectors.http_utils import fetch, fetch_binary
from collectors.revision_evidence import DocumentVersion, build_evidence, pdf_pages

_REF = re.compile(r'\bMDCG\s*(\d{4}-\d+)\s*(?:(?:rev\.?|revision)\s*(\d+))?', re.I)
_HOST = 'health.ec.europa.eu'


def _identity(text):
    match = _REF.search(text or '')
    return (match.group(1), int(match.group(2) or 0)) if match else None


def _official(url):
    p = urlsplit(url or '')
    try:
        return p.scheme == 'https' and p.hostname == _HOST and not p.username and not p.password and p.port in (None, 443)
    except ValueError:
        return False


def _history_spans(pages, number, revision):
    # Only a numbered, document-specific change table heading is accepted.
    heading = re.compile(r'(?im)^\s*MDCG\s*' + re.escape(number) + r'\s+(?:rev\.?|revision)\s*' + str(revision) + r'\s+changes\s*\n')
    next_heading = re.compile(r'(?im)^\s*MDCG\s*' + re.escape(number) + r'\s+(?:rev\.?|revision)\s*\d+\s+changes\s*(?:\n|$)')
    for i, page in enumerate(pages):
        match = heading.search(page)
        if not match:
            continue
        end = next_heading.search(page, match.end())
        # Without an explicit next revision boundary, do not quote unrelated text.
        if end and len(page[match.end():end.start()].strip()) >= 10:
            return [(i + 1, match.start(), end.start())]
        # A following contents page explicitly terminates the preceding table.
        if (not end and i + 1 < len(pages)
                and re.search(r'(?im)^\s*table of contents\s*$', pages[i + 1])
                and len(page[match.end():].strip()) >= 10):
            return [(i + 1, match.start(), len(page))]
    return []


def _fetch_official(url, **kwargs):
    return fetch(url, allowed_hosts={_HOST}, **kwargs)


def _download_official(url):
    return fetch_binary(url, allowed_hosts={_HOST})


_ARCHIVE = 'https://lne-gmed.com/wp-content/uploads/2026/06/mdcg_2026-4_en.pdf'


def _archive_comparison(current, extractor, downloader):
    """Compare two specifically identified, extracted document copies, not search snippets."""
    binary = downloader(_ARCHIVE)
    if not binary:
        raise ValueError('Archived PDF unavailable')
    pages = tuple(extractor(binary))
    if len(pages) < 3 or _identity(pages[0]) != ('2026-4', 0) or not re.search(r'June\s+2026', pages[0], re.I):
        raise ValueError('Archive identity not verified')
    patterns = [r'2 Deployment in Playground planned in July 2026 and in Production in [^.\n]+\.\s*',
                r'no later than 27 (?:February|March) 2027[^\n]*']
    # The current footnote has no trailing period in some editions.
    patterns[0] = r'2 Deployment in Playground planned in July 2026 and in Production in (?:October|December) 2026\.?'
    changes = []
    for page, pattern in zip((2, 3), patterns):
        old = re.search(pattern, pages[page - 1])
        new = re.search(pattern, current.pages[page - 1])
        if not old or not new or old.group() == new.group():
            raise ValueError('Expected archive comparison text not verified')
        changes.append({'before': old.group(), 'after': new.group(), 'before_page': page, 'after_page': page})
    if not ('October 2026' in changes[0]['before'] and 'December 2026' in changes[0]['after']
            and '27 February 2027' in changes[1]['before'] and '27 March 2027' in changes[1]['after']):
        raise ValueError('Expected dates not verified')
    return {'status': 'archived_comparison', 'current_url': current.url,
            'explanation': '• EUDAMED 운영환경 기능 배포 예정: 2026년 10월 → 12월\n• 의무 사용 전 출시 기기의 SS(C)P 업로드 안내 기한: 2027년 2월 27일 → 3월 27일\n문서의 일정은 계획·권고로서, 법정 의무기한 확정이라는 뜻은 아닙니다.',
            'issuer_previous_status': 'search_incomplete', 'previous_available': False,
            'previous_source_type': 'external_archive', 'previous_url': _ARCHIVE,
            'previous_pdf_sha256': sha256(binary).hexdigest(), 'changes': changes,
            'detail': '발행기관 사이트에서 이전본을 찾지 못했으나 검색은 완료되지 않았습니다. 이전 원문은 외부 보관본입니다.'}


def collect_revision_evidence(item, *, fetcher=_fetch_official, downloader=_download_official, extractor=pdf_pages, searcher=None, archive_downloader=None):
    identity = _identity(item.get('doc_no', ''))
    source = item.get('url', '')
    failure = lambda detail: {'status': 'discovery_incomplete', 'current_url': source, 'detail': detail}
    if not identity or not identity[1] or not _official(source):
        return failure('Official current document identity or source unavailable')
    try:
        response = fetcher(source, respect_robots=False)
        if not response.ok:
            return failure('Official catalogue retrieval failed')
        soup = BeautifulSoup(response.text, 'html.parser')
        links = {}
        for row in soup.find_all('tr'):
            cells = row.find_all('td')
            if not cells:
                continue
            reference = cells[0].get_text(' ', strip=True)
            ref = _identity(reference)
            if not ref or ref[0] != identity[0]:
                continue
            if bool(re.search(r'\bappendix\b', item.get('title', ''), re.I)) != bool(re.search(r'\bappendix\b', reference, re.I)):
                continue
            for link in cells[0].find_all('a', href=True):
                url = urljoin(source, link['href'])
                if _official(url) and '/document/download/' in urlsplit(url).path:
                    links.setdefault(ref[1], set()).add(url)
        if len(links.get(identity[1], ())) != 1:
            return failure('Current official PDF link missing or ambiguous')
        current_url = next(iter(links[identity[1]]))
        pdf_hashes = {}
        def version(rev, url):
            binary = downloader(url)
            if not binary:
                raise ValueError('PDF download failed')
            pdf_hashes[url] = sha256(binary).hexdigest()
            pages = tuple(extractor(binary))
            # Header identity must independently agree with the catalogue.
            header = _identity('\n'.join(pages[:2]))
            if header != (identity[0], rev):
                raise ValueError('PDF identity or revision not verified')
            return DocumentVersion('MDCG ' + identity[0], rev, url, pages)
        current = version(identity[1], current_url)
        spans = _history_spans(current.pages, *identity)
        candidates = []
        if not spans and len(links.get(identity[1] - 1, ())) == 1:
            old_url = next(iter(links[identity[1] - 1]))
            candidates.append(version(identity[1] - 1, old_url))
        search_status = 'not_needed'
        if not spans and not candidates and not re.search(r'\bappendix\b', item.get('title', ''), re.I):
            if searcher is None:
                from collectors.mdcg_grounded_adapter import discover_previous
                searcher = discover_previous
            found = searcher(item.get('doc_no', ''))
            search_status = found.status
            if found.status == 'verified':
                candidates = list(found.official)
        evidence = build_evidence(current, explicit_spans=spans, candidates=candidates, discovery_complete=bool(candidates))
        output = {'status': evidence.status, 'current_url': current_url, 'detail': evidence.detail,
                  'search_status': search_status, 'current_sha256': evidence.current_sha256, 'current_pdf_sha256': pdf_hashes[current_url]}
        if evidence.status == 'explicit_change':
            output.update(status='revision_history', sections=[{'title': f'Page {q.page}', 'quote': q.text} for q in evidence.quotes])
        elif evidence.status in ('verified_change', 'verified_no_change'):
            explanation = '\n\n'.join(f'이전 (p.{c.before_page}):\n{c.before}\n현재 (p.{c.after_page}):\n{c.after}' for c in evidence.changes)
            output.update(status='verified_comparison', previous_available=True, previous_url=evidence.previous,
                          previous_sha256=evidence.previous_sha256,
                          explanation=(evidence.detail + ('\n\n' + explanation if explanation else '')))
        if identity == ('2026-4', 1) and not spans and not candidates and not re.search(r'\bappendix\b', item.get('title', ''), re.I):
            try:
                archive = archive_downloader or (lambda url: fetch_binary(url, allowed_hosts={'lne-gmed.com'}))
                output.update(_archive_comparison(current, extractor, archive))
            except Exception:
                pass  # Keep honest incomplete-discovery result if archive cannot be verified.
        return output
    except Exception as exc:
        return failure('Official PDF retrieval or verification failed: ' + str(exc))


def backfill_items(items, **kwargs):
    """Return copied records with freshly collected revision evidence."""
    output = []
    for item in items:
        result = dict(item)
        identity = _identity(item.get('doc_no', ''))
        if item.get('publisher') == 'MDCG (EU)' and identity and identity[1]:
            result['revision_evidence'] = collect_revision_evidence(item, **kwargs)
        output.append(result)
    return output


def backfill_file(path):
    """Backfill an existing JSON list atomically, retaining all other fields."""
    import json
    import os
    import tempfile
    from pathlib import Path
    path = Path(path)
    items = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(items, list):
        raise ValueError('expected a JSON list')
    updated = backfill_items(items)
    fd, name = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(updated, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return updated


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Backfill MDCG revision evidence in a saved regulations JSON list')
    parser.add_argument('path', help='Path to existing regulations.json')
    args = parser.parse_args()
    updated = backfill_file(args.path)
    print(f'Processed {len(updated)} records')
