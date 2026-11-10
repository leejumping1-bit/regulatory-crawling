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
    state = {'status': 'ok' if case == 'ok' else 'error', 'checked_at': stamp}
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
    inside = [x.value for x in list(source.warning) + list(source.success) + list(source.caption) if 'MDSAP' in x.value]
    assert len(inside) == 1
    message = inside[0]
    all_status = [x.value for x in list(app.warning) + list(app.success) + list(app.caption) if 'MDSAP' in x.value]
    assert all_status == inside
    if case == 'unknown':
        assert '확인 불가' in message
    elif case == 'stale' or (case == 'persisted' and now - datetime.fromisoformat(stamp) > timedelta(hours=48)):
        assert '오래됨' in message and stamp in message
    elif case == 'ok':
        assert '수집 완료' in message and stamp in message
        assert '전체 범위' in message
    else:
        assert f'MDSAP AU 수집 실패 · 확인 시각: {stamp}' in message
        assert '부분 수집' not in message
