from types import SimpleNamespace

from collectors import mdcg
from collectors.mdcg import _find_matching_attachment


TARGET_TITLE = "New MDCG Position Paper: UDI assignment between manufacturers and distributors"


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
