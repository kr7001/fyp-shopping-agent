"""A stub tree for dry runs of the stage command's chains (24 October 2026).

`tools/claim2_stage_command.py --root <tree>` points an emitted chain at this tree instead of
the repository: its runners, live check, preflight and account reader are stubs that call no
model and touch no shop, while its voids.py and pilot_check.py are the real ones, run from
the repository, so the chain's parsing of their output is the real thing. A scenario file in
the tree says what each stub does (a failing live check, a provider the routing forbids, a
refused preflight, a void, a run near its limits, an unreadable account, a slow run for the
watchdog), and a usage file stands for the account, which the stub suite bumps by each run's
cost, so the cap gate and the watchdog see spend as the real chain would.

Not a test module itself: tests/test_stage_command.py and tests/test_pilot_check.py import it.
"""
from __future__ import annotations

import json
import os
import pathlib
import stat
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402

REAL = paths.REPO
SCENARIO = "experiments/results/.scenario.json"
USAGE = "experiments/results/.usage"
DEEPSEEK = "deepseek/deepseek-v4-flash"
ROUTING = {DEEPSEEK: {"order": ["gmicloud", "deepinfra", "streamlake"], "allow_fallbacks": False,
                      "quantizations": ["fp8"]}}

TEE = ["tee-headline", "tee-target-price", "tee-cheapest-target", "tee-all-stocked", "tee-count-stocked",
       "tee-count-buyable", "tee-exists-under", "tee-top-3", "tee-xs-price", "tee-promo-check"]
DECLINES = ["decline-delivery", "decline-fit", "decline-scarcity"]
GATED = ["tee-target-price", "tee-cheapest-target", "tee-all-stocked", "tee-count-stocked",
         "tee-count-buyable", "tee-exists-under", "tee-top-3", "tee-xs-price"]
# The held-out tasks of the stand-in claim file: v2's by rw-NN, v3's by rw3-NN, each with the
# template it rewords.
HELD = [("rw-03", "tee-target-price"), ("rw-05", "tee-cheapest-target"), ("rw-07", "tee-all-stocked"),
        ("rw-11", "tee-count-buyable"), ("rw-13", "tee-exists-under"), ("rw-15", "tee-top-3"),
        ("rw-27", "decline-delivery"), ("rw3-01", "tee-xs-price"), ("rw3-02", "tee-promo-check"),
        ("rw3-03", "decline-fit"), ("rw3-04", "tee-headline"), ("rw3-05", "tee-count-stocked")]

