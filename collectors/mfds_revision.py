"""Extract bounded MFDS-authored amendment descriptions, never infer a diff."""
import re
import hashlib
from urllib.parse import urlsplit, urljoin, parse_qs

import requests

from bs4 import BeautifulSoup
from collectors import regional_revision_evidence as regional
from collectors.revision_evidence import pdf_pages


def _download_pdf(url):
    response = requests.get(url, headers=regional.DEFAULT_HEADERS, timeout=20,
                            allow_redirects=False, stream=True)
    try:
        if response.status_code != 200 or response.url != url:
            raise ValueError('attachment response not exact')
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > 15 * 1024 * 1024:
                raise ValueError('attachment too large')
            chunks.append(chunk)
        data = b''.join(chunks)
        if not data.startswith(b'%PDF-'):
            raise ValueError('attachment is not a PDF')
        return data
    finally:
        response.close()


def _attachment_sections(url, html, title, downloader, pages):
    if '개정' not in title:
        return []
    notice = urlsplit(url)
    seq = parse_qs(notice.query).get('seq')
    if not seq or len(seq) != 1:
        return []
    soup = BeautifulSoup(html or '', 'html.parser')
    sections = []
    for container in soup.select('.bbs_file_cont'):
        name = container.find('strong')
        link = container.select_one('a[href*="down.do"]')
        if not name or not link:
            continue
        filename = name.get_text(strip=True)
        if not filename.lower().endswith('.pdf') or '개정' not in filename or '전문' in filename:
            continue
        target = urljoin(url, link.get('href', ''))
        parts = urlsplit(target)
        if (not regional._official('mfds', target) or parts.hostname != notice.hostname
                or parts.path != notice.path.replace('/view.do', '/down.do')
                or parse_qs(parts.query).get('seq') != seq):
            continue
        page = None
        digest = None
        try:
            data = downloader(target)
            digest = hashlib.sha256(data).hexdigest()
            if not data.startswith(b'%PDF-'):
                raise ValueError('not PDF')
            for number, text in enumerate(pages(data), 1):
                if re.search(r'신\s*[ㆍ·･.]?\s*구\s*조\s*문\s*대\s*비\s*표', text):
                    page = number
                    break
        except Exception:
            pass
        label = ('개정안' if '(안)' in title or '예고' in title else
                 '고시' if '고시' in title else '공고 상태 미확인')
        location = f'{page}쪽부터' if page else '쪽수 확인 실패'
        message = ('표의 좌우 문구를 재구성하지 않고 하단에 원본 페이지로 표시합니다.' if page
                   else '대비표 쪽수를 확인하지 못했습니다. 공식 PDF를 확인하세요.')
        sections.append({'title': f'신구조문대비표 확인 ({label})' if page else f'개정 첨부 PDF 확인 ({label})',
                         'quote': f'{filename}\n{location}. {message}\n{target}',
                         'source_url': target, 'page': page, 'sha256': digest if page else None})
        if len(sections) >= 4:
            break
    return sections


def parse_notice(url, html, title=''):
    incomplete = {'status': 'discovery_incomplete', 'current_url': url,
                  'detail': '공식 개정 주요내용 또는 이전 버전을 검증하지 못함'}
    if not regional._official('mfds', url) or urlsplit(url).path not in (
            '/brd/m_207/view.do', '/brd/m_209/view.do') or not html:
        return incomplete
    existing = regional.parse_revision_history('mfds', url, html)
    soup = BeautifulSoup(html, 'html.parser')
    bodies = soup.select('.bv_cont')
    if len(bodies) != 1:
        return incomplete
    body = bodies[0]
    for block in body.find_all(['p', 'br']):
        block.insert_after('\n')
    text = body.get_text('', strip=False)
    text = '\n'.join(re.sub(r'[^\S\n]+', ' ', line).strip() for line in text.splitlines()).strip()
    if not re.search(r'개정', title):
        return incomplete
    marker = re.search(r'(?:<\s*주요\s*내용\s*>|(?:^|\s)\d+\s*\.\s*주요\s*내용)', text)
    if marker:
        remainder = text[marker.end():]
        remainder = re.split(r'<\s*(?:붙임|첨부|참고|문의|향후계획)[^>]*>|(?:^|\s)\d+\s*\.\s*(?:의견\s*제출|참고\s*사항|붙임|행정\s*사항)', remainder, maxsplit=1)[0].strip(' :')
        remainder = re.sub(r'\n{3,}', '\n\n', remainder).strip(' :\n')
        if remainder and re.search(r'[가-하]\s*\.', remainder):
            label = '주요내용 (개정안)' if '개정' in title and ('(안)' in title or '예고' in title) else '주요내용'
            return {'status': 'revision_history', 'current_url': url,
                    'sections': [{'title': label, 'quote': remainder}]}
    return existing


def backfill_items(items, *, collector=None):
    collector = collector or collect_revision_evidence
    result = []
    for item in items:
        out = dict(item)
        existing = item.get('revision_evidence') or {}
        if item.get('publisher', '').startswith('MFDS') and existing.get('status') in (None, 'discovery_incomplete'):
            candidate = collector(item)
            if candidate.get('status') == 'revision_history':
                out['revision_evidence'] = candidate
        result.append(out)
    return result


def collect_revision_evidence(item, *, getter=None, downloader=None, pages=None):
    url = item.get('url', '')
    if not regional._official('mfds', url):
        return {'status': 'discovery_incomplete', 'current_url': url,
                'detail': '공식 MFDS 개정 공고 또는 법령 이전 버전 확인 미완료'}
    try:
        html = (getter or regional._get_exact)(url, 'mfds')
        title = item.get('title', '')
        result = parse_notice(url, html, title)
        attachments = _attachment_sections(url, html, title, downloader or _download_pdf, pages or pdf_pages)
        if attachments:
            if any(section['page'] for section in attachments):
                result['status'] = 'revision_history'
            result.setdefault('sections', []).extend(attachments)
        return result
    except Exception:
        return {'status': 'discovery_incomplete', 'current_url': url,
                'detail': '공식 원문 조회 또는 파싱 실패'}
