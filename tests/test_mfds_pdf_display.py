import ast
from pathlib import Path
import pymupdf as fitz
import pytest
from collectors.mfds_pdf_display import render_pdf_pages, evidence_for_item, load_evidence_images


def test_persisted_evidence_matches_only_the_exact_official_notice():
    item = {'doc_no': '제2026-67호', 'url': 'https://www.mfds.go.kr/brd/m_207/view.do?seq=15196'}
    entry = evidence_for_item(item)
    assert entry['page'] == 5
    assert evidence_for_item({**item, 'url': 'https://evil.test/brd/m_207/view.do?seq=15196'}) is None
    assert evidence_for_item({**item, 'url': 'https://www.mfds.go.kr/brd/m_207/view.do?seq=15181'}) is None


def test_discovered_same_notice_pdf_evidence_is_accepted():
    item = {'url': 'https://www.mfds.go.kr/brd/m_207/view.do?seq=99', 'doc_no': 'test',
            'revision_evidence': {'status': 'revision_history', 'sections': [{
                'source_url': 'https://www.mfds.go.kr/brd/m_207/down.do?seq=99&file_seq=3',
                'page': 4, 'sha256': 'a'*64}]}}
    evidence = evidence_for_item(item)
    assert evidence and evidence['page'] == 4
    item['revision_evidence']['sections'][0]['source_url'] = 'https://www.mfds.go.kr/brd/m_207/down.do?seq=100&file_seq=3'
    assert evidence_for_item(item) is None


def test_tampered_evidence_cannot_trigger_network():
    item = {'doc_no': '제2026-67호', 'url': 'https://www.mfds.go.kr/brd/m_207/view.do?seq=15196'}
    entry = dict(evidence_for_item(item), source_url='http://127.0.0.1/')
    with pytest.raises(ValueError):
        load_evidence_images(item, entry)



def test_ui_displays_each_page_as_an_image():
    source = Path('app.py').read_text()
    tree = ast.parse(source)
    fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'render_mfds_pdf_evidence'), None)
    assert fn is not None
    calls = []
    class UI:
        def __getattr__(self, name):
            return lambda *a, **kw: calls.append((name, a, kw))
    ns = {'evidence_for_item': lambda item: {'source_url': 'https://www.mfds.go.kr/pdf'},
          'load_evidence_images': lambda item, evidence: [(5, b'page5'), (6, b'page6')]}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), 'app.py', 'exec'), ns)
    ns['render_mfds_pdf_evidence'](UI(), {})
    assert [args[0] for method, args, _ in calls if method == 'image'] == [b'page5', b'page6']
    assert 'render_mfds_pdf_evidence(st, selected_item)' in source


def test_render_original_pages_including_continuation():
    doc = fitz.open()
    for word in ('first', 'table start', 'continuation'):
        page = doc.new_page()
        page.insert_text((72, 72), word)
    data = doc.tobytes()
    images = render_pdf_pages(data, 2)
    assert [number for number, _ in images] == [2, 3]
    assert all(image.startswith(b'\x89PNG\r\n\x1a\n') for _, image in images)