STUB_SUITE = '''#!/usr/bin/env python3
"""Stub suite.py: writes a batch as the real one does, by the scenario; spends by bumping the usage file."""
import argparse, datetime, json, os, pathlib, sys, time
HERE = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, %(runners)r)
import provider_routing
scenario_path = HERE / %(scenario)r
scenario = json.loads(scenario_path.read_text())
ap = argparse.ArgumentParser()
ap.add_argument("--tasks"); ap.add_argument("--repeats", type=int, default=1)
ap.add_argument("--repeat-start", type=int, default=1); ap.add_argument("--only", nargs="*")
for flag in ("--box", "--exhaustive", "--box-exhaust", "--targeting"):
    ap.add_argument(flag, action="store_true")
for flag in ("--exhaustive-wording", "--reading", "--rate-plan", "--page-reader", "--parser-model"):
    ap.add_argument(flag)
ap.add_argument("--parser", default="rules"); ap.add_argument("--max-steps", type=int); ap.add_argument("--clock", type=int)
a = ap.parse_args()
model = os.environ.get("MODEL_NAME")
arm = ("box-model" if a.box and a.parser == "model" else "box" if a.box
       else "exhaustive-product" if a.exhaustive and a.exhaustive_wording == "product"
       else "exhaustive" if a.exhaustive else "none")
(HERE / "experiments/results/.suite_calls").open("a").write(json.dumps({"argv": sys.argv[1:], "model": model,
    "routing": os.environ.get("IGR_PROVIDER_ROUTING")}) + "\\n")
if arm in scenario.get("no_batch_for", []):
    sys.exit(0)
usage_file = HERE / %(usage)r
if scenario.get("spend_first"):
    # A real run's charges land while it runs; the watchdog's test needs them before the sleep.
    usage_file.write_text(f"{float(usage_file.read_text()) + scenario['spend_first']:.4f}")
time.sleep(scenario.get("sleep", 0))
spec = json.loads((HERE / a.tasks).read_text())
tasks = [t for t in spec["tasks"] if not a.only or t["id"] in a.only]
stamp = datetime.datetime.now().strftime("%%Y%%m%%dT%%H%%M%%S%%f")
out = HERE / "experiments/results" / stamp
out.mkdir(parents=True)
rows = []
for t in tasks:
    for repeat in range(a.repeat_start, a.repeat_start + a.repeats):
        cost = scenario.get("cost", {}).get(arm, {}).get(t["id"], scenario.get("default_cost", 0.1))
        void = t["id"] in scenario.get("void", []) and arm in scenario.get("void_arms", [arm])
        calls = scenario.get("calls", {}).get(t["id"], 20)
        elapsed = scenario.get("elapsed", {}).get(t["id"], 60)
        verdict = scenario.get("verdict", {}).get(t["id"], "correct")
        record = {"model": model, "elapsed_s": elapsed, "cost_usd": cost, "max_steps": a.max_steps, "clock_s": a.clock,
                  "error": "model call failed, reason: planted" if void else None,
                  "result": {"ok": not void, "final": "" if void else "an answer"},
                  "trace": {"tool_calls_total": calls}}
        (out / f"{t['id']}-{repeat}.json").write_text(json.dumps(record))
        rows.append({"task": t["id"], "family": t.get("family"), "gated": t.get("gated"), "repeat": repeat,
                     "verdict": "void" if void else verdict, "why": "", "answer": record["result"]["final"],
                     "tool_calls": calls, "actions": calls, "observations": 0, "cost_usd": cost,
                     "elapsed_s": elapsed, "error": record["error"], "log": None})
        usage_file.write_text(f"{float(usage_file.read_text()) + cost:.4f}")
        if void:
            # Void once: the re-run of the same slot comes back whole.
            scenario["void"] = [v for v in scenario["void"] if v != t["id"]]
            scenario_path.write_text(json.dumps(scenario))
boxed = a.box or a.box_exhaust
payload = {"ran_at": stamp, "repeats": a.repeats, "repeat_start": a.repeat_start, "policy": "off",
           "confidence": "off", "exhaustive": a.exhaustive, "exhaustive_wording": a.exhaustive_wording,
           "targeting": a.targeting, "box": a.box, "box_exhaust": a.box_exhaust, "arm": arm,
           "parser": a.parser if boxed else None, "parser_model": model if boxed and a.parser == "model" else None,
           "reading": a.reading, "page_reader": (a.page_reader or "rendered") if boxed else None,
           "rate_plan": (a.rate_plan or "bound") if boxed else None, "scaffold": "openjiuwen",
           "max_steps": a.max_steps, "clock_s": a.clock, "model": model,
           "provider_routing": {"agent": provider_routing.routing_for(model),
                                "parser": provider_routing.routing_for(model) if boxed and a.parser == "model" else None},
           "tasks_file": pathlib.Path(a.tasks).name, "draw": spec.get("brand", "?") + ":stub",
           "summary": {"total_cost": round(sum(r["cost_usd"] for r in rows), 4)}, "rows": rows}
(out / "suite.json").write_text(json.dumps(payload))
print(f"full results: {out}/suite.json")
'''

