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
import time

import guarded_replication as original

STUDY = 'matched-briefing-2026-10-29'
LATEST = dt.datetime.fromisoformat('2026-10-30T12:00:00+08:00')
CAP = 10.0
# Every study this launcher may run, by its id: the latest deadline, the cap and the smallest
# in-flight reserve its design allows. The 29 October study keeps its own values. The fresh
# market's (notes/fresh-market-2-nov/protocol.md, 2 November 2026) has a USD 2 cap, so the
# replication guard's USD 1 reserve would stop it at USD 1; its USD 0.50 reserve is more than
# twice the 29 October study's largest trial charge, USD 0.194.
FRESH = 'matched-briefing-fresh-2026-11-02'
STUDIES = {
    STUDY: {'latest': LATEST, 'cap': CAP, 'min_reserve': 1.0},
    FRESH: {'latest': dt.datetime.fromisoformat('2026-11-03T12:00:00+08:00'), 'cap': 2.0, 'min_reserve': 0.5},
}
# Amendment 4, 2 November 2026 (notes/fresh-market-2-nov/amendment-4-2-nov.md): later stages of
# the fresh study, each its own launch after its own verifier pass, sharing one total cap of
# USD 2.75 with the primary run, whose counted spend each carries. A later stage runs the primary
# run's own steps unchanged and writes its own manifest, status and logs beside the primary's,
# which it never touches.
#   continuation  the primary run's steps it never completed (slot 16), after the same live check
FRESH_PRIMARY_CONFIG = 'notes/fresh-market-2-nov/study-b-command.json'
FRESH_PRIMARY_SHA256 = '507aea6cad5222ad7f3b3d8d421ee32be3bb5db34c7fd694cae5a188f6799a12'
FRESH_STEM = 'experiments/results/matched-briefing-fresh-2-nov'
CONTINUATION = 'continuation'
LATER = {CONTINUATION: {'manifest': f'{FRESH_STEM}.continuation.manifest',
                        'status': f'{FRESH_STEM}.continuation.status.json',
                        'log_dir': f'{FRESH_STEM}.continuation.logs'}}
# The thresholds, chosen 2 November 2026. A running trial stops when the counted spend, the
# carryover included, reaches the cap less the in-flight reserve, USD 2.50; a trial starts only
# while the counted spend plus twice its estimate stays below that. The largest charge of any
# trial of this study so far is USD 0.2498 (slot 7, at its 1800 s clock), so a trial started just
# below its threshold that charged that much, wholly unseen by the account until it ended, still
# ends below USD 2.75 (2.50 - 2 x 0.075 + 0.25 = 2.60 for slot 16). The primary run's USD 0.50
# reserve would stop a running trial at USD 2.25 and is not needed for that.
LATER_CAP, LATER_RESERVE = 2.75, 0.25
# Only the launchers may change after the primary run; every other file it bound keeps its hash.
RENEWED = {'tools/guarded_matched_briefing.py', 'tools/guarded_replication.py'}
AMENDMENT = 'notes/fresh-market-2-nov/amendment-4-2-nov.md'
START_CUTOFF_REASON = 'start cutoff reached; no new trial'


def validate_config(path):
    cfg = json.loads(Path(path).read_text())
    study = STUDIES.get(cfg.get('study_id'))
    if study is None or cfg.get('round') != 1 or 'prior_round' in cfg:
        raise original.Stop('wrong supplementary study or budget scope')
    stage = cfg.get('stage')
    if stage is not None and (cfg['study_id'] != FRESH or stage not in LATER):
        raise original.Stop('only the fresh study has later stages, those of amendment 4')
    if original.number(cfg.get('cap_usd')) != (LATER_CAP if stage else study['cap']):
        raise original.Stop('supplementary study cap differs from its design')
    deadline = dt.datetime.fromisoformat(cfg['deadline'])
    if deadline.tzinfo is None or deadline > study['latest']:
        raise original.Stop('supplementary deadline exceeds verified design')
    root = Path(cfg['repo'])
    protocol_path = root / cfg['protocol']
    protocol = json.loads(protocol_path.read_text())
    if (protocol.get('study_id') != cfg['study_id'] or protocol.get('status') != 'frozen'
            or cfg['hashes'].get(cfg['protocol']) != original.sha(protocol_path)):
        raise original.Stop('supplementary protocol is not frozen and bound')
    paid = [step for step in cfg['steps'] if step['kind'] == 'paid']
    if stage:
        validate_later(cfg, protocol, deadline)
    elif len(paid) != 16 or [s.get('study_slot') for s in paid] != protocol['schedule']:
        raise original.Stop('paid schedule differs from the sixteen original slots')
    return cfg, protocol


