#!/usr/bin/env python3
"""Local sequential replication launcher; no model is called by validation or tests.

Run: python3 tools/guarded_replication.py --config CONFIG.json
The separate receipt must say PASS and bind config_sha256 and head. Config requires
repo, expected_head, hashes, verification_receipt, deadline, manifest, status,
log_dir, results_dir, steps. Paid steps require estimate_usd and output_kind
('suite' with expected_tasks/repeat, or 'file' with expected_output). Each step
has argv, optional cwd/env (null removes an inherited variable), max_seconds,
and optional manifest_line_template using {batch} or {output}. No shell is used.
All logs/status/manifests are local private files. No automatic resume or round 2.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

AUTHORIZED_DEADLINE = dt.datetime.fromisoformat("2026-10-28T08:00:00+08:00")


class Stop(RuntimeError):
    pass


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
        json.dump(value, f, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporary, path)


def number(value):
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise Stop("invalid financial value")
    return value


def account_probe(env_file):
    """Three short transient-read attempts; print only usage and remaining balance."""
    try:
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            for line in Path(env_file).read_text().splitlines():
                match = re.match(r"\s*(?:export\s+)?OPENROUTER_API_KEY\s*=\s*(.*?)\s*$", line)
                if match:
                    key = match.group(1).strip("\"'")
                    break
        if not key:
            return 2
        request = urllib.request.Request("https://openrouter.ai/api/v1/key",
                                         headers={"Authorization": f"Bearer {key}"})
    except Exception:
        return 2
    expires = time.monotonic() + 6
    for _ in range(3):
        remaining_time = expires - time.monotonic()
        if remaining_time <= 0:
            return 2
        try:
            with urllib.request.urlopen(request, timeout=min(2, remaining_time)) as response:
                data = json.load(response)["data"]
        except urllib.error.HTTPError as error:
            if error.code not in (408, 429, 500, 502, 503, 504):
                return 2
            continue
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
        except Exception:
            return 2
        try:
            usage = number(data["usage"])
            remaining = data.get("limit_remaining")
            if remaining is None and data.get("limit") is not None:
                remaining = max(0, number(data["limit"]) - usage)
            if remaining is None or time.monotonic() >= expires:
                return 2
            remaining = number(remaining)
        except Exception:
            return 2
        print(json.dumps({"usage": usage, "remaining": remaining}))
        return 0
    # Neither exception text nor HTTP response bodies may disclose a secret.
    return 2


class Guard:
    def __init__(self, config_path, *, account_command=None):
        self.config_path = Path(config_path).resolve()
        self.config_hash = sha(self.config_path)
        self.config = json.loads(self.config_path.read_text())
        self.repo = Path(self.config["repo"]).resolve()
        self.deadline = dt.datetime.fromisoformat(self.config["deadline"])
        if self.deadline.tzinfo is None or self.deadline > AUTHORIZED_DEADLINE:
            raise Stop("deadline exceeds the authorized limit or lacks timezone")
        self.shutdown_epoch = self.deadline.timestamp() - 15
        self.shutdown_monotonic = time.monotonic() + self.shutdown_epoch - time.time()
        self.launch_window = None  # Derive from each step's agent + setup wall budget.
        self.poll_interval = 10
        self.account_timeout = 8
        self.kill_grace = 4
        self.cap = number(self.config.get("cap_usd", 20))
        self.reserve = number(self.config.get("reserve_usd", 1))
        if not 0 < self.cap <= 20 or self.reserve < 1 or self.reserve >= self.cap:
            raise Stop("invalid authorized budget or inflight reserve")
        self.manifest = self.path(self.config["manifest"])
        self.status_path = self.path(self.config["status"])
        self.log_dir = self.path(self.config["log_dir"])
        self.results_dir = self.path(self.config["results_dir"])
        self.account_command = account_command or [sys.executable, str(Path(__file__).resolve()),
                                                   "--account-probe", str(self.repo / ".env")]
        self.child = None
        self.probe = None
        self.lock = None
        self.manifest_created = False
        self.start_usage = None
        self.usage = None
        self.remaining = None
        self.recorded = 0.0
        self.completed = []
        self.current = None
        self.initial_dirs = set()
        self.explicit_outputs = set()
        self.next_probe = 0
        self.next_records = 0
        self.last_probe_time = None

    def path(self, value):
        p = Path(value)
        return p.resolve() if p.is_absolute() else (self.repo / p).resolve()

    def deadline_check(self):
        if time.monotonic() >= self.shutdown_monotonic or time.time() >= self.shutdown_epoch:
            raise Stop("absolute deadline shutdown")

    def status(self, state, reason=None):
        if not self.manifest_created:
            return
        atomic_json(self.status_path, {"status": state, "reason": reason, "pid": os.getpid(),
                    "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "deadline": self.config["deadline"], "config_sha256": self.config_hash,
                    "start_usage": self.start_usage, "last_usage": self.usage,
                    "recorded_usd": self.recorded, "spent_usd": self.spent(),
                    "current_step": self.current, "completed_steps": self.completed})

    def append(self, line):
        if "\n" in line or "\r" in line:
            raise Stop("invalid manifest line")
        with self.manifest.open("a") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())

    def check_integrity(self):
        self.deadline_check()
        if sha(self.config_path) != self.config_hash:
            raise Stop("configuration changed")
        receipt = json.loads(self.path(self.config["verification_receipt"]).read_text())
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo,
                                       stderr=subprocess.DEVNULL, timeout=3).decode().strip()
        if head != self.config["expected_head"]:
            raise Stop("repository HEAD changed")
        if receipt.get("status") != "PASS" or receipt.get("head") != head or receipt.get("config_sha256") != self.config_hash:
            raise Stop("verification receipt does not bind this command/configuration")
        hashes = self.config.get("hashes", {})
        if not hashes:
            raise Stop("no immutable files declared")
        for path, expected in hashes.items():
            if sha(self.path(path)) != expected:
                raise Stop("immutable file changed")
        for check in self.config.get("git_checks", []):
            cwd = self.path(check["cwd"])
            actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=cwd, timeout=3).decode().strip()
            patch = subprocess.check_output(["git", "diff", "--binary", "HEAD"], cwd=cwd, timeout=3)
            if actual != check["head"] or hashlib.sha256(patch).hexdigest() != check["diff_sha256"]:
                raise Stop("agent or experiment git state changed")

    def cleanup_group(self, process):
        if process is None:
            return
        # Reap a completed direct child before addressing its process group.
        # macOS may return EPERM for an unreaped, already-dead group leader.
        process.poll()
        # Never use pgrep/pkill: only the process group this launcher created.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            if process.stdout is not None:
                process.stdout.close()
            return
        end = time.monotonic() + self.kill_grace
        while time.monotonic() < end:
            process.poll()
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                break
            time.sleep(.05)
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=.5)
        except subprocess.TimeoutExpired:
            pass
        if process.stdout is not None:
            process.stdout.close()

    def start_probe(self):
        self.probe = subprocess.Popen(self.account_command, cwd=self.repo, stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL, start_new_session=True)
        self.probe_started = time.monotonic()

    def poll_account(self, required=False):
        if self.probe is None and (required or time.monotonic() >= self.next_probe):
            self.start_probe()
        while self.probe is not None:
            self.deadline_check()
            code = self.probe.poll()
            if code is not None:
                raw = self.probe.communicate()[0]
                self.cleanup_group(self.probe)
                self.probe = None
                try:
                    if code:
                        raise ValueError()
                    result = json.loads(raw)
                    usage = number(result["usage"])
                    remaining = result.get("remaining")
                    if remaining is None:
                        raise ValueError("account reserve cannot be verified")
                    remaining = number(remaining)
                except Exception:
                    raise Stop("account visibility lost") from None
                if self.usage is not None and usage + 1e-6 < self.usage:
                    raise Stop("account usage moved backwards")
                self.usage, self.remaining = usage, remaining
                self.last_probe_time = time.monotonic()
                self.next_probe = self.last_probe_time + self.poll_interval
                return
            if time.monotonic() - self.probe_started >= self.account_timeout:
                raise Stop("account read timed out")
            if not required:
                return
            time.sleep(.05)

    def spent(self):
        delta = 0 if self.start_usage is None or self.usage is None else self.usage - self.start_usage
        return max(delta, self.recorded)

    def budget_check(self, estimate=0):
        if self.spent() + 2 * estimate >= self.cap - self.reserve - 1e-8:
            raise Stop("budget stop or insufficient budget for next step")
        if self.remaining is not None and self.remaining - 2 * estimate < 20 + self.reserve:
            raise Stop("account reserve would be crossed")

    def update_recorded(self):
        total = 0.0
        # Only directories created since our exclusive launch are candidates.
        # The pre-launch external-process check is the root verifier's job.
        for folder in set(self.results_dir.iterdir()) - self.initial_dirs:
            if not folder.is_dir():
                continue
            for path in folder.glob("*.json"):
                if path.name == "suite.json":
                    continue
                try:
                    record = json.loads(path.read_text())
                    if "cost_usd" in record:
                        total += number(record["cost_usd"])
                except (json.JSONDecodeError, OSError):
                    continue  # A writer may be atomically completing its record.
            suite = folder / "suite.json"
            if suite.exists():
                try:
                    for row in json.loads(suite.read_text())["rows"]:
                        if row.get("log") is None:
                            total += number(row.get("parse_cost_usd") or row.get("cost_usd") or 0)
                except (json.JSONDecodeError, OSError):
                    pass
        for path in self.explicit_outputs:
            if path.exists():
                try:
                    data = json.loads(path.read_text())
                    total += number(data.get("cost_usd") or data.get("charged_usd") or
                                    sum(number(r.get("cost_usd") or 0) for r in data.get("rows", [])))
                except (json.JSONDecodeError, OSError):
                    pass
        self.recorded = max(self.recorded, total)
        self.next_records = time.monotonic() + 2

    def validate_output(self, step, logfile, before_dirs):
        if step.get("output_kind") == "suite":
            matches = re.findall(r"^full results:\s*(.+?)\s*$", logfile.read_text(errors="replace"), re.M)
            if len(matches) != 1:
                raise Stop("missing or ambiguous batch completion marker")
            path = self.path(matches[0])
            folder = path.parent if path.name == "suite.json" else path
            if folder.parent != self.results_dir or folder in before_dirs or not (folder / "suite.json").is_file():
                raise Stop("batch completion output is not a new result")
            data = json.loads((folder / "suite.json").read_text())
            observed = [(r["task"], r["repeat"]) for r in data["rows"]]
            expected = [(task, step.get("repeat", 1)) for task in step["expected_tasks"]]
            if sorted(observed) != sorted(expected):
                raise Stop("batch tasks or repeats do not match the command")
            return {"batch": str(folder), "output": str(folder / "suite.json")}
        if step.get("output_kind") == "file":
            path = self.path(step["expected_output"])
            if not path.is_file():
                raise Stop("expected result file missing")
            json.loads(path.read_text())
            return {"batch": "", "output": str(path)}
        if step["kind"] == "paid":
            raise Stop("paid step lacks a verifiable completion output")
        return {"batch": "", "output": ""}

    def execute_step(self, step):
        self.check_integrity()
        paid = step["kind"] == "paid"
        estimate = number(step.get("estimate_usd", 0))
        wall_limit = number(step.get("max_seconds", 1920))
        if not 0 < wall_limit <= 1920:
            raise Stop("step wall budget must be within 1920 seconds")
        if paid and estimate <= 0:
            raise Stop("paid step requires a positive declared estimate")
        self.poll_account(required=True)
        self.update_recorded()
        self.budget_check(estimate)
        launch_window = wall_limit + 30 if self.launch_window is None else self.launch_window
        if paid and min(self.shutdown_monotonic - time.monotonic(), self.shutdown_epoch - time.time()) < launch_window:
            raise Stop("insufficient time for another full trial")
        if step.get("output_kind") == "file":
            output = self.path(step["expected_output"])
            if output.exists():
                raise Stop("result file already exists")
            self.explicit_outputs.add(output)
        argv = step["argv"]
        if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
            raise Stop("step argv must be a nonempty string array")
        environment = os.environ.copy()
        for key, value in step.get("env", {}).items():
            if any(s in key.upper() for s in ("API_KEY", "PASSWORD", "SECRET", "TOKEN")):
                raise Stop("credentials must not be embedded in configuration")
            if value is None:
                environment.pop(key, None)
            else:
                environment[key] = str(value)
        self.current = step["id"]
        logfile = self.log_dir / f"{len(self.completed):03d}.log"
        before_dirs = set(self.results_dir.iterdir())
        with os.fdopen(os.open(logfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as log:
            self.child = subprocess.Popen(argv, cwd=self.path(step.get("cwd", str(self.repo))),
                                          env=environment, stdout=log, stderr=subprocess.STDOUT,
                                          start_new_session=True)
            started = time.monotonic()
            self.status("running")
            while self.child.poll() is None:
                self.deadline_check()
                if time.monotonic() - started > wall_limit:
                    raise Stop("step time limit reached")
                self.poll_account()
                if time.monotonic() >= self.next_records:
                    self.update_recorded()
                    self.status("running")
                self.budget_check()
                time.sleep(.05)
            code = self.child.returncode
            self.cleanup_group(self.child)  # Also remove descendants surviving their parent.
            self.child = None
        self.deadline_check()
        if code != 0:
            raise Stop("step exited unsuccessfully")
        output = self.validate_output(step, logfile, before_dirs)
        # A completed paid run remains part of the record even if a subsequent
        # account read fails or the charge crosses our stop threshold.
        if step.get("manifest_line_template"):
            self.append(step["manifest_line_template"].format(**output))
        self.completed.append(step["id"])
        self.current = None
        self.status("running")
        self.poll_account(required=True)
        self.update_recorded()
        self.budget_check()
        self.status("running")

    def run(self):
        previous = {}
        try:
            self.check_integrity()
            lockpath = self.repo / ".verification" / "guarded-account.lock"
            lockpath.parent.mkdir(parents=True, exist_ok=True)
            self.lock = lockpath.open("a+")
            try:
                fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Stop("another guarded account operation is active") from None
            if self.manifest.exists() or self.status_path.exists() or self.log_dir.exists():
                raise Stop("existing run artifact; automatic resume is forbidden")
            self.results_dir.mkdir(parents=True, exist_ok=True)
            self.initial_dirs = set(self.results_dir.iterdir())
            self.manifest.parent.mkdir(parents=True, exist_ok=True)
            os.close(os.open(self.manifest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
            self.manifest_created = True
            self.log_dir.mkdir(mode=0o700)
            self.status("starting")
            def interrupted(signum, frame):
                raise Stop("launcher interrupted")
            for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
                previous[signum] = signal.signal(signum, interrupted)
            self.poll_account(required=True)
            self.start_usage = self.usage
            self.budget_check()
            self.status("running")  # Persist baseline before the first paid child.
            self.append(f"start {dt.datetime.now().isoformat()} usage {self.start_usage:.10f} cap {self.cap:.2f}")
            for line in self.config.get("manifest_header", []):
                self.append(line)
            ids = [s["id"] for s in self.config["steps"]]
            if len(ids) != len(set(ids)):
                raise Stop("duplicate step ids")
            for step in self.config["steps"]:
                if step.get("kind") not in ("paid", "preflight"):
                    raise Stop("unknown step kind")
                self.execute_step(step)
            self.append(f"end {dt.datetime.now().isoformat()} usage {self.usage:.10f}")
            self.status("complete")
            return 0
        except BaseException as exc:
            # Ignore repeated interrupts while guaranteeing owned-group cleanup.
            for signum in previous:
                signal.signal(signum, signal.SIG_IGN)
            self.cleanup_group(self.child)
            self.child = None
            self.cleanup_group(self.probe)
            self.probe = None
            reason = str(exc) if isinstance(exc, Stop) else f"launcher failure ({type(exc).__name__})"
            if self.manifest_created:
                self.append("STOP " + reason)
                self.status("stopped", reason)
            return 2
        finally:
            self.cleanup_group(self.child)
            self.cleanup_group(self.probe)
            for signum, handler in previous.items():
                signal.signal(signum, handler)
            if self.lock is not None:
                self.lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--account-probe", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.account_probe:
        return account_probe(args.account_probe)
    if not args.config:
        parser.error("--config is required")
    try:
        return Guard(args.config).run()
    except Exception:
        print("Launcher refused configuration; no experiment was started.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