STUB_PROBE = '''#!/usr/bin/env python3
"""Stub parse_probe.py: writes a result file in the real shape, by the scenario; calls nothing."""
import argparse, datetime, json, os, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parents[2]
scenario = json.loads((HERE / %(scenario)r).read_text())
ap = argparse.ArgumentParser()
ap.add_argument("--questions"); ap.add_argument("--model"); ap.add_argument("--spec-from"); ap.add_argument("--page-from")
ap.add_argument("--only-templates", nargs="+")
a = ap.parse_args()
entries = json.loads((HERE / a.questions).read_text())["paraphrases"] if (HERE / a.questions).exists() else [{}] * 30
kept = [e for e in entries if a.only_templates is None or e.get("template") is None or e.get("template") in a.only_templates]
provider = scenario.get("provider", "GMICloud")
rows = [{"id": e.get("id", n), "provider": provider, "call_failed": False, "cost_usd": 0.0004} for n, e in enumerate(kept, 1)]
stamp = datetime.datetime.now().strftime("%%Y%%m%%dT%%H%%M%%S%%f")
out = HERE / "experiments/results" / f"parse-probe-{pathlib.Path(a.questions).stem}-{stamp}.json"
out.write_text(json.dumps({"model": a.model, "charged_usd": round(0.0004 * len(rows), 6), "calls_failed": 0,
                           "rows": rows, "only_templates": a.only_templates, "spec_from": a.spec_from,
                           "page_from": a.page_from, "env_routing": os.environ.get("IGR_PROVIDER_ROUTING")}))
usage_file = HERE / %(usage)r
usage_file.write_text(f"{float(usage_file.read_text()) + 0.0004 * len(rows):.4f}")
print(f"written: {out}")
'''

STUB_CLAIM = '''#!/usr/bin/env python3
"""Stub claim.py --preflight: refuses the arms the scenario names, records the model it ran under."""
import argparse, json, os, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parents[2]
scenario = json.loads((HERE / %(scenario)r).read_text())
ap = argparse.ArgumentParser()
ap.add_argument("--protocol"); ap.add_argument("--preflight"); ap.add_argument("--flags")
a = ap.parse_args()
(HERE / "experiments/results/.preflights").open("a").write(json.dumps({"arm": a.preflight, "flags": a.flags,
    "model": os.environ.get("MODEL_NAME")}) + "\\n")
if a.preflight in scenario.get("preflight_refuse", []):
    print(f"REFUSED: planted for {a.preflight}")
    sys.exit(1)
print("within what the protocol requires: the batch may run")
'''

STUB_CHECK = '''#!/usr/bin/env python3
"""Stub check_aplus_market.py: passes or fails by the scenario; --search-terms prints one row."""
import json, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parents[1]
scenario = json.loads((HERE / %(scenario)r).read_text())
if "--search-terms" in sys.argv:
    print(sys.argv[-1].lower() + " tee\\t45\\t3\\t2026-10-24 10:00:00")
    sys.exit(0)
print("live check of", sys.argv[1:])
sys.exit(scenario.get("livecheck_exit", 0))
'''

STUB_CELL_FACTS = '''"""Stub cell_facts.account_usage: the usage file, or None when the scenario says unreadable."""
import json, pathlib
HERE = pathlib.Path(__file__).resolve().parents[2]
def account_usage():
    scenario = json.loads((HERE / %(scenario)r).read_text())
    if scenario.get("usage_unreadable"):
        return None
    return float((HERE / %(usage)r).read_text())
'''

SHIM = '''#!/usr/bin/env python3
"""The real %(name)s, run from the repository against this tree's batches."""
import runpy, sys
sys.argv[0] = %(real)r
runpy.run_path(%(real)r, run_name="__main__")
'''

VENV_PYTHON = "#!/bin/sh\nexec python3 \"$@\"\n"


