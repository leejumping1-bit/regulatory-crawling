from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_official_summary_provenance_is_displayed(monkeypatch):
    import requests
    import streamlit as st

    row = {'no': 1, 'publisher': 'MDCG (EU)', 'doc_no': 'MDCG 2026-6',
           'title': 'Example official guidance', 'url': 'https://health.ec.europa.eu/x',
           'search_month': '2026-01', 'summary': '공식 문서에 근거한 한글 요약입니다.',
           'summary_source': {'type': 'official_document_excerpt', 'url': 'https://health.ec.europa.eu/document/x'},
           'revision_evidence': {'status':'discovery_incomplete'}}
    class Response:
        def __init__(self, value): self.value = value
        def raise_for_status(self): pass
        def json(self): return self.value
    monkeypatch.setattr(requests, 'get', lambda url, **kw: Response({'status':'ok','checked_at':'2099-01-01T00:00:00+00:00'} if url.endswith('mdsap_status.json') else [row]))
    st.cache_data.clear()
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run(timeout=30)
    assert not app.exception
    assert any('요약 근거: 공식 문서에서 추출한 내용' in x.value for x in app.caption)
    assert any(x.proto.label == '요약 출처 열기' and x.proto.url == 'https://health.ec.europa.eu/document/x' for x in app.get('link_button'))
