from types import SimpleNamespace
from collectors.mdcg_revision import collect_revision_evidence, backfill_items

INDEX = 'https://health.ec.europa.eu/catalog'
CURRENT = 'https://health.ec.europa.eu/document/download/current'
OLD = 'https://health.ec.europa.eu/document/download/old'
ITEM = {'publisher': 'MDCG (EU)', 'doc_no': 'MDCG 2020-16 rev.5', 'title': 'MDCG 2020-16 rev.5: Guidance', 'url': INDEX, 'summary': 'keep', 'summary_status': 'pdf_extracted'}

def response(html):
    return SimpleNamespace(ok=True, text=html, error=None)

def test_explicit_history_is_verbatim_and_backfill_preserves_other_fields():
    html = f'<table><tr><td>MDCG 2020-16 rev.5 <a href="{CURRENT}">PDF</a></td><td>Guidance</td></tr></table>'
    text = 'MDCG 2020-16 revision 5 changes\nRule 7 Clarification of the rationale\nMDCG 2020-16 revision 4 changes\nOld'
    result = backfill_items([ITEM], fetcher=lambda *a, **k: response(html), downloader=lambda u: b'pdf', extractor=lambda b: (text,))[0]
    ev = result['revision_evidence']
    assert ev['status'] == 'revision_history'
    assert ev['sections'][0]['quote'] == 'MDCG 2020-16 revision 5 changes\nRule 7 Clarification of the rationale\n'
    assert ev['current_url'] == CURRENT
    assert result['summary'] == 'keep' and result['summary_status'] == 'pdf_extracted' and result['url'] == INDEX

def test_prior_official_revision_is_compared():
    html = f'<table><tr><td>MDCG 2020-16 rev.5 <a href="{CURRENT}">PDF</a></td><td>Guidance</td></tr><tr><td>MDCG 2020-16 rev.4 <a href="{OLD}">PDF</a></td><td>Guidance</td></tr></table>'
    def extract(b):
        return ('MDCG 2020-16 rev.' + ('5\nnew' if b == b'current' else '4\nold'),)
    ev = collect_revision_evidence(ITEM, fetcher=lambda *a, **k: response(html), downloader=lambda u: u.rsplit('/', 1)[-1].encode(), extractor=extract)
    assert ev['status'] == 'verified_comparison' and ev['previous_url'] == OLD
    assert 'old' in ev['explanation'] and 'new' in ev['explanation']

def test_failed_discovery_does_not_claim_missing_and_preserves_verified():
    old = {'status': 'revision_history', 'current_url': CURRENT, 'sections': [{'title': 'History', 'quote': 'Original'}]}
    item = dict(ITEM, revision_evidence=old)
    result = backfill_items([item], fetcher=lambda *a, **k: SimpleNamespace(ok=False, error='network'))[0]
    assert result['revision_evidence']['status'] == 'discovery_incomplete'
    assert result['summary'] == 'keep'
    ev = collect_revision_evidence(ITEM, fetcher=lambda *a, **k: SimpleNamespace(ok=False, error='network'))
    assert ev['status'] == 'discovery_incomplete' and ev.get('previous_available') is not False


def test_appendix_selects_only_appendix_row():
    item = dict(ITEM, doc_no='MDCG 2021-5 rev.1', title='MDCG 2021-5 rev.1 - Appendix: Transition')
    html = f'<table><tr><td>MDCG 2021-5 rev.1 <a href="{OLD}">PDF</a></td><td>Guidance</td></tr><tr><td>MDCG 2021-5 rev.1 - Appendix <a href="{CURRENT}">PDF</a></td><td>Transition</td></tr></table>'
    text = 'MDCG 2021-5 rev.1\nMDCG 2021-5 revision 1 changes\nAppendix text updated\nMDCG 2021-5 revision 0 changes\nold'
    ev = collect_revision_evidence(item, fetcher=lambda *a, **k: response(html), downloader=lambda u: b'pdf', extractor=lambda b: (text,))
    assert ev['status'] == 'revision_history' and ev['current_url'] == CURRENT


def test_grounded_search_predecessor_is_compared_after_catalogue_miss():
    from collectors.mdcg_grounded_adapter import DiscoveryResult
    from collectors.revision_evidence import DocumentVersion
    html = f'<table><tr><td>MDCG 2020-16 rev.5 <a href="{CURRENT}">PDF</a></td></tr></table>'
    previous = DocumentVersion('MDCG 2020-16', 4, OLD, ('MDCG 2020-16 rev.4\nold rule',))
    calls = []
    def search(doc_no):
        calls.append(doc_no)
        return DiscoveryResult('verified', official=(previous,))
    ev = collect_revision_evidence(ITEM, fetcher=lambda *a, **k: response(html), downloader=lambda u: b'pdf', extractor=lambda b: ('MDCG 2020-16 rev.5\nnew rule',), searcher=search)
    assert calls == [ITEM['doc_no']]
    assert ev['status'] == 'verified_comparison' and ev['previous_url'] == OLD
    assert 'old rule' in ev['explanation'] and 'new rule' in ev['explanation']


def test_current_revision_table_ending_at_page_with_next_page_contents():
    html = f'<table><tr><td>MDCG 2020-16 rev.5 <a href="{CURRENT}">PDF</a></td><td>Guidance</td></tr></table>'
    pages = ('MDCG 2020-16 rev.5\nMDCG 2020-16 revision 5 changes\nRule 7 Updated', 'Table of contents\n1 Purpose')
    ev = collect_revision_evidence(ITEM, fetcher=lambda *a, **k: response(html), downloader=lambda u: b'pdf', extractor=lambda b: pages)
    assert ev['status'] == 'revision_history'
    assert ev['sections'][0]['quote'] == 'MDCG 2020-16 revision 5 changes\nRule 7 Updated'


def test_default_network_restricts_redirects_to_issuer(monkeypatch):
    from collectors import mdcg_revision
    calls = []
    monkeypatch.setattr(mdcg_revision, 'fetch', lambda url, **kwargs: calls.append(kwargs) or SimpleNamespace(ok=False))
    mdcg_revision._fetch_official(INDEX, respect_robots=False)
    assert calls[0]['allowed_hosts'] == {'health.ec.europa.eu'}


def test_replaced_pdf_same_url_is_retrieved_hashed_and_reanalyzed():
    import hashlib
    html = f'<table><tr><td>MDCG 2020-16 rev.5 <a href="{CURRENT}">PDF</a></td></tr></table>'
    def extract(data):
        return (f'MDCG 2020-16 revision 5 changes\n{data.decode()}\nMDCG 2020-16 revision 4 changes\nOld',)
    kwargs = dict(fetcher=lambda *a, **k: response(html), extractor=extract)
    first = backfill_items([ITEM], downloader=lambda u: b'Original change text', **kwargs)[0]
    second = backfill_items([first], downloader=lambda u: b'Replaced change text', **kwargs)[0]
    assert second['revision_evidence']['current_pdf_sha256'] == hashlib.sha256(b'Replaced change text').hexdigest()
    assert 'Replaced change text' in second['revision_evidence']['sections'][0]['quote']
    assert second['summary'] == 'keep'
