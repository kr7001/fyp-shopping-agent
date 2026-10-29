#!/usr/bin/env python3
"""Dated, separately authorised matched-briefing launcher; reuses tested process guard."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import guarded_replication as original

STUDY = 'matched-briefing-2026-10-29'
LATEST = dt.datetime.fromisoformat('2026-10-30T12:00:00+08:00')
CAP = 10.0


def validate_config(path):
    cfg = json.loads(Path(path).read_text())
    if cfg.get('study_id') != STUDY or cfg.get('round') != 1 or 'prior_round' in cfg:
        raise original.Stop('wrong supplementary study or budget scope')
    if original.number(cfg.get('cap_usd')) != CAP:
        raise original.Stop('supplementary study cap must be USD10')
    deadline = dt.datetime.fromisoformat(cfg['deadline'])
    if deadline.tzinfo is None or deadline > LATEST:
        raise original.Stop('supplementary deadline exceeds verified design')
    root = Path(cfg['repo'])
    protocol_path = root / cfg['protocol']
    protocol = json.loads(protocol_path.read_text())
    if (protocol.get('study_id') != STUDY or protocol.get('status') != 'frozen'
            or cfg['hashes'].get(cfg['protocol']) != original.sha(protocol_path)):
        raise original.Stop('supplementary protocol is not frozen and bound')
    paid = [step for step in cfg['steps'] if step['kind'] == 'paid']
    if len(paid) != 16 or [s.get('study_slot') for s in paid] != protocol['schedule']:
        raise original.Stop('paid schedule differs from the sixteen original slots')
    return cfg, protocol


def check_key_context(root, environment=None):
    """Fail closed on different parser, monitor or executor keys; never print them."""
    environment = os.environ if environment is None else environment
    paths = [Path(root) / '.env', Path(root) / 'agent/agent-core/.env']
    sources = []
    for path in paths:
        values = {}
        for line in path.read_text().splitlines():
            match = re.match(r'\s*(?:export\s+)?([A-Z_]+)\s*=\s*(.*?)\s*$', line)
            if match:
                name, raw = match.groups()
                if name in ('API_KEY', 'MODEL_API_KEY', 'OPENROUTER_API_KEY'):
                    if name in values:
                        raise original.Stop('ambiguous credential configuration')
                    values[name] = raw.strip('"\'')
        sources.append(values)
    # Match the frozen parser's exact root-file convention, not a new dotenv rule.
    raw = [line.split('=',1)[1].strip() for line in paths[0].read_text().splitlines()
           if line.startswith('OPENROUTER_API_KEY=')]
    if len(raw) != 1 or not raw[0] or raw[0] != sources[0].get('OPENROUTER_API_KEY'):
        raise original.Stop('parser and monitor credential conventions differ')
    canonical = raw[0]
    inherited = environment.get('OPENROUTER_API_KEY')
    if inherited and inherited != canonical:
        raise original.Stop('monitor credential differs from parser')
    effective = {**sources[1], **{k:v for k,v in environment.items() if v}}
    executor = next((effective[k].strip() for k in ('API_KEY','MODEL_API_KEY','OPENROUTER_API_KEY')
                     if effective.get(k)), None)
    if executor != canonical:
        raise original.Stop('executor credential differs from parser')


class MatchedGuard(original.Guard):
    def __init__(self, config_path, *, account_command=None):
        cfg, self.protocol = validate_config(config_path)
        # Constructor reads this constant once. Restore it even if it refuses.
        old = original.AUTHORIZED_DEADLINE
        try:
            original.AUTHORIZED_DEADLINE = LATEST
            super().__init__(config_path, account_command=account_command)
        finally:
            original.AUTHORIZED_DEADLINE = old
        self.protocol_sha = original.sha(self.repo / cfg['protocol'])

    def check_integrity(self):
        super().check_integrity()
        check_key_context(self.repo)

    def validate_output(self, step, logfile, before_dirs):
        output = super().validate_output(step, logfile, before_dirs)
        if step['kind'] == 'paid':
            data = json.loads(Path(output['output']).read_text())
            expected = step['study_slot']
            for stamp in [data] + data['rows']:
                if (stamp.get('study_id') != STUDY
                        or stamp.get('condition') != expected['arm']
                        or stamp.get('slot_id') != expected['slot']
                        or stamp.get('protocol_sha256') != self.protocol_sha):
                    raise original.Stop('completed output has wrong supplementary study identity')
        return output


def prepare_review(guard):
    """Offline work after the paid terminal end. No paid deadline is extended."""
    cfg, root = guard.config, guard.repo
    status_path = root / cfg['preparation_status']
    if status_path.exists():
        return 3
    try:
        if original.sha(guard.config_path) != guard.config_hash:
            raise original.Stop('configuration changed after paid completion')
        for path, expected in cfg['hashes'].items():
            if original.sha(root / path) != expected:
                raise original.Stop('immutable input changed before review preparation')
        receipt = json.loads((root / cfg['verification_receipt']).read_text())
        if (receipt.get('status') != 'PASS' or receipt.get('config_sha256') != guard.config_hash
                or receipt.get('head') != cfg['expected_head']):
            raise original.Stop('review preparation receipt differs')
        state = json.loads(guard.status_path.read_text())
        if state['status'] != 'complete' or state['completed_steps'] != [s['id'] for s in cfg['steps']]:
            raise original.Stop('paid schedule not complete')
        jobs = [
            [sys.executable, 'experiments/analysis/matched_briefing_analysis.py',
             '--protocol', cfg['protocol'], '--sheet', cfg['review_sheet'], cfg['manifest']],
            [sys.executable, 'tools/hand_review.py', '--sheet', cfg['review_sheet'],
             '--output', cfg['review_html']],
        ]
        logpath = root / cfg['preparation_log']
        with os.fdopen(os.open(logpath, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as log:
            for argv in jobs:
                result = subprocess.run(argv, cwd=root, stdin=subprocess.DEVNULL,
                                        stdout=log, stderr=subprocess.STDOUT, timeout=1200)
                if result.returncode:
                    raise original.Stop('offline review preparation failed; paid runs preserved')
        original.atomic_json(status_path, {'status':'complete', 'paid_runs_repeated':False,
            'sheet':cfg['review_sheet'], 'reader':cfg['review_html'],
            'config_sha256':guard.config_hash})
        return 0
    except Exception as exc:
        original.atomic_json(status_path, {'status':'failed', 'paid_runs_repeated':False,
            'reason':str(exc) if isinstance(exc,original.Stop) else type(exc).__name__,
            'config_sha256':guard.config_hash})
        return 3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--validate', action='store_true', help='check fixed scope and key alignment, no API call')
    args = parser.parse_args()
    try:
        cfg, _ = validate_config(args.config)
        check_key_context(cfg['repo'])
        if args.validate:
            print('Supplementary scope, frozen protocol and credential alignment checked; no API call.')
            return 0
        guard = MatchedGuard(args.config)
        result = guard.run()
        return result if result else prepare_review(guard)
    except Exception:
        print('Supplementary launcher refused configuration; no secret details printed.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
