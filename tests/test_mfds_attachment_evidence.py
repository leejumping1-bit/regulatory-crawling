from collectors.mfds_revision import collect_revision_evidence

NOTICE = 'https://www.mfds.go.kr/brd/m_207/view.do?seq=15196'
PDF = 'https://www.mfds.go.kr/brd/m_207/down.do?brd_id=data0008&seq=15196&data_tp=A&file_seq=4'
HTML = '''<div class="bv_cont"><p>1. 개정이유</p><p>개정합니다.</p></div>
<div class="bbs_file_cont"><strong>일부개정고시.pdf</strong>
<a href="./down.do?brd_id=data0008&amp;seq=15196&amp;data_tp=A&amp;file_seq=4">다운받기</a></div>'''


def test_unreliable_table_provides_exact_official_attachment_link_and_page():
    evidence = collect_revision_evidence(
        {'url': NOTICE, 'title': '규정 일부개정고시'}, getter=lambda *a: HTML,
        downloader=lambda url: b'%PDF-test', pages=lambda data: ('본문', '신ㆍ구조문대비표\n현 행 개 정 안'))
    section = evidence['sections'][-1]
    assert evidence['status'] == 'revision_history'
    assert PDF in section['quote']
    assert '2쪽' in section['quote']
    assert '고시' in section['title']
    assert '자동 추출' in section['quote']
    assert section['source_url'] == PDF
    assert section['page'] == 2
    import hashlib
    assert section['sha256'] == hashlib.sha256(b'%PDF-test').hexdigest()