def analysis_file() -> dict:
    """A tee-only analysis file in the 24 October shape: the current file's arms, with the
    sets and the design of the redesign."""
    current = json.loads((paths.TASKS / "claim2_analysis.json").read_text())
    return {**current, "version": 8,
            "sets": {"control": ["tee-headline"], "decline": DECLINES, "gated": GATED, "lookup": ["tee-promo-check"],
                     "two_readings": ["tee-all-stocked", "tee-count-stocked"],
                     "reading_independent": [q for q in GATED if q not in ("tee-all-stocked", "tee-count-stocked")]
                     + ["tee-promo-check"], "held_out": "template"},
            "design": {DEEPSEEK: {"asks": {"shipped": {"templates": [1, 2, 3]},
                                           "open everything (product)": {"gated": [1, 2, 3]},
                                           "the block (rules)": {"templates": [1, 2, 3], "held_out": [1]},
                                           "the block (model)": {"templates": [1, 2, 3], "held_out": [1]}},
                                  "tests": ["H1", "H2", "H3", "H4"]}}}


def task_file(brand: str, held: bool) -> dict:
    """A stand-in task file: the thirteen templates, each keyed but the declines, and with
    `held` the held-out tasks of `HELD`, each with the template it rewords and a note naming
    its file as the generator writes it."""
    lead = f"Go to {{base}}/catalogsearch/result/?q={brand} ."
    tasks = []
    for t in TEE + DECLINES:
        expect = {"kind": "none"} if t.startswith("decline") else {"kind": "price", "target": 1.0}
        tasks.append({"id": t, "family": "aplus", "product": "tee", "gated": t in GATED or t == "tee-promo-check",
                      "query": f"{lead} the wording of {t}", "expect": expect, "box": {"outcome": "plan", "kind": "x"}})
    if held:
        for hid, template in HELD:
            base = next(x for x in tasks if x["id"] == template)
            source = "paraphrases_v3.json" if hid.startswith("rw3-") else "paraphrases_v2.json"
            tasks.append({**base, "id": hid, "template": template, "rewording": int(hid.split("-")[1]),
                          "note": f"Held-out rewording {int(hid.split('-')[1])} of {template} ({source}).",
                          "query": f"{lead} reworded {template} as {hid}"})
    return {"brand": brand, "base_url": "http://localhost:7770", "fixture": f"{brand.lower()}.json", "tasks": tasks}


def paraphrase_file(ids_and_templates) -> dict:
    """A held-out paraphrase file's shape with no text to speak of: ids and templates only,
    None for a reading-test-only entry."""
    return {"templates": None, "base_url": None, "lead": None, "page_from": None,
            "paraphrases": [{"id": n, "template": t, "text": "x", "expected": "plan", "label": "clear",
                             "meaning_kept": True} for n, t in ids_and_templates]}


def fixture(brand: str, listings: int) -> dict:
    return {"_generated": {"brand": brand, "sku_prefix": "IGR-STUB"},
            "families": [{"product": "tee", "seller": f"Seller {i}"} for i in range(listings)]}


