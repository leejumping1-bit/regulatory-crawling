from types import SimpleNamespace
from collectors.mdcg_revision import collect_revision_evidence


def test_specific_official_word_replacements_have_korean_explanation():
    item = {'doc_no': 'MDCG 2021-24 rev.1', 'url': 'https://health.ec.europa.eu/catalog'}
    html = '<table><tr><td>MDCG 2021-24 rev.1 <a href="/document/download/p">PDF</a></td></tr></table>'
    text = 'MDCG 2021-24 Rev 1 changes\n3.1.4 Invasiveness – Implantable devices Word ‘surgical’ was replaced with ‘clinical’\n3.2 Application of the classification rules Word ‘device’ was replaced with ‘product’\nMDCG 2021-24 Rev 0 changes\nOld'
    ev = collect_revision_evidence(item, fetcher=lambda *a, **kw: SimpleNamespace(ok=True, text=html), downloader=lambda u: b'pdf', extractor=lambda b: (text,))
    assert 'surgical → clinical' in ev['sections'][0]['title']
    assert 'device → product' in ev['sections'][0]['title']
    assert ev['sections'][0]['quote'].startswith('MDCG 2021-24 Rev 1 changes')
