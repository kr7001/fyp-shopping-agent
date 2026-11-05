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
# USD 4 with the primary run (USD 2.75 in point 1, USD 4 in point 6), whose counted spend each
# carries. A later stage runs the primary run's own steps unchanged, the reruns through their
# reviewed wrapper, and writes its own manifest, status and logs beside the primary's, which it
# never touches.
#   continuation   the primary run's steps it never completed (slot 16), after the same live check
#   timeout-rerun  each slot whose primary record reached its 1800 s clock, once more, in slot
#                  order, its clock doubled to 3600 s and nothing else changed, with its own record
#                  in its own manifest, `rerun|` lines naming the primary record, never `batch|`
FRESH_PRIMARY_CONFIG = 'notes/fresh-market-2-nov/study-b-command.json'
FRESH_PRIMARY_SHA256 = '507aea6cad5222ad7f3b3d8d421ee32be3bb5db34c7fd694cae5a188f6799a12'
FRESH_STEM = 'experiments/results/matched-briefing-fresh-2-nov'
CONTINUATION, RERUN = 'continuation', 'timeout-rerun'
LATER = {stage: {'manifest': f'{FRESH_STEM}.{name}.manifest', 'status': f'{FRESH_STEM}.{name}.status.json',
                 'log_dir': f'{FRESH_STEM}.{name}.logs'} for stage, name in ((CONTINUATION, 'continuation'),
                                                                             (RERUN, 'rerun'))}
CLOCK_S, RERUN_CLOCK_S = 1800, 3600
# The reruns run the frozen code through a separately reviewed wrapper that hands suite.py a
# 3600 s clock and changes nothing else (amendment 4 point 6), pinned here by its SHA-256. The
# frozen runner, which accepts only 1800 s, stays byte-identical.
FROZEN_RUNNER = 'experiments/runners/matched_briefing_study.py'
RERUN_RUNNER = 'experiments/runners/matched_briefing_rerun.py'
RERUN_RUNNER_SHA256 = '99bea5a628d88ce1f360bbc70d7df353a24c4b9bc8188cc269d743488abfbfa8'
# Amendment 4 point 6 (12:50): Study B's shared cap is USD 4, and slot 16's estimate about USD 0.25
# to 0.45, going by slot 7 (USD 0.2498) and slot 16's own partial run (USD 0.1757 at step 152).
LATER_CAP, CONTINUATION_ESTIMATE_USD = 4.0, 0.45
# The thresholds, chosen 2 November 2026 for the USD 4 cap. A running trial stops when the counted
# spend, the carryover included, reaches the cap less the in-flight reserve, USD 3.65; a trial
# starts only while the counted spend plus twice its step's estimate stays below that. Taking a
# trial at the 1800 s clock to charge at most USD 0.45 (point 6's upper figure) and a rerun at
# twice the clock at most twice that, USD 0.90, a trial started just below its threshold that
# charged that much, wholly unseen by the account until it ended, still ends below USD 4:
#   slot 16, its primary step's estimate 0.075 unchanged: starts below 3.50, ends at most 3.95
#   a rerun, estimate 0.30:                               starts below 3.05, ends at most 3.95
LATER_RESERVE = 0.35
# A rerun step keeps the primary step's 120 s beside its clock.
RERUN_WALL_S, RERUN_ESTIMATE = RERUN_CLOCK_S + 120, 0.30
# Only the launchers, and the replication guard's own tests, may change after the primary run;
# every other file it bound keeps its hash. The tests changed with the account probe's retries
# (2 November 2026, 13:18).
RENEWED = {'tools/guarded_matched_briefing.py', 'tools/guarded_replication.py',
           'experiments/tests/test_guarded_replication.py'}
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


