from types import SimpleNamespace
from collectors.mdcg_revision import collect_revision_evidence

INDEX = 'https://health.ec.europa.eu/catalogue'
CURRENT = 'https://health.ec.europa.eu/document/download/current'
OLD = 'https://health.ec.europa.eu/document/download/old'


def test_history_with_exact_predecessor_retains_quotes_and_comparison():
    item = {'doc_no': 'MDCG 2020-16 rev.5', 'title': 'Guidance', 'url': INDEX}
    html = f'<table><tr><td>MDCG 2020-16 rev.5 <a href="{CURRENT}">PDF</a></td></tr><tr><td>MDCG 2020-16 rev.4 <a href="{OLD}">PDF</a></td></tr></table>'
    pages = {CURRENT: ('MDCG 2020-16 rev.5\nMDCG 2020-16 revision 5 changes\nRule 7 Clarification of the rationale\nand revision of examples\nMDCG 2020-16 revision 4 changes\nOld',), OLD: ('MDCG 2020-16 rev.4\nOld provision',)}
    ev = collect_revision_evidence(item, fetcher=lambda *a, **kw: SimpleNamespace(ok=True, text=html), downloader=lambda u: u.encode(), extractor=lambda u: pages[u.decode()])
    assert ev['previous_url'] == OLD
    assert ev['changes'] and ev['sections'][0]['quote'].startswith('MDCG 2020-16 revision 5 changes')
    assert 'Rule 7' in ev['sections'][0]['title'] and '근거' in ev['sections'][0]['title']


def test_history_does_not_invent_translation_for_unknown_text():
    item = {'doc_no': 'MDCG 2020-16 rev.5', 'title': 'Guidance', 'url': INDEX}
    html = f'<table><tr><td>MDCG 2020-16 rev.5 <a href="{CURRENT}">PDF</a></td></tr></table>'
    text = 'MDCG 2020-16 revision 5 changes\nDifferent provision amended\nMDCG 2020-16 revision 4 changes\nOld'
    ev = collect_revision_evidence(item, fetcher=lambda *a, **kw: SimpleNamespace(ok=True, text=html), downloader=lambda u: b'pdf', extractor=lambda b: (text,), searcher=lambda n: SimpleNamespace(status='no_results'))
    assert ev['sections'][0]['title'] == 'Page 1'
