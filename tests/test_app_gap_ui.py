"""Guard removal of the old Gap and CanLII context displays."""
from pathlib import Path


def test_old_gap_panel_and_context_comparison_are_removed():
    source = (Path(__file__).resolve().parents[1] / 'app.py').read_text()
    assert 'CanLII Webdiff 스타일 문맥 비교' not in source
    assert '과거 규격 내용' not in source
    assert '현재 규격 내용' not in source
    assert 'render_revision_evidence(st, selected_item)' in source
