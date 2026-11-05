import pytest


def test_grounding_disabled_even_with_key(monkeypatch):
    from collectors import grounded_discovery
    monkeypatch.setenv('GEMINI_API_KEY', 'present')
    calls = []
    with pytest.raises(grounded_discovery.GroundedDiscoveryError, match='disabled'):
        grounded_discovery.discover_links('MDCG', generate=lambda query: calls.append(query))
    assert calls == []


def test_default_search_uses_only_eu(monkeypatch):
    from collectors import mdcg_grounded_adapter as adapter
    monkeypatch.setenv('GEMINI_API_KEY', 'present')
    calls = []
    monkeypatch.setattr(adapter, 'discover_official_links', lambda number, revision: calls.append((number, revision)) or [])
    monkeypatch.setattr(adapter, 'discover_links', lambda *a, **k: pytest.fail('Google called'))
    assert adapter.discover_previous('MDCG 2020-16 rev.5').status == 'no_results'
    assert calls == [('2020-16', 4)]
