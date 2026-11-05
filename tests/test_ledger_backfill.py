from collectors.ledger_backfill import backfill_items


def test_backfill_regional_records_without_touching_other_fields():
    items = [{'publisher': 'MFDS (Korea)', 'url': 'https://www.mfds.go.kr/brd/m_207/view.do?seq=1', 'summary': 'keep'}, {'publisher': 'other', 'summary': 'untouched'}]
    evidence = {'status': 'revision_history', 'sections': [{'title': '개정 이유', 'quote': '실제 원문'}]}
    result = backfill_items(items, regional=lambda kind, url: evidence)
    assert result[0] == dict(items[0], revision_evidence=evidence)
    assert result[1] == items[1]
    assert 'revision_evidence' not in items[0]


def test_retries_incomplete_mdcg_without_replacing_verified_evidence():
    items = [{'publisher': 'MDCG (EU)', 'doc_no': 'MDCG 2026-4 rev.1', 'revision_evidence': {'status': 'discovery_incomplete'}},
             {'publisher': 'MDCG (EU)', 'doc_no': 'MDCG 2021-24 rev.1', 'revision_evidence': {'status': 'revision_history'}}]
    result = backfill_items(items, mdcg=lambda item: {'status': 'archived_comparison'})
    assert result[0]['revision_evidence']['status'] == 'archived_comparison'
    assert result[1] == items[1]


def test_failed_retry_preserves_existing_diagnostic_evidence():
    item = {'publisher': 'MDCG (EU)', 'doc_no': 'MDCG 2026-4 rev.1',
            'revision_evidence': {'status': 'discovery_incomplete', 'detail': 'prior source diagnostic'}}
    result = backfill_items([item], mdcg=lambda _: {'status': 'discovery_incomplete', 'detail': 'transient error'})
    assert result[0] == item
