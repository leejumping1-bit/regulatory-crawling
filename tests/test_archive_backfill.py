from types import SimpleNamespace
from collectors.mdcg_revision import collect_revision_evidence


def test_archive_comparison_remains_distinct_from_official_discovery():
    item = {'doc_no': 'MDCG 2026-4 rev.1', 'title': 'MDCG 2026-4 rev.1', 'url': 'https://health.ec.europa.eu/catalogue'}
    html = '<table><tr><td><a href="/document/download/current">MDCG 2026-4 rev.1</a></td></tr></table>'
    old = ('MDCG 2026-4\nJune 2026', '2 Deployment in Playground planned in July 2026 and in Production in October 2026.', 'Since manufacturers will only be able to upload SS(C)Ps from October 2026 onwards,\nno later than 27 February 2027')
    new = ('MDCG 2026-4 rev.1\nOctober 2026', '2 Deployment in Playground planned in July 2026 and in Production in December 2026', 'Since manufacturers will only be able to upload SS(C)Ps from December 2026 onwards,\nno later than 27 March 2027')
    result = collect_revision_evidence(item, fetcher=lambda *a, **k: SimpleNamespace(ok=True, text=html), downloader=lambda u: b'current', extractor=lambda b: new if b == b'current' else old, searcher=lambda n: SimpleNamespace(status='unavailable'), archive_downloader=lambda u: b'archive')
    assert result['status'] == 'archived_comparison'
    assert result['issuer_previous_status'] == 'search_incomplete'
    assert result['previous_source_type'] == 'external_archive'
    assert '27 February 2027' in result['changes'][1]['before']
    assert '27 March 2027' in result['changes'][1]['after']
    assert '2026년 10월 → 12월' in result['explanation']
    assert '2027년 2월 27일 → 3월 27일' in result['explanation']
