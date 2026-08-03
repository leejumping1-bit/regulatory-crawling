from types import SimpleNamespace

from collectors import mdcg
from collectors.mdcg import _document_identity, _find_matching_attachment
from collectors.mdcg import _extract_endorsed_items


TARGET_TITLE = "New MDCG 2026-5 Position Paper: UDI assignment between manufacturers and distributors"


def test_endorsed_documents_index_provides_numbered_mdcg_candidates():
    html = """
    <table>
      <tr><td><a href="/document/download/five?filename=mdcg_2026-5_en.pdf">MDCG 2026-5</a></td>
          <td>Position Paper: UDI assignment between manufacturers and distributors</td>
          <td>July 2026</td></tr>
      <tr><td><a href="/document/download/rev?filename=mdcg_2025-8_en.pdf">MDCG 2025-8 - rev.1</a></td>
          <td>Guidance on Master UDI-DI</td><td>March 2026</td></tr>
    </table>
    """
    items = _extract_endorsed_items(html, 2026, 1)
    assert items == [
        {
            "title": "New MDCG 2026-5 Position Paper: UDI assignment between manufacturers and distributors",
            "url": "https://health.ec.europa.eu/medical-devices-sector/new-regulations/guidance-mdcg-endorsed-documents-and-other-guidance_en#mdcg-2026-5",
            "pub_date": "2026-07",
        },
        {
            "title": "MDCG 2025-8 - rev.1: Guidance on Master UDI-DI",
            "url": "https://health.ec.europa.eu/medical-devices-sector/new-regulations/guidance-mdcg-endorsed-documents-and-other-guidance_en#mdcg-2025-8-rev-1",
            "pub_date": "2026-03",
        },
    ]


def test_collection_page_selects_attachment_from_matching_table_row():
    html = """
    <h2 id="sec18">Unique Device Identifier (UDI)</h2>
    <table><tbody>
      <tr><td><a href="/document/download/wrong?filename=article10a.pdf">MDCG 2024-1</a></td>
          <td>Q&amp;A on Article 10a</td></tr>
      <tr><td><a href="/document/download/right?filename=mdcg_2026-5_en.pdf">MDCG 2026-5</a></td>
          <td>Position Paper: UDI assignment between manufacturers and distributors</td></tr>
    </tbody></table>
    """
    assert _find_matching_attachment(html, TARGET_TITLE, "#sec18").endswith("filename=mdcg_2026-5_en.pdf")


def test_collection_page_fails_closed_when_title_has_no_matching_row():
    html = """
    <h2 id="sec18">Unique Device Identifier (UDI)</h2>
    <table><tbody>
      <tr><td><a href="/document/download/wrong?filename=article10a.pdf">MDCG 2024-1</a></td>
          <td>Q&amp;A on Article 10a</td></tr>
    </tbody></table>
    """
    assert _find_matching_attachment(html, TARGET_TITLE, "#sec18") is None


def test_news_and_catalog_titles_have_same_document_identity():
    assert _document_identity(
        "New MDCG Position Paper: UDI assignment between manufacturers and distributors"
    ) == _document_identity(TARGET_TITLE)


def test_collection_page_without_pdf_fails_closed(monkeypatch):
    html = "<h2 id='sec18'>UDI</h2><p>News announcement</p>"
    monkeypatch.setattr(mdcg, "fetch", lambda *args, **kwargs: SimpleNamespace(ok=True, text=html, error=None))
    body, status = mdcg._fetch_detail(
        "https://health.ec.europa.eu/medical-devices-sector/new-regulations/"
        "guidance-mdcg-endorsed-documents-and-other-guidance_en#sec18",
        TARGET_TITLE,
    )
    assert body == ""
    assert status == "PDF 첨부파일을 찾지 못함"


def test_fetch_detail_downloads_only_the_matching_row_attachment(monkeypatch):
    html = """
    <h2 id="sec18">Unique Device Identifier (UDI)</h2>
    <table><tbody>
      <tr><td><a href="/document/download/wrong?filename=article10a.pdf">MDCG 2024-1</a></td>
          <td>Q&amp;A on Article 10a</td></tr>
      <tr><td><a href="/document/download/right?filename=mdcg_2026-5_en.pdf">MDCG 2026-5</a></td>
          <td>Position Paper: UDI assignment between manufacturers and distributors</td></tr>
    </tbody></table>
    """
    requested = []
    monkeypatch.setattr(mdcg, "fetch", lambda *args, **kwargs: SimpleNamespace(ok=True, text=html, error=None))

    def fake_fetch_binary(url):
        requested.append(url)
        return b"pdf"

    monkeypatch.setattr(mdcg, "fetch_binary", fake_fetch_binary)
    monkeypatch.setattr(mdcg, "extract_text", lambda content, filename: ("UDI assignment source", "OK"))

    body, status = mdcg._fetch_detail(
        "https://health.ec.europa.eu/medical-devices-sector/new-regulations/"
        "guidance-mdcg-endorsed-documents-and-other-guidance_en#sec18",
        TARGET_TITLE,
    )

    assert body == "UDI assignment source"
    assert "mdcg_2026-5_en.pdf" in requested[0]
    assert "article10a.pdf" not in requested[0]
    assert status == "OK (제목 일치 행의 첨부 원문)"


def test_news_feed_preserves_exact_day_when_page_publishes_one():
    html = """
    <div>News announcement 1 July 2026
      <a href="/latest-updates/example-2026-07-01_en">June 2026 updated information on the applications for designation as a notified body</a>
    </div>
    """
    items = mdcg._extract_items(html)
    assert len(items) == 1
    assert items[0]["pub_date"] == "2026-07-01"
