"""Extract bounded MFDS-authored amendment descriptions, never infer a diff."""
import re
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from collectors import regional_revision_evidence as regional


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


def collect_revision_evidence(item, *, getter=None):
    url = item.get('url', '')
    if not regional._official('mfds', url):
        return {'status': 'discovery_incomplete', 'current_url': url,
                'detail': '공식 MFDS 개정 공고 또는 법령 이전 버전 확인 미완료'}
    try:
        html = (getter or regional._get_exact)(url, 'mfds')
        return parse_notice(url, html, item.get('title', ''))
    except Exception:
        return {'status': 'discovery_incomplete', 'current_url': url,
                'detail': '공식 원문 조회 또는 파싱 실패'}
