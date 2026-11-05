from collectors.regional_revision_evidence import parse_revision_history, collect_revision_evidence


def test_mhra_history_preserves_latest_note_and_ignores_outside():
    html = '''<p>Outside</p><ol id="full-publication-update-history"><li class="gem-c-metadata__change-history-item"><time class="gem-c-metadata__change-date">20 February 2026</time><p class="gem-c-metadata__change-note">Updated A.\n\nRemoval of B.</p></li><li class="gem-c-metadata__change-history-item"><time class="gem-c-metadata__change-date">1 January 2020</time><p class="gem-c-metadata__change-note">First published.</p></li></ol><p>Footer</p>'''
    evidence = parse_revision_history('mhra', 'https://www.gov.uk/guidance/example', html)
    assert evidence['status'] == 'revision_history'
    assert evidence['sections'] == [{'title': '20 February 2026', 'quote': 'Updated A.\n\nRemoval of B.'}]


def test_mfds_official_notice_sections_are_bounded_and_verbatim():
    html = '<div class="bv_cont"><p>1. 개정이유 </p><p> 이유 그대로</p><p>2. 주요내용</p><p>가. 변경 내용</p><div><br></div><p>3. 참고사항</p><p>Not a change</p></div>'
    evidence = parse_revision_history('mfds', 'https://www.mfds.go.kr/brd/m_207/view.do?seq=1', html)
    assert evidence['status'] == 'revision_history'
    assert [s['quote'] for s in evidence['sections']] == [' 이유 그대로', '가. 변경 내용']


def test_missing_structure_or_untrusted_host_is_incomplete():
    assert parse_revision_history('mhra', 'https://www.gov.uk/guidance/a', '<p>Updated something</p>')['status'] == 'discovery_incomplete'
    assert parse_revision_history('mfds', 'https://www.mfds.go.kr.evil.test/a', '<div class="bv_cont"><p>1. 개정이유</p><p>change</p></div>')['status'] == 'discovery_incomplete'
    assert parse_revision_history('health_canada', 'https://laws-lois.justice.gc.ca/eng/regulations/sor-98-282/', '<p>Revision history</p>')['status'] == 'discovery_incomplete'


def test_failed_or_redirected_retrieval_is_incomplete():
    url = 'https://www.gov.uk/guidance/example'
    assert collect_revision_evidence('mhra', url, getter=lambda *a: None)['status'] == 'discovery_incomplete'


def test_mfds_generic_major_content_is_not_proof_of_revision():
    html = '<div class="bv_cont"><p>1. 주요내용</p><p>Some contents</p></div>'
    evidence = parse_revision_history('mfds', 'https://www.mfds.go.kr/brd/m_207/view.do?seq=1', html)
    assert evidence['status'] == 'discovery_incomplete'
