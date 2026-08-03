from collectors import pipeline


def test_build_item_does_not_summarize_title_without_source(monkeypatch):
    monkeypatch.setattr(pipeline, "fetch_detail_text", lambda url: ("", "PDF 원문을 찾지 못함"))
    monkeypatch.setattr(pipeline, "load_previous_snapshot", lambda *args: None)
    monkeypatch.setattr(pipeline, "save_snapshot", lambda *args: None)
    monkeypatch.setattr(pipeline, "generate_document_gap", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        pipeline,
        "summarize",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("title-only summary must not run")),
    )

    item = pipeline.build_item(
        "MDCG (EU)",
        "Document title",
        "https://example.test/document",
        "2026-07",
        "DOC-1",
    )

    assert item["summary_status"] == "source_unavailable"
    assert item["summary"].startswith("[요약 오류]")
    assert item["manufacturer_obligation"] == ""