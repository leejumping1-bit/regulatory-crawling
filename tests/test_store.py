import json

import pytest

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


def test_load_remote_regulations_accepts_persistent_list(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return [{"title": "from github"}]

    monkeypatch.setattr(store.requests, "get", lambda *args, **kwargs: Response())
    assert store.load_remote_regulations("https://example.test/data.json") == [{"title": "from github"}]


def test_load_remote_regulations_rejects_non_list(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"items": []}

    monkeypatch.setattr(store.requests, "get", lambda *args, **kwargs: Response())
    with pytest.raises(ValueError, match="not a list"):
        store.load_remote_regulations("https://example.test/data.json")

def test_mdcg_pdf_unavailable_retains_prior_summary(monkeypatch):
    old = {'publisher':'MDCG (EU)', 'doc_no':'MDCG 2020-16 rev.5', 'title':'Guidance', 'url':'https://example.test/a', 'summary':'verified', 'summary_status':'pdf_extracted'}
    new = dict(old, summary='[요약 오류]', summary_status='pdf_unavailable')
    result = store._retain_failed_collection(old, new)
    assert result['summary'] == 'verified'
    assert result['summary_retained_stale'] is True


def test_failed_recrawl_preserves_evidence_as_unverified_and_summary(monkeypatch):
    from tests.test_revision_ui import render, contents
    old = {"publisher": "MDCG (EU)", "doc_no": "MDCG 2020-16 rev.5", "title": "Guidance", "url": "https://example.test/a", "summary": "old summary", "summary_status": "source_extracted", "revision_evidence": {"status": "revision_history", "current_url": "https://example.test/doc", "sections": [{"quote": "old evidence"}]}}
    new = dict(old, summary="extraction failed", summary_status="source_unavailable", revision_evidence={"status": "discovery_incomplete", "detail": "network failure"})
    monkeypatch.setattr(store, "load_regulations", lambda: [old])
    monkeypatch.setattr(store, "save_regulations", lambda items: items)
    result = upsert_regulations([new])[0]
    assert result["summary"] == "old summary"
    evidence = result["revision_evidence"]
    assert evidence["status"] == "discovery_incomplete"
    assert evidence["retained_evidence"]["sections"][0]["quote"] == "old evidence"
    assert evidence["detail"] == "network failure"
    assert "old evidence" not in contents(render(result))


@pytest.mark.parametrize("field,value", [("title", "different"), ("url", "https://example.test/b"), ("doc_no", "other revision"), ("title", ""), ("publisher", "Other")])
def test_failed_recrawl_never_transfers_across_identity(monkeypatch, field, value):
    old = {"publisher": "MFDS (Korea)", "doc_no": "notice 1", "title": "title", "url": "https://example.test/a", "summary": "old", "summary_status": "source_extracted", "revision_evidence": {"status": "revision_history", "sections": [{"quote": "old"}]}}
    new = dict(old, summary="failure", summary_status="source_unavailable", revision_evidence={"status": "discovery_incomplete", "detail": "failure"})
    new[field] = value
    monkeypatch.setattr(store, "load_regulations", lambda: [old])
    monkeypatch.setattr(store, "save_regulations", lambda items: items)
    result = next(item for item in upsert_regulations([new]) if item is new or item == new)
    assert result["summary"] == "failure"
    assert "retained_evidence" not in result["revision_evidence"]


def test_repeated_failure_retains_once_and_success_replaces(monkeypatch):
    old = {"publisher": "MFDS (Korea)", "doc_no": "notice 1", "title": "title", "url": "https://example.test/a", "summary": "old", "summary_status": "source_extracted", "revision_evidence": {"status": "revision_history", "sections": [{"quote": "old"}]}}
    failure = dict(old, summary="failure", summary_status="source_unavailable", revision_evidence={"status": "discovery_incomplete", "detail": "failed"})
    stored = [old]
    monkeypatch.setattr(store, "load_regulations", lambda: stored[:])
    monkeypatch.setattr(store, "save_regulations", lambda items: stored.__setitem__(slice(None), items) or items)
    upsert_regulations([failure])
    upsert_regulations([failure])
    assert stored[0]["revision_evidence"]["retained_evidence"] == old["revision_evidence"]
    assert stored[0]["summary"] == "old"
    fresh = dict(old, summary="new", revision_evidence={"status": "revision_history", "sections": [{"quote": "new"}]})
    upsert_regulations([fresh])
    assert stored[0] == fresh


def test_summary_not_preserved_without_explicit_failure(monkeypatch):
    old = {"publisher": "MFDS (Korea)", "doc_no": "1", "title": "title", "url": "https://example.test/a", "summary": "old", "summary_status": "source_extracted"}
    new = dict(old, summary="", summary_status="source_extracted")
    monkeypatch.setattr(store, "load_regulations", lambda: [old])
    monkeypatch.setattr(store, "save_regulations", lambda items: items)
    assert upsert_regulations([new])[0]["summary"] == ""