def primary_spent(root, primary, status):
    """The primary run's counted spend: the larger of the account's usage over its run, as its
    guard counted it (`spent_usd`), and its recorded charges plus those its partial run's log shows,
    which no record holds (slot 16's 151 calls; amendment 4 point 6)."""
    partial = partial_run(root, primary, status)
    charges = partial['charges_usd'] if partial else 0.0
    return max(original.number(status['spent_usd']), original.number(status['recorded_usd']) + charges)


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
    # The charges its run logs show, by the frozen trace reader (`trace_stats.cost_reported`),
    # every completion with its charge, or the run is refused as unaccounted.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'experiments'))
    import paths  # noqa: F401  (puts analysis/ on the path)
    import trace_stats
    runs = sorted(folder.glob('*.log')) if folder and folder.is_dir() else []
    texts = [path.read_text(errors='replace') for path in runs]
    calls = sum(len(trace_stats.USAGE.findall(text)) for text in texts)
    if sum(len(trace_stats.COST_FIELD.findall(text)) for text in texts) != calls:
        raise original.Stop("the partial run's log has a completion without its charge; inspect it")
    charges = round(sum(trace_stats.cost_reported(text) or 0.0 for text in texts), 6)
    return {'step': status.get('current_step'), 'log': str(log.relative_to(root)), 'log_sha256': original.sha(log),
            'results_folder': str(folder) if folder else None,
            'results_files': sorted(p.name for p in folder.iterdir()) if folder and folder.is_dir() else [],
            'suite_written': bool(folder and (folder / 'suite.json').exists()),
            'run_logs': [str(path.relative_to(root)) for path in runs], 'charged_calls': calls, 'charges_usd': charges}


def launched(root, stage):
    """Whether a later stage has left any file: its manifest, status or logs."""
    return any((Path(root) / path).exists() for path in LATER[stage].values())


def rerun_step(step, timeout):
    """A primary step run once more for its timed-out slot: through the reviewed wrapper, its clock
    1800 s to 3600 s and its wall budget with it, its estimate the reruns', every other argument and
    the environment as they were, and a `rerun|` manifest line that names the primary record's
    folder."""
    argv = list(step['argv'])
    at = argv.index('--clock')
    if argv[at + 1] != str(CLOCK_S) or step.get('max_seconds') != CLOCK_S + 120 or argv[1] != FROZEN_RUNNER:
        raise original.Stop("a rerun doubles a primary step's 1800 s clock")
    argv[1], argv[at + 1] = RERUN_RUNNER, str(RERUN_CLOCK_S)
    return {**step, 'id': 'rerun-' + step['id'], 'argv': argv, 'max_seconds': RERUN_WALL_S,
            'estimate_usd': RERUN_ESTIMATE, 'rerun_of': timeout,
            'manifest_line_template': f"rerun|{{batch}}|stage {RERUN}|primary {timeout['batch']}|" + ' '.join(argv[2:])}


