import pytest
from collectors.revision_evidence import DocumentVersion, build_evidence, pdf_pages


def doc(revision, text='text', url=None, document_id='MDCG 2022-9'):
    return DocumentVersion(document_id, revision, url or f'https://health.ec.europa.eu/{revision}.pdf', (text,))


def test_explicit_change_quote_is_verbatim_and_has_page_provenance():
    text = 'MDCG 2022-9 Rev.1 changes\nIntroduction\nClarification on when the SSP should be made available to patients.'
    current = doc(1, text)
    result = build_evidence(current, explicit_spans=[(1, 26, len(text))])
    assert result.status == 'explicit_change'
    assert result.quotes[0].text == text[26:]
    assert result.quotes[0].page == 1
    assert result.quotes[0].url == current.url


def test_unvalidated_template_is_not_change():
    assert build_evidence(doc(1, 'Revision history\nDate   Description'), discovery_complete=True).status == 'previous_not_found'


def test_invalid_quote_span_is_failure():
    assert build_evidence(doc(1), explicit_spans=[(1, 0, 100)]).status == 'extraction_failed'


def test_previous_must_be_same_issuer_site_not_archive():
    archive = doc(0, url='https://archive.org/official.pdf')
    result = build_evidence(doc(1), candidates=[archive], discovery_complete=True)
    assert result.status == 'previous_not_found'
    assert result.previous == '찾을 수 없음'


def test_discovery_failure_is_not_previous_not_found():
    assert build_evidence(doc(1)).status == 'discovery_incomplete'


def test_comparison_selects_immediate_previous_and_quotes_both():
    current = doc(3, 'A\nnew\nC')
    result = build_evidence(current, candidates=[doc(1, 'older'), doc(2, 'A\nold\nC')], discovery_complete=True)
    assert result.status == 'verified_change'
    assert result.previous == 'https://health.ec.europa.eu/2.pdf'
    assert result.changes[0].before == 'old'
    assert result.changes[0].after == 'new'
    assert result.changes[0].before_page == result.changes[0].after_page == 1


def test_same_text_is_no_change_and_missing_text_failure():
    assert build_evidence(doc(2), candidates=[doc(1)], discovery_complete=True).status == 'verified_no_change'
    assert build_evidence(doc(2, ''), candidates=[doc(1)], discovery_complete=True).status == 'extraction_failed'


def test_same_mutable_url_cannot_be_treated_as_two_versions():
    assert build_evidence(doc(2), candidates=[doc(1, url='https://health.ec.europa.eu/2.pdf')], discovery_complete=True).status == 'version_ambiguous'


def test_revision_gap_and_duplicate_are_ambiguous():
    assert build_evidence(doc(3), candidates=[doc(1)], discovery_complete=True).status == 'version_ambiguous'
    assert build_evidence(doc(2), candidates=[doc(1), doc(1, url='https://health.ec.europa.eu/other.pdf')], discovery_complete=True).status == 'version_ambiguous'


def test_invalid_pdf_is_extraction_failure():
    with pytest.raises(ValueError):
        pdf_pages(b'not a pdf')
