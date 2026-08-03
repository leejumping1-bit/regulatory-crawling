import json

from collectors import store
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


def test_save_regulations_writes_valid_json_and_backup(tmp_path, monkeypatch):
    data_path = tmp_path / "regulations.json"
    monkeypatch.setattr(store, "DATA_PATH", str(data_path))

    store.save_regulations([{"publish_date": "2026-08-03", "title": "old"}])
    store.save_regulations([{"publish_date": "2026-08-04", "title": "new"}])

    assert json.loads(data_path.read_text(encoding="utf-8"))[0]["title"] == "new"
    assert json.loads((tmp_path / "regulations.json.bak").read_text(encoding="utf-8"))[0]["title"] == "old"


def test_load_regulations_recovers_from_corrupt_primary(tmp_path, monkeypatch):
    data_path = tmp_path / "regulations.json"
    backup_path = tmp_path / "regulations.json.bak"
    data_path.write_text("[{\"broken\":", encoding="utf-8")
    backup_path.write_text('[{"title": "recovered"}]', encoding="utf-8")
    monkeypatch.setattr(store, "DATA_PATH", str(data_path))

    assert store.load_regulations() == [{"title": "recovered"}]