from collectors.mfds_revision import parse_notice, backfill_items


def test_backfill_preserves_summary_and_existing_verified_evidence():
    old = {'status': 'revision_history', 'sections': [{'title': '기존', 'quote': '기존 근거'}]}
    items = [{'publisher': 'MFDS (Korea)', 'summary': '기존 요약', 'revision_evidence': old},
             {'publisher': 'MFDS (Korea)', 'summary': '보존', 'revision_evidence': {'status': 'discovery_incomplete'}},
             {'publisher': 'Other', 'summary': 'other'}]
    evidence = {'status': 'revision_history', 'sections': [{'title': '주요내용', 'quote': '확인'}]}
    result = backfill_items(items, collector=lambda item: evidence)
    assert result[0] == items[0]
    assert result[1] == dict(items[1], revision_evidence=evidence)
    assert result[2] == items[2]
    assert items[1]['revision_evidence']['status'] == 'discovery_incomplete'


def test_enactment_notice_referring_to_amended_law_is_not_an_amendment():
    html = '<div class="bv_cont">법 개정으로 제정합니다. &lt;주요내용&gt; 가. 세부 절차를 규정</div>'
    ev = parse_notice('https://www.mfds.go.kr/brd/m_209/view.do?seq=2', html, '규정 제정고시(안) 행정예고')
    assert ev['status'] == 'discovery_incomplete'


def test_inline_spans_do_not_insert_spaces_inside_words():
    html = '<div class="bv_cont"><p>&lt; 주요내용 &gt;</p><p>가. <span>한국의료기기</span><span>안전정보원</span>에서 교육함</p></div>'
    ev = parse_notice('https://www.mfds.go.kr/brd/m_207/view.do?seq=1', html, '규정 일부개정고시')
    assert '한국의료기기안전정보원' in ev['sections'][0]['quote']


def test_major_content_with_split_html_and_explicit_amendment():
    html = '<div class="bv_cont"><p>규정을 일부 개정하였음을 알려드립니다.</p><p>&lt; 주요내용 &gt;</p><p>가. 지정 갱신 절차를 정비함</p><p>나. 점검 범위를 조정함</p><p>&lt; 붙임 &gt;</p><p>첨부 안내</p></div>'
    ev = parse_notice('https://www.mfds.go.kr/brd/m_207/view.do?seq=1', html, '규정 일부개정고시')
    assert ev['status'] == 'revision_history'
    assert '갱신 절차를 정비함' in ev['sections'][0]['quote']
    assert '첨부 안내' not in ev['sections'][0]['quote']
