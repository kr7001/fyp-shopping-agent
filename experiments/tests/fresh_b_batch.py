"""A synthetic Study B for the matched-briefing fresh review tests (2 November 2026).

Not a test module itself: tests/test_matched_briefing_fresh_review.py imports it. In a temporary
repository it writes what Study B's stages leave, shaped as guarded_matched_briefing.py and the
frozen runner write them: the primary run's command, status, launcher logs and manifest
(`batch|` lines), each slot's results folder (suite.json, run record, run log) as the frozen
reader's own synthetic test writes one, and the later stages of amendment 4: a continuation that
runs slot 16 on the student's ruling, and the timeout reruns (`rerun|` lines) with their clock
doubled. The protocol's schedule is the real analysis file's, slot for slot. No model, browser
or shop is involved.

A slot's kind says what its run did:

    answered   a committed, correct answer
    wrong      a committed, wrong answer
    timeout    no final answer when its clock ran out (the frozen void rules' clock limit)
    closed     the full block asked back, so no executor ran (full block only)
    void       a provider error and no final answer (the frozen void rules' technical void)
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "tools"))
import paths  # noqa: E402,F401
import guarded_matched_briefing as guard  # noqa: E402
import matched_briefing_fresh_review as review  # noqa: E402

STUDY = guard.FRESH
PROTOCOL = "experiments/tasks/matched_briefing_2_nov.json"
PRIMARY_CONFIG = "notes/fresh-market-2-nov/study-b-command.json"
ARMS = {"full-block": "box-model", "matched-briefing": "matched-briefing"}
ROUTING = {"order": ["fake"], "allow_fallbacks": False}
PREAMBLE = "Same factual briefing of 45 listings"
VALUE = 3  # every task's synthetic key: a count of 3


def sha_text(text):
    return hashlib.sha256(text.encode()).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def put(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
    return path


class StudyB:
    """The primary run, which ran slots 1 to `ran` and stopped inside slot `ran + 1` with no
    record when `partial`, as on 2 November; then `continuation` and `rerun` when called."""

    def __init__(self, folder, kinds=None, ran=15, partial=True):
        self.root = Path(folder).resolve()
        self.results = self.root / "experiments/results"
        self.tasks_dir = self.root / "experiments/tasks"
        self.kinds = dict(kinds or {})
        real = json.loads((ROOT / PROTOCOL).read_text())
        self.schedule = real["schedule"]
        tasks = [{"id": task, "query": f"How many listings can sell size M? {task} {{base}}/search",
                  "gated": True, "expect": {"kind": "count", "value": VALUE}} for task in review.frozen.TASKS]
        put(self.tasks_dir / "tasks.json", {"base_url": "http://localhost:7770", "tasks": tasks})
        self.tasks = tasks
        self.protocol_path = put(self.root / PROTOCOL, {
            "study_id": STUDY, "model": "synthetic/model", "tasks_file": "tasks.json",
            "tasks": list(review.frozen.TASKS), "repeats": [1, 2],
            "arms": {arm: {"payload_arm": value} for arm, value in ARMS.items()},
            "schedule": self.schedule, "require": {"max_steps": 300, "clock_s": 1800},
            "provider_routing": {"synthetic/model": ROUTING}})
        # Each paid step as the launch builder writes it: the frozen runner, the 1800 s clock, and
        # its wall budget, so that guarded_matched_briefing.rerun_step can turn it into a rerun.
        self.steps = [{"id": "preflight", "kind": "preflight"}] + [
            {"id": f"slot-{s['slot']}-{s['arm']}-{s['task']}-r{s['repeat']}", "kind": "paid", "study_slot": s,
             "argv": ["python", guard.FROZEN_RUNNER, *self.runner_args(s, 1800).split()], "max_seconds": 1920,
             "estimate_usd": 0.075, "manifest_line_template": "batch|{batch}|" + self.runner_args(s, 1800)}
            for s in self.schedule]
        self.config_path = put(self.root / PRIMARY_CONFIG, {
            "study_id": STUDY, "round": 1, "repo": str(self.root), "manifest": f"{guard.FRESH_STEM}.manifest",
            "status": f"{guard.FRESH_STEM}.status.json", "log_dir": f"{guard.FRESH_STEM}.logs",
            "results_dir": "experiments/results", "steps": self.steps,
            "hashes": {name: sha(ROOT / name) for name in review.FROZEN_CODE}})
        self.config_sha = sha(self.config_path)
        self.study = dataclasses.replace(review.STUDY_B, root=self.root, primary_sha256=self.config_sha,
                                         sheet="synthetic-b.sheet.csv")
        self.folders = {}
        lines = [f"start 2026-11-02T03:16:06 usage 136 cap 2.00",
                 f"study {STUDY} the matched-briefing design on the synthetic market",
                 "conditions commit 0000000 browser synthetic",
                 "WATCHDOG USD2 study cap; USD0.50 inflight reserve"]
        for slot in self.schedule[:ran]:
            lines.append(self.run_line(slot))
        logs = self.root / f"{guard.FRESH_STEM}.logs"
        logs.mkdir(parents=True, exist_ok=True)
        for i in range(ran + 1):
            (logs / f"{i:03d}.log").write_text("synthetic launcher log\n")
        completed = ["preflight"] + [step["id"] for step in self.steps[1:ran + 1]]
        status = {"status": "stopped", "reason": "budget stop or insufficient budget for next step",
                  "config_sha256": self.config_sha, "completed_steps": completed,
                  "current_step": None, "recorded_usd": 1.0, "spent_usd": 1.2}
        if partial and ran < 16:
            # The started slot: its launcher log names a results folder with caches and a log only.
            started = self.results / f"started-{ran + 1:02d}"
            (started / "caches").mkdir(parents=True)
            # Its run log, with the charges the later stages' carryover counts (151 calls on 2 November).
            (started / "tee-count-buyable-2.log").write_text(
                self.kinds.get("started_log", "2026-11-02 06:24:00 | start\nCompletionUsage(completion_tokens=10, "
                               "prompt_tokens=20, total_tokens=30) cost=0.1757, is_byok=False, provider='fake'\n"))
            (logs / f"{ran + 1:03d}.log").write_text(f"slot {ran + 1} -> {started}\n")
            status["current_step"] = self.steps[ran + 1]["id"]
        lines.append("STOP budget stop or insufficient budget for next step" if ran < 16 else "end 2026-11-02T06:40:00 usage 137")
        self.manifest = self.root / f"{guard.FRESH_STEM}.manifest"
        self.manifest.write_text("\n".join(lines) + "\n")
        put(self.root / f"{guard.FRESH_STEM}.status.json", status)
        self.status = status
        self.stages = {}

    def run_line(self, slot, clock=1800, prefix="P", rerun_of=None):
        """One run's results folder, as the frozen runner writes it, and its manifest line."""
        number, arm, task, repeat = (slot[k] for k in ("slot", "arm", "task", "repeat"))
        kind = self.kinds.get((prefix, number), "answered")
        folder = self.results / f"{prefix}{number:02d}"
        folder.mkdir(parents=True)
        self.folders[(prefix, number)] = folder
        identity = {"study_id": STUDY, "protocol_sha256": sha(self.protocol_path), "wrapper_id": "matched-briefing-v1",
                    "condition": arm, "slot_id": number, "arm": ARMS[arm]}
        original = next(t["query"] for t in self.tasks if t["id"] == task).format(base="http://localhost:7770")
        page = {"listings": [{"url": f"http://localhost:7770/l{n}.html", "price": n} for n in range(45)],
                "reader": "rendered", "next_page": False, "total": 45, "count": 45}
        preamble = self.kinds.get((prefix, number, "preamble"), PREAMBLE)
        briefing = {"query": original, "query_sha256": sha_text(original), "original_query": original,
                    "original_query_sha256": sha_text(original), "preamble": preamble,
                    "preamble_sha256": sha_text(preamble), "page": page,
                    "page_sha256": sha_text(json.dumps(page, sort_keys=True, separators=(",", ":"))),
                    "pre_read_elapsed_s": 2, "pre_read_cached": True, "query_build_elapsed_s": 1}
        final = {"answered": f"{VALUE} listings can sell size M. ", "wrong": f"{VALUE + 2} listings can sell size M. ",
                 "timeout": "", "void": "", "closed": ""}[kind] + ("Supporting explanation. " * 30 if kind in ("answered", "wrong") else "")
        error = {"timeout": f"task_timeout: exceeded {clock}s", "void": "Error code: 429"}.get(kind)
        token = {"prompt": 20, "completion": 10, "total": 30, "calls": 1}
        cost = 0.11 if arm == "full-block" else 0.10
        record = {**identity, "briefing": briefing, "query": original, "cost_usd": cost,
                  "elapsed_s": clock + 1 if kind == "timeout" else 4, "model": "synthetic/model",
                  "scaffold": "openjiuwen", "shop": "gated", "probe": "viewport", "max_steps": 300, "clock_s": clock,
                  "provider_routing": ROUTING, "result": {"ok": kind in ("answered", "wrong"), "final": final, "error": error},
                  "tokens": token, "trace": {"tool_calls_total": 0, "actions": 0, "tokens": token}}
        row = {**identity, "briefing": briefing, "task": task, "repeat": repeat, "cost_usd": cost,
               "answer": final[:300], "verdict": "correct", "elapsed_s": record["elapsed_s"]}
        if arm == "full-block":
            record.update(agent_cost_usd=.1, parse_cost_usd=.01, parse_tokens=token, parse_provider="fake")
            record["tokens"] = {"prompt": 40, "completion": 20, "total": 60}
            row.update(parse_cost_usd=.01, parse_tokens=token, parse_provider="fake", box={"query": "plan"})
        else:
            for item in (row, record):
                item.update(parse_cost_usd=0, parse_tokens={"prompt": 0, "completion": 0, "total": 0, "calls": 0},
                            parse_provider=None)
        payload = {**identity, "arm": ARMS[arm], "box": arm == "full-block", "box_exhaust": False,
                   "parser": "model" if arm == "full-block" else None, "repeats": 1, "repeat_start": repeat,
                   "tasks_file": "tasks.json", "model": "synthetic/model", "max_steps": 300, "clock_s": clock,
                   "briefing_page_reader": "rendered", "rows": [row], "provider_routing": {
                       "agent": ROUTING, "parser": ROUTING if arm == "full-block" else None}}
        if kind == "closed":
            assert arm == "full-block", "only the full block closes a slot"
            row.update(verdict="asked", cost_usd=.01, elapsed_s=0, log=None, box={"asked": True, "query": None})
            row["briefing"].update(query=None, query_sha256=None)
        else:
            (folder / f"{task}-{repeat}.json").write_text(json.dumps(record))
            (folder / f"{task}-{repeat}.log").write_text(
                "2026-11-02 03:00:00 | start\nCompletionUsage(completion_tokens=10, prompt_tokens=20, total_tokens=30) "
                "cost=0.1, is_byok=False, provider='fake'\n2026-11-02 03:00:04 | end\n")
        (folder / "suite.json").write_text(json.dumps(payload))
        args = self.runner_args(slot, clock)
        if rerun_of:
            return f"rerun|{folder}|stage {guard.RERUN}|primary {rerun_of}|{args}"
        return f"batch|{folder}|{args}"

    @staticmethod
    def runner_args(slot, clock):
        """A slot's runner arguments, as its manifest line repeats them."""
        return (f"--condition {slot['arm']} --protocol {PROTOCOL} --slot-id {slot['slot']} --tasks "
                f"experiments/tasks/tasks.json --only {slot['task']} --repeats 1 --repeat-start {slot['repeat']} "
                f"--page-reader rendered --max-steps 300 --clock {clock}")

    def later(self, stage, steps, lines, extra=None, status="complete", hashes=None):
        """A later stage's configuration, verifier's receipt, status and manifest. A stage that
        stopped says why, as its start cutoff does."""
        files = guard.LATER[stage]
        config = {"study_id": STUDY, "round": 1, "stage": stage, "repo": str(self.root), **files,
                  "results_dir": "experiments/results", "steps": [self.steps[0]] + steps,
                  "hashes": {PRIMARY_CONFIG: self.config_sha, **(hashes or {})}, "expected_head": "synthetic-head",
                  "verification_receipt": str(self.root / f"notes/fresh-market-2-nov/study-b-{stage}.verification.json"),
                  **(extra or {})}
        path = put(self.root / f"notes/fresh-market-2-nov/study-b-{stage}-command.json", config)
        digest = sha(path)
        put(config["verification_receipt"], {"status": "PASS", "head": "synthetic-head", "config_sha256": digest})
        put(self.root / files["status"], {"status": status, "stage": stage, "config_sha256": digest,
                                          "reason": None if status == "complete" else "start cutoff reached; no new trial"})
        (self.root / files["log_dir"]).mkdir(parents=True, exist_ok=True)
        (self.root / files["manifest"]).write_text("\n".join(
            ["start 2026-11-02T13:00:00 usage 138 cap 2.75", f"study {STUDY} {stage}; amendment 4; no pooling with Quenby",
             *lines, "end 2026-11-02T14:00:00 usage 139"]) + "\n")
        self.stages[stage] = (path, digest)
        return config

    def continuation(self, ruling="Yes, run slot 16 again.", run=True):
        """Slot 16 run once more, carrying the primary run's partial-run evidence and the ruling."""
        slot = self.schedule[15]
        partial = guard.partial_run(self.root, json.loads(self.config_path.read_text()), self.status)
        extra = {"partial_run": partial, "partial_run_ruling": ruling} if partial else {}
        lines = [self.run_line(slot, prefix="C")] if run else []
        return self.later(guard.CONTINUATION, [self.steps[16]], lines, extra)

    def rerun(self, ran=None):
        """Every primary timeout once more, its clock doubled to 3600 s, in slot order; with `ran`,
        only the first `ran` of them before the stage stopped."""
        manifests = [str(self.manifest.relative_to(self.root))]
        if guard.CONTINUATION in self.stages:
            manifests.append(guard.LATER[guard.CONTINUATION]["manifest"])
        timeouts = guard.primary_timeouts(self.root, manifests)
        by_slot = {s["slot"]: s for s in self.schedule}
        lines = [self.run_line(by_slot[row["slot"]], clock=3600, prefix="R", rerun_of=row["batch"])
                 for row in timeouts[:ran]]
        return self.later(guard.RERUN, self.rerun_steps(timeouts), lines, hashes=self.wrapper(),
                          status="complete" if ran is None or ran >= len(timeouts) else "stopped")

    def rerun_steps(self, rows):
        """Each rerun step as the launcher builds it, through the reviewed wrapper (f4035ed)."""
        return [guard.rerun_step(self.steps[row["slot"]], row) for row in rows]

    @staticmethod
    def wrapper():
        """The rerun stage's binding of the wrapper at its reviewed SHA-256."""
        return {guard.RERUN_RUNNER: guard.RERUN_RUNNER_SHA256}

    def args(self):
        """The later stages as `prepare` is given them."""
        return {stage: self.stages[stage] for stage in self.stages}
