from collectors.excerpt_summary import ExcerptSummarizer


def record(text='A medical device rule.', number='2026-1'):
    return {'publisher': 'FDA (US)', 'doc_no': number, 'url': 'https://www.federalregister.gov/documents/x', 'title': 'Device rule', 'summary': '[Federal Register 공식 초록 (영문)]\n' + text}


def test_new_summary_and_exact_reuse():
    calls = []
    def provider(payload):
        calls.append(payload)
        return {'identity': payload['identity'], 'summary_ko': '의료기기 규칙에 관한 내용입니다.'}
    engine = ExcerptSummarizer(provider=provider)
    first = engine.process(record(), None)
    assert first['summary'] == '의료기기 규칙에 관한 내용입니다.'
    assert first['summary_source']['text'] == 'A medical device rule.'
    assert first['summary_source']['type'] == 'official_abstract'
    second = engine.process(record(), first)
    assert second['summary'] == first['summary']
    assert len(calls) == 1


def test_changed_hash_or_identity_does_not_reuse_and_failures_are_stale():
    def provider(p):
        return {"identity": p["identity"], "summary_ko": "의료기기 규칙에 관한 내용입니다."}
    old = ExcerptSummarizer(provider).process(record(), None)
    engine = ExcerptSummarizer(lambda p: {"identity": "wrong", "summary_ko": "다른 문서의 잘못된 응답입니다."})
    changed = engine.process(record("A changed device rule."), old)
    assert changed["summary"] == old["summary"]
    assert changed["summary_retained_stale"] is True
    assert changed["summary_source"]["text"] == "A changed device rule."
    different = engine.process(record(number="2026-2"), old)
    assert different["summary"] != old["summary"]
    assert different["summary_status"] == "summary_unavailable"


def test_crawler_persists_generated_summary_on_partial_collection(monkeypatch):
    import crawler
    from collectors.http_utils import FetchResult
    saved = []
    fake = type("Module", (), {"run": staticmethod(lambda y, m: ([record()], FetchResult(False, error="incomplete")))})
    import collectors.excerpt_summary as excerpt_summary
    monkeypatch.setattr(excerpt_summary, "gemini_provider", lambda p: {"identity": p["identity"], "summary_ko": "의료기기 규칙에 관한 내용입니다."})
    monkeypatch.setattr(crawler.importlib, "import_module", lambda name: fake)
    monkeypatch.setattr(crawler, "load_regulations", lambda: list(saved))
    monkeypatch.setattr(crawler, "upsert_regulations", lambda rows: saved.extend(rows))
    crawler.run_crawler(only=["fda"])
    assert saved[0]["summary"] == "의료기기 규칙에 관한 내용입니다."
    assert saved[0]["summary_source"]["type"] == "official_abstract"


def test_mdsap_store_does_not_replace_changed_generated_summary():
    from collectors.store import _retain_failed_collection
    row = {'publisher':'MDSAP', 'doc_no':'MDSAP AU P0002.011', 'url':'https://www.mdsap.global/x', 'title':'Audit Approach', 'summary_status':'source_extracted', 'summary':'placeholder', 'revision_evidence':{'status':'revision_history', 'sections':[{'quote':'Original revision history text.'}]}}
    engine = ExcerptSummarizer(lambda p: {'identity':p['identity'], 'summary_ko':'이전 개정 내역을 설명하는 요약입니다.'})
    old = engine.process(row, None)
    updated = dict(row, revision_evidence={'status':'revision_history','sections':[{'quote':'Changed revision history text.'}]})
    engine.provider = lambda p: {'identity':p['identity'], 'summary_ko':'새 개정 내역을 설명하는 요약입니다.'}
    current = engine.process(updated, old)
    stored = _retain_failed_collection(old, current)
    assert stored['summary'] == '새 개정 내역을 설명하는 요약입니다.'


