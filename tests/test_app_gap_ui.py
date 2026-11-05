"""Exercise the Streamlit gap panel without loading remote data or Streamlit."""
import ast
from contextlib import nullcontext
from pathlib import Path


def test_gap_panel_shows_past_and_present_without_context_comparison():
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text()
    tree = ast.parse(source)
    panel = next(
        node for node in tree.body
        if isinstance(node, ast.With)
        and any(isinstance(child, ast.Name) and child.id == "gap_data"
                for child in ast.walk(node))
    )
    output = []

    class StreamlitRecorder:
        def container(self, **kwargs):
            return nullcontext()

        def columns(self, count):
            return [nullcontext() for _ in range(count)]

        def markdown(self, text, **kwargs):
            output.append(text)

        def caption(self, text):
            output.append(text)

        def info(self, text):
            output.append(text)

        def success(self, text):
            output.append(text)

    exec(compile(ast.Module(body=[panel], type_ignores=[]), "app.py", "exec"), {
        "st": StreamlitRecorder(),
        "render_html": output.append,
        "selected_item": {"gap_analysis": {
            "past_text": "Old provision",
            "present_text": "New provision",
            "diff_html": "UNWANTED_DIFF_MARKER",
        }},
    })
    rendered = "\n".join(output)
    assert "Gap 분석" in rendered
    assert "과거 규격 내용" in rendered and "Old provision" in rendered
    assert "현재 규격 내용" in rendered and "New provision" in rendered
    assert "CanLII" not in rendered
    assert "UNWANTED_DIFF_MARKER" not in rendered
