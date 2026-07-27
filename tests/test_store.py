from collectors.store import upsert_regulations


def test_mdcg_same_title_and_url_keeps_numbered_item(monkeypatch):
    old = [
        {"publisher": "MDCG (EU)", "doc_no": "", "title": "Same title", "url": "https://example.test/doc"},
        {"publisher": "Other", "doc_no": "1", "title": "Same title", "url": "https://example.test/doc"},
    ]
    saved = {}
    monkeypatch.setattr("collectors.store.load_regulations", lambda: old)
    monkeypatch.setattr("collectors.store.save_regulations", lambda items: saved.setdefault("items", items) or items)

    result = upsert_regulations([
        {"publisher": "MDCG (EU)", "doc_no": "MDCG 2026-5", "title": "Same title", "url": "https://example.test/doc"}
    ])

    mdcg = [x for x in result if x["publisher"] == "MDCG (EU)"]
    assert len(mdcg) == 1
    assert mdcg[0]["doc_no"] == "MDCG 2026-5"