def primary_spent(status):
    """The primary run's counted spend: the larger of its recorded charges and the account's
    usage over its run, as its guard counted it (`spent_usd`)."""
    return max(original.number(status['recorded_usd']), original.number(status['spent_usd']))


def batch_slots(manifest):
    """The slot of every `batch|` line of a manifest, read from its `--slot-id`."""
    slots = []
    for line in Path(manifest).read_text().splitlines():
        if line.startswith('batch|'):
            found = re.search(r'--slot-id (\d+)\b', line)
            slots.append(int(found.group(1)) if found else None)
    return slots


def partial_run(root, primary, status):
    """The step the primary run had started and not completed when it stopped, if any. Its launcher
    opens each step's log before the step's process starts, numbered by the steps completed before
    it, so a log past them is a step that began. Returns that log, the results folder its runner
    named, and whether the runner wrote a suite record there (2 November 2026)."""
    log = Path(root) / primary['log_dir'] / f"{len(status['completed_steps']):03d}.log"
    if not log.exists():
        return None
    named = re.search(r'-> (\S+)\s*$', log.read_text(errors='replace'), re.M)
    folder = Path(named.group(1)) if named else None
    return {'step': status.get('current_step'), 'log': str(log.relative_to(root)), 'log_sha256': original.sha(log),
            'results_folder': str(folder) if folder else None,
            'results_files': sorted(p.name for p in folder.iterdir()) if folder and folder.is_dir() else [],
            'suite_written': bool(folder and (folder / 'suite.json').exists())}


