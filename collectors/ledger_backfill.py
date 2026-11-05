"""Conservative existing-ledger evidence backfill; leaves all other fields intact."""
from urllib.parse import urldefrag

from collectors.regional_revision_evidence import collect_revision_evidence
from collectors.mdcg_revision import collect_revision_evidence as collect_mdcg, _identity

KINDS = {'MFDS (Korea)': 'mfds', 'MHRA (UK)': 'mhra', 'Health Canada': 'health_canada'}


def backfill_items(items, *, regional=collect_revision_evidence, mdcg=collect_mdcg):
    output = []
    for item in items:
        result = dict(item)
        kind = KINDS.get(item.get('publisher'))
        existing = item.get('revision_evidence') or {}
        retry = not existing or existing.get('status') == 'discovery_incomplete'
        identity = _identity(item.get('doc_no', ''))
        candidate = None
        if kind and retry:
            candidate = regional(kind, urldefrag(item.get('url', ''))[0])
        elif item.get('publisher') == 'MDCG (EU)' and identity and identity[1] and retry:
            candidate = mdcg(item)
        if candidate and (not existing or candidate.get('status') != 'discovery_incomplete'):
            result['revision_evidence'] = candidate
        output.append(result)
    return output