def primary_timeouts(root, manifests):
    """Every slot whose primary record reached its 1800 s clock, in slot order, from the `batch|`
    lines of the given manifests: the frozen void rules (experiments/analysis/voids.py) call the
    run reported, not correct, by the clock, and its record's own elapsed time is at or past its
    clock. A run those rules void, as a silent log or a provider error, is not rerun (amendment 4
    point 4). Reads the record's markers and the log's timing, never judges an answer."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'experiments'))
    import paths  # noqa: F401  (puts analysis/ on the path)
    import voids
    root = Path(root).resolve()
    found = []
    for manifest in manifests:
        for line in (root / manifest).read_text().splitlines():
            if not line.startswith('batch|'):
                continue
            folder = Path(line.split('|')[1]).resolve()
            slot = int(re.search(r'--slot-id (\d+)\b', line).group(1))
            row = json.loads((folder / 'suite.json').read_text())['rows'][0]
            record_path = folder / f"{row['task']}-{row['repeat']}.json"
            log_path = record_path.with_suffix('.log')
            record = json.loads(record_path.read_text()) if record_path.exists() else None
            log = log_path.read_text(errors='replace') if log_path.exists() else None
            outcome, reason, _ = voids.classify(record, log, row=row)
            if (outcome, reason) != (voids.NOT_CORRECT, 'clock'):
                continue
            elapsed, clock = record.get('elapsed_s'), record.get('clock_s')
            if clock != CLOCK_S or not isinstance(elapsed, (int, float)) or elapsed < clock:
                continue
            found.append({'slot': slot, 'batch': str(folder), 'manifest': manifest,
                          'suite': str((folder / 'suite.json').relative_to(root)),
                          'suite_sha256': original.sha(folder / 'suite.json'),
                          'record': str(record_path.relative_to(root)), 'record_sha256': original.sha(record_path),
                          'log': str(log_path.relative_to(root)), 'log_sha256': original.sha(log_path),
                          'elapsed_s': elapsed, 'clock_s': clock})
    found.sort(key=lambda row: row['slot'])
    if len({row['slot'] for row in found}) != len(found):
        raise original.Stop('a slot has two primary records')
    return found


def rerun_carryover(root, primary, status):
    """The reruns' carryover and the manifests of primary records: the continuation's counted
    spend, its carryover included, once it ran, else the primary run's."""
    path = Path(root) / LATER[CONTINUATION]['status']
    if not launched(root, CONTINUATION):
        return primary_spent(root, primary, status), [primary['manifest']], []
    if not path.exists():
        raise original.Stop('the continuation left files but no status; inspect it')
    continuation = json.loads(path.read_text())
    if (continuation.get('status') not in ('complete', 'stopped') or continuation.get('stage') != CONTINUATION
            or abs(original.number(continuation.get('carryover_usd')) - primary_spent(root, primary, status)) > 1e-12):
        raise original.Stop("the reruns need the continuation's terminal status, carrying the primary run's spend")
    return (original.number(continuation['spent_usd']), [primary['manifest'], LATER[CONTINUATION]['manifest']],
            [LATER[CONTINUATION]['status'], LATER[CONTINUATION]['manifest']])


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
        raise original.Stop("a later stage keeps the shared USD 4 cap and its USD 0.35 in-flight reserve")
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
    if launched(root, RERUN):
        raise original.Stop('the timeout reruns have already been launched: a slot is rerun once only, '
                            'and no stage comes after them')
    if stage == RERUN:
        carryover, manifests, later = rerun_carryover(root, primary, status)
        if abs(original.number(cfg.get('carryover_usd')) - carryover) > 1e-12:
            raise original.Stop("the reruns carry the primary run's and the continuation's counted spend")
        timeouts = primary_timeouts(root, manifests)
        rows = [step.get('rerun_of') for step in cfg['steps'][1:]]
        eligible = {row['slot'] for row in timeouts}
        for row in rows:
            if (row or {}).get('slot') not in eligible:
                raise original.Stop(f"slot {(row or {}).get('slot')} is not a timeout: only a slot whose primary "
                                    f"record reached its clock is rerun")
        if len({row['slot'] for row in rows}) != len(rows):
            raise original.Stop('a slot is rerun once only')
        by_slot = {step['study_slot']['slot']: step for step in primary['steps'][1:]}
        steps = [primary['steps'][0]] + [rerun_step(by_slot[row['slot']], row) for row in timeouts]
        if rows != timeouts or cfg['steps'] != steps:
            raise original.Stop('the reruns are every timed-out slot in slot order, its primary step with '
                                'the clock doubled and nothing else changed')
        evidence.update(later)
        for row in timeouts:
            evidence.update({row['suite'], row['record'], row['log']})
        if original.sha(root / RERUN_RUNNER) != RERUN_RUNNER_SHA256:
            raise original.Stop('the rerun wrapper is not the reviewed one')
        evidence.add(RERUN_RUNNER)
    if stage == CONTINUATION:
        if abs(original.number(cfg.get('carryover_usd')) - primary_spent(root, primary, status)) > 1e-12:
            raise original.Stop("the continuation carries the primary run's counted spend")
        if cfg.get('declared_estimate_usd') != CONTINUATION_ESTIMATE_USD:
            raise original.Stop("the continuation declares amendment 4's estimate for slot 16")
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
            evidence.update([partial['log'], *partial['run_logs']])
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
        # start cutoff. The primary run's configuration has none of these.
        self.stage = cfg.get('stage')
        self.carryover = original.number(cfg.get('carryover_usd', 0))
        self.start_cutoff = dt.datetime.fromisoformat(cfg['start_cutoff']).timestamp() if self.stage else None
        self.MIN_RESERVE_USD = LATER_RESERVE if self.stage else STUDIES[self.study_id]['min_reserve']
        if self.stage == RERUN:
            self.MAX_STEP_SECONDS = RERUN_WALL_S
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
