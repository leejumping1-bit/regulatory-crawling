"""Render original MFDS attachment pages without extracting or rearranging text."""
import hashlib
import re
from urllib.parse import parse_qs, urlsplit

import pymupdf

# Verified against the official attachments. Digest pins the page numbers to those bytes.
_EVIDENCE = {
    '제2026-67호': {'seq': '15196', 'file_seq': '4', 'page': 5,
                    'sha256': '6ed7c4005a751c758c702264bd6f6c3173cb73a530167dd1b445b28cb2aa60f4'},
    '제2026-53호': {'seq': '15181', 'file_seq': '1', 'page': 6,
                    'sha256': '2220eef91fb82e4abee29dc519014c7b733b19d82c0e6ab48b45ec32546c05f9'},
}


def evidence_for_item(item):
    record = _EVIDENCE.get(item.get('doc_no'))
    if not record:
        try:
            notice = urlsplit(item.get('url', ''))
            seq = parse_qs(notice.query).get('seq')
            if notice.scheme != 'https' or notice.netloc != 'www.mfds.go.kr' or notice.path not in ('/brd/m_207/view.do', '/brd/m_209/view.do') or not seq or len(seq) != 1:
                return None
            evidence = item.get('revision_evidence') or {}
            if evidence.get('status') != 'revision_history':
                return None
            for section in evidence.get('sections', []):
                if not isinstance(section, dict):
                    continue
                source = section.get('source_url', '')
                target = urlsplit(source)
                page = section.get('page')
                digest = section.get('sha256')
                if (target.scheme == 'https' and target.netloc == 'www.mfds.go.kr'
                        and target.path == notice.path.replace('/view.do', '/down.do')
                        and parse_qs(target.query).get('seq') == seq
                        and isinstance(page, int) and not isinstance(page, bool) and page > 0
                        and isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{64}', digest)):
                    return {'source_url': source, 'page': page, 'sha256': digest}
        except (ValueError, TypeError, AttributeError):
            pass
        return None
    try:
        url = urlsplit(item.get('url', ''))
        if (url.scheme != 'https' or url.netloc != 'www.mfds.go.kr'
                or url.path != '/brd/m_207/view.do'
                or parse_qs(url.query).get('seq') != [record['seq']]):
            return None
    except (ValueError, TypeError):
        return None
    source = ('https://www.mfds.go.kr/brd/m_207/down.do?brd_id=data0008'
              f"&seq={record['seq']}&data_tp=A&file_seq={record['file_seq']}")
    return {'source_url': source, 'page': record['page'], 'sha256': record['sha256']}


def backfill_items(items):
    """Attach verified visual evidence to copies; never mutate the source ledger."""
    return [dict(item, mfds_pdf_evidence=evidence_for_item(item))
            if evidence_for_item(item) else dict(item) for item in items]


def load_evidence_images(item, evidence):
    # Never request a URL from ledger/user data. Only exact pinned records are allowed.
    expected = evidence_for_item(item)
    if expected is None or evidence != expected:
        raise ValueError('검증되지 않은 첨부파일 정보')
    from collectors.mfds_revision import _download_pdf
    data = _download_pdf(expected['source_url'])
    if hashlib.sha256(data).hexdigest() != expected['sha256']:
        raise ValueError('공식 PDF가 검증된 원본과 다릅니다')
    return render_pdf_pages(data, expected['page'])


def render_pdf_pages(data, start_page):
    with pymupdf.open(stream=data, filetype='pdf') as document:
        if not isinstance(start_page, int) or isinstance(start_page, bool) or not 1 <= start_page <= len(document):
            raise ValueError('PDF 시작 쪽수가 유효하지 않습니다')
        if len(document) - start_page + 1 > 20:
            raise ValueError('대비표 이후 쪽수가 너무 많아 자동 표시할 수 없습니다. 원본을 확인하세요.')
        return [(n + 1, document[n].get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False).tobytes('png'))
                for n in range(start_page - 1, len(document))]
