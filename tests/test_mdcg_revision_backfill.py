import json
from collectors import mdcg_revision


def test_backfill_file_updates_only_evidence(tmp_path, monkeypatch):
    path = tmp_path / 'regulations.json'
    item = {'publisher': 'MDCG (EU)', 'doc_no': 'MDCG 2021-24 rev.1', 'summary': 'keep', 'url': 'https://health.ec.europa.eu/a'}
    path.write_text(json.dumps([item]), encoding='utf-8')
    monkeypatch.setattr(mdcg_revision, 'collect_revision_evidence', lambda *a, **k: {'status': 'discovery_incomplete', 'detail': 'failed'})
    mdcg_revision.backfill_file(path)
    result = json.loads(path.read_text(encoding='utf-8'))[0]
    assert result['summary'] == 'keep' and result['url'] == item['url']
    assert result['revision_evidence']['status'] == 'discovery_incomplete'