def build(root: pathlib.Path, scenario: dict | None = None, usage: float = 10.0) -> pathlib.Path:
    """The stub tree under `root`: the stubs, the shims, the stand-in files and the scenario."""
    files = {
        "experiments/runners/suite.py": STUB_SUITE % {"runners": str(paths.EXPERIMENTS / "runners"),
                                                      "scenario": SCENARIO, "usage": USAGE},
        "experiments/runners/parse_probe.py": STUB_PROBE % {"scenario": SCENARIO, "usage": USAGE},
        "experiments/analysis/claim.py": STUB_CLAIM % {"scenario": SCENARIO},
        "experiments/analysis/cell_facts.py": STUB_CELL_FACTS % {"scenario": SCENARIO, "usage": USAGE},
        "experiments/analysis/voids.py": SHIM % {"name": "voids.py", "real": str(paths.EXPERIMENTS / "analysis" / "voids.py")},
        "experiments/analysis/pilot_check.py": SHIM % {"name": "pilot_check.py",
                                                       "real": str(paths.EXPERIMENTS / "analysis" / "pilot_check.py")},
        "env/check_aplus_market.py": STUB_CHECK % {"scenario": SCENARIO},
        ".venv-naive/bin/python": VENV_PYTHON,
    }
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    (root / "experiments/results").mkdir(parents=True, exist_ok=True)
    (root / "experiments/tasks").mkdir(parents=True, exist_ok=True)
    (root / "env/fixtures").mkdir(parents=True, exist_ok=True)
    write(root / "experiments/tasks/claim2_analysis.json", analysis_file())
    write(root / "experiments/tasks/tasks_dev.json", task_file("Devbrand", held=False))
    write(root / "experiments/tasks/tasks_claim.json", task_file("Wexcombe", held=True))
    write(root / "experiments/tasks/paraphrases_v2.json",
          paraphrase_file([(3, "tee-target-price"), (5, "tee-cheapest-target"), (17, "water-target-price"),
                           (27, "decline-delivery"), (29, "decline-taste")]))
    write(root / "experiments/tasks/paraphrases_v3.json",
          paraphrase_file([(1, "tee-xs-price"), (2, "tee-promo-check"), (3, None), (4, "decline-fit")]))
    write(root / "env/fixtures/devbrand.json", fixture("Devbrand", 45))
    write(root / "env/fixtures/wexcombe.json", fixture("Wexcombe", 45))
    write(root / SCENARIO, scenario or {})
    (root / USAGE).write_text(f"{usage:.4f}")
    # A .env with the keys the scenario names, each set to a made-up value the chain must never
    # read or print (`env_keys`), or with the raw lines it gives (`env_lines`, for the other forms
    # python-dotenv reads); none of the keys is in the environment the chain runs under.
    lines = [f"{key}=0.73" for key in (scenario or {}).get("env_keys", [])] + (scenario or {}).get("env_lines", [])
    if lines:
        (root / ".env").write_text("".join(line + "\n" for line in lines))
    return root


def write(path: pathlib.Path, content: dict) -> None:
    path.write_text(json.dumps(content, indent=1))


def generate(root: pathlib.Path, stage: str, **flags) -> str:
    """The chain the generator emits for this tree, as text."""
    argv = [sys.executable, str(REAL / "tools" / "claim2_stage_command.py"), "--stage", stage, "--root", str(root),
            "--analysis", "experiments/tasks/claim2_analysis.json", "--watchdog-interval", "1",
            "--routing", json.dumps(ROUTING), "--reading-files", "experiments/tasks/paraphrases_v2.json",
            "experiments/tasks/paraphrases_v3.json"]
    if stage == "pilot":
        argv += ["--tasks", "experiments/tasks/tasks_dev.json", "--fixture", str(root / "env/fixtures/devbrand.json"),
                 "--stage1-tasks", "experiments/tasks/tasks_claim.json", "--stage1-cap", "69", "--tag", "pilot-test",
                 "--cap", "6"]
    else:
        argv += ["--tasks", "experiments/tasks/tasks_claim.json", "--fixture", str(root / "env/fixtures/wexcombe.json"),
                 "--tag", "stage1-test", "--cap", "69"]
    for flag, value in flags.items():
        argv += [f"--{flag.replace('_', '-')}", str(value)]
    done = subprocess.run(argv, capture_output=True, text=True, check=True)
    return done.stdout


def run_chain(root: pathlib.Path, text: str, timeout: int = 180) -> subprocess.CompletedProcess:
    """Execute an emitted chain in the stub tree, with no routing or model in the environment
    but what the chain itself exports."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("IGR_") and k != "MODEL_NAME"}
    return subprocess.run(["bash", "-c", text], cwd=root, env=env, capture_output=True, text=True, timeout=timeout)


def manifest(root: pathlib.Path, tag: str) -> str:
    path = root / "experiments/results" / f"{tag}.manifest"
    return path.read_text() if path.exists() else ""


def calls(root: pathlib.Path, name: str) -> list[dict]:
    path = root / "experiments/results" / name
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
