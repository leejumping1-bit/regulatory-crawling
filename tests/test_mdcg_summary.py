from collectors import mdcg
from collectors.summarizer import summarize


def test_mdcg_detail_text_excludes_styles_scripts_and_jsonld():
    html = """
    <html><head><style>.bad-css { color: red; }</style>
    <script>{\"fake\": true}</script></head>
    <body><nav>Navigation</nav><main><h1>Monitoring of Notified Bodies</h1>
    <p>New MDR and IVDR reports are now available.</p></main></body></html>
    """
    text = mdcg._visible_detail_text(html)
    assert "Monitoring of Notified Bodies" in text
    assert "New MDR and IVDR reports" in text
    assert "bad-css" not in text
    assert "fake" not in text
    assert "Navigation" not in text


def test_rule_summary_is_korean_and_detailed():
    result = summarize(
        "Monitoring of Notified Bodies: new MDR and IVDR reports",
        "Member States summaries of annual reports on monitoring and on-site assessment of notified bodies in 2025 are now available. The reports cover MDR and IVDR notified bodies.",
    )
    assert "핵심 내용" in result
    assert "실무 검토" in result
    assert len(result) >= 300


def test_short_llm_result_is_not_used_as_final_summary(monkeypatch):
    monkeypatch.setattr("collectors.summarizer._llm_summary", lambda title, body: "짧은 요약")
    result = summarize("제목", "원문 내용이 충분히 긴 문장입니다. 적용 범위와 검토사항을 확인해야 합니다.")
    assert result != "짧은 요약"
    assert "핵심 내용" in result