def test_crawler_reports_summary_generation_failure(monkeypatch):
    import crawler, collectors.excerpt_summary as mod
    saved = []
    fake = type('Module', (), {'run': staticmethod(lambda y,m: ([record()], None))})
    monkeypatch.setattr(mod, 'gemini_provider', lambda payload: (_ for _ in ()).throw(RuntimeError('secret')))
    monkeypatch.setattr(crawler.importlib, 'import_module', lambda name: fake)
    monkeypatch.setattr(crawler, 'load_regulations', lambda: saved)
    monkeypatch.setattr(crawler, 'upsert_regulations', lambda rows: saved.extend(rows))
    _, report = crawler.run_crawler(only=['fda'])
    assert '요약 미완료' in report['fda']
    assert 'secret' not in report['fda']


def test_budget_caps_calls_and_marks_exhausted():
    calls = []
    def provider(p):
        calls.append(p)
        return {'identity': p['identity'], 'summary_ko':'의료기기 규칙에 관한 내용입니다.'}
    engine = ExcerptSummarizer(provider, max_calls=100)
    results = [engine.process(record(number=str(i)), None) for i in range(31)]
    assert len(calls) == 30
    assert results[-1]['summary_status'] == 'summary_unavailable'


def test_first_publication_is_deterministic():
    row = {'publisher':'MHRA (UK)', 'doc_no':'MHRA-x', 'url':'https://www.gov.uk/x', 'summary':'[MHRA 공식 변경 설명 (영문)]\nFirst published.'}
    engine = ExcerptSummarizer(lambda p: (_ for _ in ()).throw(AssertionError('no call')))
    out = engine.process(row, None)
    assert out['summary'].startswith('최초 게시')
    assert engine.calls == 0
    assert out['summary_source']['text'] == 'First published.'


def test_mdsap_unavailable_source_retains_stale_summary():
    row = {'publisher':'MDSAP', 'doc_no':'MDSAP AU P0002.011', 'url':'https://www.mdsap.global/x', 'title':'Audit Approach', 'summary':'placeholder', 'revision_evidence':{'status':'revision_history', 'sections':[{'quote':'Revision history text.'}]}}
    engine = ExcerptSummarizer(lambda p: {'identity':p['identity'], 'summary_ko':'개정 내역을 설명하는 한국어 요약입니다.'})
    old = engine.process(row, None)
    new = dict(row, summary_status='source_unavailable', revision_evidence={'status':'discovery_incomplete'})
    result = engine.process(new, old)
    assert result['summary'] == old['summary']
    assert result['summary_retained_stale'] is True


def test_backfill_metadata_exact_match_avoids_provider_and_survives_store(monkeypatch, tmp_path):
    import json
    import collectors.store as store
    from collectors.excerpt_summary import identity, source
    original = record()
    excerpt = source(original)
    backfilled = dict(original, summary='공식 초록을 바탕으로 한 한국어 요약입니다.', summary_source=excerpt,
                      summary_provenance={'identity':identity(original), 'source_type':excerpt['type'], 'source_sha256':excerpt['sha256']})
    monkeypatch.setattr(store, 'DATA_PATH', str(tmp_path / 'regulations.json'))
    store.save_regulations([backfilled])
    engine = ExcerptSummarizer(lambda p: (_ for _ in ()).throw(AssertionError('provider should not be called')))
    prior = store.load_regulations()[0]
    result = engine.process(original, prior)
    store.upsert_regulations([result])
    assert store.load_regulations()[0]['summary'] == backfilled['summary']
    assert engine.calls == 0


def test_missing_key_reports_failure_without_fake_success(monkeypatch):
    from collectors.excerpt_summary import gemini_provider
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    engine = ExcerptSummarizer(gemini_provider)
    out = engine.process(record(), None)
    assert out['summary_status'] == 'summary_unavailable'
    assert out['summary'].startswith('[Federal Register 공식 초록 (영문)]')
    assert engine.failures == 1


def test_stale_reason_distinguishes_generation_failure_from_source_failure():
    original = record()
    old = ExcerptSummarizer(lambda p: {'identity': p['identity'], 'summary_ko':'원문에 근거한 한국어 요약 내용입니다.'}).process(original, None)
    engine = ExcerptSummarizer(lambda p: (_ for _ in ()).throw(RuntimeError('failure')))
    result = engine.process(record('Changed official abstract.'), old)
    assert result['summary_retained_stale_reason'] == 'generation_failed_or_deferred'
    assert result['summary'] == old['summary']
