#!/usr/bin/env python3
"""Write a reviewable copy, never modify the input or overwrite output.

Run from repo root: python scripts/backfill_mfds_evidence.py data/regulations.json /tmp/mfds-review.json
Rerun against the latest ledger immediately before a separately reviewed merge.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collectors.mfds_revision import backfill_items, collect_revision_evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error('output must differ from input')
    raw = args.input.read_bytes()
    source_hash = hashlib.sha256(raw).hexdigest()
    items = json.loads(raw)
    if not isinstance(items, list):
        raise ValueError('input must be a JSON array')
    cache = {}
    def collect(item):
        key = (item.get('url'), item.get('title'))
        if key not in cache:
            cache[key] = collect_revision_evidence(item)
            time.sleep(1)
        return cache[key]
    result = backfill_items(items, collector=collect)
    if hashlib.sha256(args.input.read_bytes()).hexdigest() != source_hash:
        raise RuntimeError('input changed during collection; rerun on latest data')
    changed = [i for i, (a, b) in enumerate(zip(items, result)) if a != b]
    if any({k:v for k,v in a.items() if k != 'revision_evidence'} !=
           {k:v for k,v in b.items() if k != 'revision_evidence'} for a,b in zip(items,result)):
        raise RuntimeError('non-evidence fields changed')
    with args.output.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(json.dumps({'input_sha256': source_hash, 'mfds_records': sum(str(x.get('publisher','')).startswith('MFDS') for x in items),
                      'attempted_unique': len(cache), 'enhanced': len(changed),
                      'enhanced_record_nos': [items[i].get('no') for i in changed],
                      'unverified_attempts': sum(v.get('status') != 'revision_history' for v in cache.values()),
                      'output': str(args.output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
