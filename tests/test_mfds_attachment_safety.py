from collectors.mfds_revision import collect_revision_evidence

URL = 'https://www.mfds.go.kr/brd/m_209/view.do?seq=7'


def html(href):
    return f'<div class="bv_cont"></div><div class="bbs_file_cont"><strong>일부개정고시안.pdf</strong><a href="{href}">다운받기</a></div>'


def test_draft_label_and_unreadable_attachment_keep_exact_link():
    link = './down.do?seq=7&amp;file_seq=1'
    ev = collect_revision_evidence({'url': URL, 'title': '일부개정고시(안) 행정예고'},
        getter=lambda *a: html(link), downloader=lambda u: (_ for _ in ()).throw(ValueError('bad')))
    section = ev['sections'][0]
    assert '(개정안)' in section['title']
    assert section['page'] is None
    assert '쪽수 확인 실패' in section['quote']
    assert section['source_url'] == 'https://www.mfds.go.kr/brd/m_209/down.do?seq=7&file_seq=1'
    assert ev['status'] == 'discovery_incomplete'


def test_unrelated_notice_or_external_attachment_never_downloaded():
    for link in ('https://evil.example/brd/m_209/down.do?seq=7', './down.do?seq=8'):
        calls = []
        ev = collect_revision_evidence({'url': URL, 'title': '일부개정고시'},
            getter=lambda *a: html(link), downloader=lambda u: calls.append(u))
        assert not calls
        assert not ev.get('sections')
