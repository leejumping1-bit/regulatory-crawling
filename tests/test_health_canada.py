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