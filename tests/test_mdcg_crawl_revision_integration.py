from collectors import mdcg


def test_crawl_does_not_transfer_main_evidence_to_appendix(monkeypatch):
    evidence = {'status': 'revision_history', 'current_url': 'https://health.ec.europa.eu/document/download/main', 'sections': [{'title': 'p1', 'quote': 'main change'}]}
    item = {'title': 'MDCG 2020-16 rev.5 - Appendix: Guidance', 'url': 'https://health.ec.europa.eu/catalog#appendix', 'pub_date': '2026-07'}
    monkeypatch.setattr(mdcg, '_crawl_feed', lambda *a, **k: ([], None))
    monkeypatch.setattr(mdcg, '_crawl_endorsed_index', lambda *a: [item])
    monkeypatch.setattr(mdcg, '_fetch_detail', lambda *a: ('body', 'OK'))
    monkeypatch.setattr(mdcg, 'load_previous_snapshot', lambda *a: None)
    monkeypatch.setattr(mdcg, 'save_snapshot', lambda *a: None)
    monkeypatch.setattr(mdcg, 'summarize', lambda *a: 'summary')
    monkeypatch.setattr(mdcg, 'load_regulations', lambda: [{'publisher': 'MDCG (EU)', 'doc_no': 'MDCG 2020-16 rev.5', 'title': 'MDCG 2020-16 rev.5: Guidance', 'revision_evidence': evidence}])
    monkeypatch.setattr(mdcg, 'backfill_items', lambda items: items)
    results, error = mdcg.run()
    assert not error and 'revision_evidence' not in results[0]
    assert results[0]['summary'] == 'summary'
