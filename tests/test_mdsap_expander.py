import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('filename', ['app.py', 'employee_app.py'])
@pytest.mark.parametrize('case', ['error', 'stale', 'unknown', 'ok', 'persisted'])
def test_mdsap_status_is_inside_source_expander(monkeypatch, filename, case):
    now = datetime.now(timezone.utc)
    stamp = (now - timedelta(hours=49) if case == 'stale' else now).isoformat()
    state = {'status': 'ok' if case in ('ok', 'stale') else 'error', 'checked_at': stamp}
    if case == 'persisted':
        state = json.loads((ROOT / 'data/mdsap_status.json').read_text())
        stamp = state['checked_at']

    class Response:
        def __init__(self, payload): self.payload = payload
        def raise_for_status(self): pass
        def json(self): return self.payload

    def get(url, **kwargs):
        if url.endswith('mdsap_status.json'):
            if case == 'unknown':
                raise requests.ConnectionError('offline')
            return Response(state)
        return Response([])

    monkeypatch.setattr(requests, 'get', get)
    st.cache_data.clear()
    app = AppTest.from_file(ROOT / filename).run(timeout=90)
    assert not app.exception
    source = next(x for x in app.expander if x.label == '데이터 출처 및 수집 안내')
    inside = [x.value for x in source.caption if 'MDSAP' in x.value]
    assert inside == [x.value for x in app.caption if 'MDSAP' in x.value]
    assert not any('MDSAP' in x.value for x in source.warning)
    text = '\n'.join(inside)
    assert '저장된 버전 없음' in text and 'https://www.mdsap.global/documents/library/audit-approach' in text
    outcome = state.get('sources', {}).get('p0002') if 'sources' in state else state.get('status')
    fresh = timedelta(0) <= now - datetime.fromisoformat(stamp) <= timedelta(hours=48)
    unverified = case == 'unknown' or outcome != 'ok' or not fresh
    assert ('MDSAP AU P0002 최신 여부 미확인 · 수동 확인 권장' in text) is unverified
    assert not any(word in text for word in ('실패', 'RSS', '수집 완료', '변경 없음'))
