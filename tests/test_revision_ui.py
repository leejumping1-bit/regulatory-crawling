"""Section 03 renders only explicitly verified, sourced revision evidence."""
import ast
from pathlib import Path
from urllib.parse import urlsplit

APP = Path(__file__).resolve().parents[1] / "app.py"


class Recorder:
    def __init__(self):
        self.events = []

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.events.append((name, args, kwargs))
        return record


def render(item):
    # Load the real renderer without executing Streamlit's top-level app or network.
    tree = ast.parse(APP.read_text())
    fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef)
               and n.name == "render_revision_evidence"), None)
    assert fn is not None, "section 03 needs an evidence renderer"
    ns = {"urlsplit": urlsplit}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(APP), "exec"), ns)
    ui = Recorder()
    ns["render_revision_evidence"](ui, item)
    return ui.events


def contents(events):
    return "\n".join(str(arg) for _, args, _ in events for arg in args)


def test_legacy_gap_is_not_claimed_as_verified():
    output = contents(render({"gap_analysis": {"past_text": "NO CHANGE", "present_text": "fake"}}))
    assert "검증되지" in output
    assert "NO CHANGE" not in output and "fake" not in output


def test_sourced_revision_history_preserves_exact_quote():
    quote = "Revision 3\n  • Changed <A> & B"
    events = render({"revision_evidence": {"status": "revision_history", "current_url": "https://agency.gov/current", "sections": [{"title": "Revision history", "quote": quote}]}})
    assert ("text", (quote,), {}) in events
    assert "https://agency.gov/current" in contents(events)


def test_verified_comparison_requires_both_sources_and_shows_explanation():
    evidence = {"status": "verified_comparison", "previous_available": True, "previous_url": "https://agency.gov/old", "current_url": "https://agency.gov/new", "explanation": "항목 A가 추가됨"}
    output = contents(render({"revision_evidence": evidence}))
    assert all(s in output for s in ["항목 A가 추가됨", evidence["previous_url"], evidence["current_url"]])
    del evidence["previous_url"]
    output = contents(render({"revision_evidence": evidence}))
    assert "검증되지" in output and "항목 A가 추가됨" not in output


def test_previous_explicitly_unavailable_is_not_no_change():
    output = contents(render({"revision_evidence": {"status": "previous_unavailable", "previous_available": False, "current_url": "https://agency.gov/new"}}))
    assert "이전 버전: 찾을 수 없음" in output
    assert "변경 없음" not in output
    assert "https://agency.gov/new" in output


def test_incomplete_search_reports_coverage_not_absence():
    output = contents(render({"revision_evidence": {"status": "discovery_incomplete", "current_url": "https://agency.gov/new", "detail": "Official-site discovery not completed"}}))
    assert "이전 버전 확인 실패" in output
    assert "찾을 수 없음" not in output
    assert "https://agency.gov/new" in output


def test_external_archived_comparison_shows_changes_and_does_not_claim_official_host():
    evidence = {'status': 'archived_comparison', 'previous_available': False,
        'issuer_previous_status': 'search_incomplete',
        'previous_url': 'https://lne-gmed.com/archive.pdf', 'current_url': 'https://health.ec.europa.eu/current.pdf',
        'changes': [{'before': 'October 2026', 'after': 'December 2026', 'before_page': 2, 'after_page': 2}]}
    output = contents(render({'revision_evidence': evidence}))
    assert '외부 보관본' in output
    assert 'October 2026' in output and 'December 2026' in output
    assert '이전 버전 확인 실패' in output
    assert 'lne-gmed.com/archive.pdf' in output
    assert '이전 버전: 찾을 수 없음' not in output


def test_section_03_uses_renderer_and_section_02_keeps_summary():
    source = APP.read_text()
    section_02, section_03 = source.split("# ==================== 3.")
    assert 'selected_item.get("summary")' in section_02
    assert "render_revision_evidence(st, selected_item)" in section_03
    assert 'gap_data.get("past_text")' not in section_03