def validate_later(cfg, protocol, deadline):
    """A later stage of the fresh study (amendment 4): the primary run's command by hash, its
    terminal status, manifest and files unchanged, its own paths, the shared cap with the primary
    run's counted spend carried, its start cutoff, and the primary run's own steps unchanged."""
    root = Path(cfg['repo']).resolve()
    primary_path = root / FRESH_PRIMARY_CONFIG
    if original.sha(primary_path) != FRESH_PRIMARY_SHA256:
        raise original.Stop("a later stage binds the primary run's exact command")
    primary = json.loads(primary_path.read_text())
    stage = cfg['stage']
    if any(cfg.get(field) != value for field, value in LATER[stage].items()) or cfg.get('results_dir') != primary['results_dir']:
        raise original.Stop("a later stage writes its own manifest, status and logs, fixed beside the primary run's")
    if original.number(cfg.get('reserve_usd')) != LATER_RESERVE or cfg.get('shared_cap_usd') != LATER_CAP:
        raise original.Stop("a later stage keeps the shared USD 2.75 cap and its USD 0.25 in-flight reserve")
    cutoff = dt.datetime.fromisoformat(cfg['start_cutoff'])
    if cutoff.tzinfo is None or cutoff > deadline:
        raise original.Stop('a later stage stops starting trials at a start cutoff no later than its deadline')
    if cfg.get('git_checks') != primary['git_checks'] or cfg.get('protocol') != primary['protocol']:
        raise original.Stop("a later stage runs the primary run's agent and protocol")
    if any(cfg['hashes'].get(name) != digest for name, digest in primary['hashes'].items() if name not in RENEWED):
        raise original.Stop('a later stage changed a file the primary run ran with')
    status = json.loads((root / primary['status']).read_text())
    if status.get('status') not in ('complete', 'stopped') or status.get('config_sha256') != FRESH_PRIMARY_SHA256:
        raise original.Stop("a later stage needs the primary run's terminal status under its own command")
    evidence = {FRESH_PRIMARY_CONFIG, primary['status'], primary['manifest'], AMENDMENT}
    completed = status['completed_steps']
    ids = [step['id'] for step in primary['steps']]
    if completed != ids[:len(completed)] or completed[:1] != ids[:1]:
        raise original.Stop("the primary run's completed steps are not its schedule's first ones")
    if stage == CONTINUATION:
        if abs(original.number(cfg.get('carryover_usd')) - primary_spent(status)) > 1e-12:
            raise original.Stop("the continuation carries the primary run's counted spend")
        steps = [primary['steps'][0]] + [step for step in primary['steps'][1:] if step['id'] not in completed]
        if cfg['steps'] != steps or len(steps) < 2:
            raise original.Stop("the continuation runs the primary run's uncompleted steps, unchanged, after its live check")
        if set(batch_slots(root / primary['manifest'])) & {step['study_slot']['slot'] for step in steps[1:]}:
            raise original.Stop('a slot the continuation would run has a result in the primary manifest')
        partial = partial_run(root, primary, status)
        if partial is not None:
            # A step the primary run started is run again only on a ruling recorded in the
            # configuration, since amendment 4 point 4 forbids replaying a started slot.
            ruling = cfg.get('partial_run_ruling')
            if cfg.get('partial_run') != partial or not isinstance(ruling, str) or not ruling.strip():
                raise original.Stop("the primary run started this step before it stopped; the configuration "
                                    "must show it and record the ruling that allows running it again")
            evidence.add(partial['log'])
        elif 'partial_run' in cfg:
            raise original.Stop('the configuration names a partial run the primary run does not show')
    if not evidence <= set(cfg['hashes']):
        raise original.Stop("the primary run's command, status, manifest and amendment 4 must be hash-bound")
    for name in evidence:
        if original.sha(root / name) != cfg['hashes'][name]:
            raise original.Stop("the primary run's evidence changed after it was bound")
    if not all(step.get('study_slot') in protocol['schedule'] for step in cfg['steps'] if step['kind'] == 'paid'):
        raise original.Stop('a later stage runs only slots of the frozen schedule')


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
    study_id = STUDY  # the configuration's, set by the constructor

    def __init__(self, config_path, *, account_command=None):
        cfg, self.protocol = validate_config(config_path)
        self.study_id = cfg['study_id']
        # A later stage of amendment 4: its own reserve, the primary run's spend carried, and a
        # start cutoff. The primary run's configuration has none of these (2 November 2026).
        self.stage = cfg.get('stage')
        self.carryover = original.number(cfg.get('carryover_usd', 0))
        self.start_cutoff = dt.datetime.fromisoformat(cfg['start_cutoff']).timestamp() if self.stage else None
        self.MIN_RESERVE_USD = LATER_RESERVE if self.stage else STUDIES[self.study_id]['min_reserve']
        # Constructor reads this constant once. Restore it even if it refuses.
        old = original.AUTHORIZED_DEADLINE
        try:
            original.AUTHORIZED_DEADLINE = STUDIES[self.study_id]['latest']
            super().__init__(config_path, account_command=account_command)
        finally:
            original.AUTHORIZED_DEADLINE = old
        self.protocol_sha = original.sha(self.repo / cfg['protocol'])

    def check_integrity(self):
        super().check_integrity()
        check_key_context(self.repo)

    def spent(self):
        """Every stop counts the carried spend of the earlier stages beside this stage's own."""
        return self.carryover + super().spent()

    def status_fields(self):
        if not self.stage:
            return {}
        return {'stage': self.stage, 'carryover_usd': self.carryover, 'stage_spent_usd': super().spent(),
                'shared_cap_usd': self.cap, 'running_trial_stop_usd': self.cap - self.reserve,
                'start_cutoff': self.config['start_cutoff']}

    def execute_step(self, step):
        """A later stage starts no paid step at or after its start cutoff."""
        if step['kind'] == 'paid' and self.start_cutoff is not None and time.time() >= self.start_cutoff:
            raise original.Stop(START_CUTOFF_REASON)
        return super().execute_step(step)

    def validate_output(self, step, logfile, before_dirs):
        output = super().validate_output(step, logfile, before_dirs)
        if step['kind'] == 'paid':
            data = json.loads(Path(output['output']).read_text())
            expected = step['study_slot']
            for stamp in [data] + data['rows']:
                if (stamp.get('study_id') != self.study_id
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
            if cfg.get('stage'):
                stop = LATER_CAP - LATER_RESERVE
                print(f"Stage {cfg['stage']}: carryover USD {cfg['carryover_usd']:.10f}; a running trial stops at "
                      f"USD {stop:.2f} counted; no trial starts at or after {cfg['start_cutoff']}, nor once the "
                      f"counted spend plus twice its estimate reaches USD {stop:.2f}.")
            return 0
        guard = MatchedGuard(args.config)
        result = guard.run()
        # A later stage's sheet waits for every stage (amendment 4: one blind sheet for all).
        return result if result or guard.stage else prepare_review(guard)
    except Exception:
        print('Supplementary launcher refused configuration; no secret details printed.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
