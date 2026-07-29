from collectors import health_canada


class _Response:
    ok = True
    robots_disallowed = False
    error = None

    def __init__(self, text):
        self.text = text


def test_full_text_uses_official_fulltext_page(monkeypatch):
    seen = []

    def fake_fetch(url):
        seen.append(url)
        return _Response("<html><main><h1>Section 1</h1><p>Current text</p></main></html>")

    monkeypatch.setattr(health_canada, "fetch", fake_fetch)
    text = health_canada._fetch_full_text(health_canada.REGULATION_URL)

    assert text == "Section 1\nCurrent text"
    assert seen == [health_canada.REGULATION_URL + "FullText.html"]


def test_article_context_is_readable_and_repeated_markers_are_collapsed():
    text = "[조항 36] 첫 문장; [조항 36] 둘째 문장\n\n[조항 37] 다음 조항"
    assert health_canada._deduplicate_article_markers(text) == (
        "[조항 36] 첫 문장; 둘째 문장\n\n[조항 37] 다음 조항"
    )