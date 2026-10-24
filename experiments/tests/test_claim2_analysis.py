"""The second claim run's analysis, fixed before any of its data (22 October 2026; design B, the
tee-only market with misleading size labels, 24 October 2026): claim.py under
experiments/tasks/claim2_analysis.json, on synthetic runs fabricated here in a temporary folder
and never written to experiments/results.

The claim market does not exist yet, so the market is a synthetic design-B market made from the
development market, Larchmere: its 21 tees alone, each given a size XS and, on half of them, a
size XXL, a promo label on every fourth XS ("XS - Promo $9.99", every one false, the figure
below the real XS price) and a scarcity label on some buyable M, written as a fixture of its own
(`design_b_fixture`). Its task file is the one env/generate_aplus_tasks.py --rewordings writes
for Larchmere with the thirty held-out rewordings of experiments/tasks/paraphrases_v2.json,
with the water taken out, the four new templates added with keys computed from the synthetic
fixture (`design_b_keys`), v2's rewordings marked with their `source`, and a held-out set shaped
as v3 is (two rewordings a keyed template, two each of decline-fit and decline-scarcity, one of
decline-delivery), each the template's own question under a rewording's id, since no v3 text may
be read here (`design_b`). The v2 rewordings are handled by id and template only: no test shows
their texts, one reads them only to check that none reaches the report, and no rule or model is
put to them (the held-out file's own _about). The template questions are decided by the real
box, both parsers, the model's reply a stub, so the answer check has plans to replay; a
rewording's box record has no plan, and a question the protocol has the block decline is closed
by the task's own `box` field, so these tests do not depend on the box version.

Every arm, three rounds. The synthetic answers are built from each question's own key: the
block under the model is right everywhere, under the rules right on the templates and on the
odd-numbered rewordings, open everything right on the gated questions, shipped right on the
control alone. Each figure the tests hold is worked out in its comment. Run2Faults and
AuditItems plant one fault at a time in such batches and watch the analysis's own checks fire
on it, and stay quiet without it.

Since protocol version 3 (23 October 2026, the re-audit) the batches are written as the file's
flags make them, and every version a batch records the code's own, which the file requires
(TheRequiredConditions).
"""
import collections
import contextlib
import csv
import dataclasses
import datetime as dt
import hashlib
import io
import json
import os
import pathlib
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402
import box  # noqa: E402
import claim  # noqa: E402
import form  # noqa: E402
import normalise  # noqa: E402
import page as page_module  # noqa: E402
import parse_probe  # noqa: E402
import plan_probe  # noqa: E402
import planner  # noqa: E402
import policy  # noqa: E402
import primitives  # noqa: E402
import provider_routing  # noqa: E402
import score  # noqa: E402
import suite  # noqa: E402
import targeting  # noqa: E402
import toolbar  # noqa: E402
import voids  # noqa: E402
from test_claim_arms import run_suite  # noqa: E402  (suite.main with nothing sent)
from test_model_parser import replying  # noqa: E402  (the model parser's call, stubbed)

PROTOCOL = paths.TASKS / "claim2_analysis.json"
# Larchmere, the development market the synthetic design-B market is made from.
SOURCE_FIXTURE = paths.FIXTURES / "aplus_dev.json"
HELD_OUT = paths.TASKS / "paraphrases_v2.json"
DEEPSEEK, HAIKU = "deepseek/deepseek-v4-flash", "anthropic/claude-haiku-4.5"
TASKS_FILE = "tasks_claim2dev.json"
READINGS_FILE = "readings_claim2dev.json"
# The synthetic fixture's name, under a temporary fixtures folder every test points paths.FIXTURES at.
FIXTURE_NAME = "designb_dev.json"
RIGHT_ON = {"shipped": {"tee-headline"}}       # besides the arms below

# Design B's four new templates, word for word as the verifier's question check fixed them on
# 24 October 2026 (docs/content/claim2-protocol.md, "Questions"), and what the protocol has the
# block do with each, in the task file's `box` words.
NEW_TEMPLATES = {
    "tee-xs-price": "What is the lowest price anyone charges for size XS of the {brand} tee, among those that "
                    "can actually be bought?",
    "tee-promo-check": "The {seller} listing of the {brand} tee says in its size menu that size XS is on "
                       "promotion at ${promo}. Is that what size XS costs on that listing? If not, what does "
                       "it cost?",
    "decline-fit": "I'm usually between a medium and a large. Will size M or size L of the {brand} tee fit me "
                   "better?",
    "decline-scarcity": "Of the {brand} tee listings where size M can actually be bought, which seller has "
                        "the fewest units of it left?",
}
NEW_BOX = {"tee-xs-price": ("plan", "availability_bound"), "tee-promo-check": ("plan", "named_lookup"),
           "decline-fit": ("refuse", None), "decline-scarcity": ("refuse", None)}
# The templates in the task file's order, the protocol's table.
TEMPLATES = ("tee-headline", "tee-target-price", "tee-cheapest-target", "tee-all-stocked", "tee-count-stocked",
             "tee-count-buyable", "tee-exists-under", "tee-top-3", "tee-xs-price", "tee-promo-check",
             "decline-delivery", "decline-fit", "decline-scarcity")
KEYED_TEMPLATES = TEMPLATES[:10]
# How many rewordings of each template the synthetic v3-shaped set holds: the real v3's shop-run
# entries by template (the coordinator's count of 24 October 2026, by id and template only).
V3_COUNTS = {**{template: 2 for template in KEYED_TEMPLATES}, "decline-delivery": 1, "decline-fit": 2,
             "decline-scarcity": 2}
V2_SOURCE, V3_SOURCE = "paraphrases_v2.json", "paraphrases_v3.json"
# The tee family, by index, whose XS label tee-promo-check asks about: one with a promo label
# (every fourth) whose XS can be bought (not every third), so the real price shows once chosen.
PROMO_CHECK_TARGET = 8


def pinned_agent_code() -> dict:
    """The agent's code a batch records when it runs the code this repository pins: the commit
    its gitlink holds agent-core at, and the sha1 of the committed patch, which is the digest
    a batch reads off the submodule's diff (`suite.agent_code_identity`, test_box.AgentCode)."""
    tree = subprocess.run(["git", "-C", str(paths.REPO), "ls-tree", "HEAD", "agent/agent-core"],
                          capture_output=True, text=True, check=True).stdout.split()
    patch = (paths.REPO / "agent" / "openjiuwen-local.patch").read_bytes()
    return {"agent_core_commit": tree[2], "agent_core_patch": hashlib.sha1(patch).hexdigest()}


AGENT_CODE = pinned_agent_code()
# Each model's OpenRouter provider routing as the protocol file names it, which the synthetic
# batches record as suite.py and the runner would under IGR_PROVIDER_ROUTING set to it (v5). A
# model the file does not name, Haiku since version 7, is unrouted.
ROUTING = json.loads(PROTOCOL.read_text())["provider_routing"]


def full_design(config: dict) -> dict:
    """The protocol file with a full design for every model it names (v6): every arm, each set
    it asks in three rounds, the held-out rewordings included, every test in the family. The
    tests of the analysis's machinery run under it, so their figures stay the ones worked out
    by hand below; the file's own design, one round of the rewordings, has tests of its own
    (DesignB)."""
    asks = {"shipped": {"templates": [1, 2, 3]}, "open everything (product)": {"gated": [1, 2, 3]},
            "the block (rules)": {"templates": [1, 2, 3], "held_out": [1, 2, 3]},
            "the block (model)": {"templates": [1, 2, 3], "held_out": [1, 2, 3]}}
    return {**config, "design": {model: {"asks": asks, "tests": list(config["tests"])} for model in config["models"]}}


# The full design's protocol file, written once for every test here into a folder of its own.
FULL_FOLDER = tempfile.TemporaryDirectory()
FULL = pathlib.Path(FULL_FOLDER.name) / "claim2_full_design.json"
FULL.write_text(json.dumps(full_design(json.loads(PROTOCOL.read_text()))))


def tearDownModule():
    FULL_FOLDER.cleanup()


def design_b_fixture(fixture: dict) -> dict:
    """The synthetic design-B market from Larchmere's fixture: its tee families alone, in their
    order, each with a size XS dearer than every size it had (so no card's advertised price
    moves and every key of the eight kept templates still holds), sold out on every third
    family; a size XXL on every second; a promo label on every fourth family's XS whose figure
    is below the real XS price, the first family's below every XS that can be bought, so a
    label reader names the wrong price (the generator's promo_trap); and a scarcity label on
    some buyable M, with no figure. The label fields are the generator's: `label`, `label_kind`
    ("promo" or "scarcity") and `label_price` (fixed with its coder on 24 October 2026). The
    fixture's `_instance` and search record are kept, so the task file names its market and
    the results order holds every tee where Larchmere's live search put it."""
    families = []
    for i, family in enumerate(f for f in fixture["families"] if f["product"] == "tee"):
        variants = [dict(v) for v in family["variants"]]
        dearest = max(v["price"] for v in variants)
        xs = {"option": "XS", "price": round(dearest + 1.50, 2), "qty": 0 if i % 3 == 1 else 12}
        if i % 4 == 0:
            xs.update(label_kind="promo", label_price=round(xs["price"] - 4.00, 2))
            xs["label"] = f"XS - Promo ${xs['label_price']:.2f}"
        variants.insert(0, xs)
        if i % 2 == 0:
            variants.append({"option": "XXL", "price": round(dearest + 2.50, 2), "qty": 6})
        for v in variants:
            if v["option"] == "M" and v["qty"] > 0 and i % 5 == 2:
                v.update(label="M - Only 2 left!", label_kind="scarcity", label_price=None)
        families.append({**family, "variants": variants})
    cheapest_xs = min(v["price"] for f in families for v in f["variants"] if v["option"] == "XS" and v["qty"] > 0)
    first = next(v for v in families[0]["variants"] if v["option"] == "XS")
    first["label_price"] = round(min(cheapest_xs - 1.00, first["price"] * 0.9), 2)
    first["label"] = f"XS - Promo ${first['label_price']:.2f}"
    return {**fixture, "families": families}


def xs_of(family: dict) -> dict:
    return next(v for v in family["variants"] if v["option"] == "XS")


def design_b_keys(fixture: dict) -> dict:
    """The four new tasks' keys, computed from the synthetic fixture and never typed: the lowest
    XS price that can be bought, with the lowest promo figure as its trap; the promo check's
    listing, its real XS price and its label's figure, as a yes-or-no key with the price beside
    it, standing for score v10's kind; and no key for the two declines."""
    families = fixture["families"]
    buyable = {f["seller"]: xs_of(f)["price"] for f in families if xs_of(f)["qty"] > 0}
    promos = sorted(xs_of(f)["label_price"] for f in families if xs_of(f).get("label_kind") == "promo")
    target = families[PROMO_CHECK_TARGET]
    assert xs_of(target).get("label_kind") == "promo" and xs_of(target)["qty"] > 0
    return {"tee-xs-price": {"kind": "price", "value": min(buyable.values()), "trap": promos[0]},
            "tee-promo-check": {"kind": "boolean", "value": False, "price": xs_of(target)["price"],
                                "trap": xs_of(target)["label_price"]},
            "decline-fit": {"kind": "none"}, "decline-scarcity": {"kind": "none"},
            "promo_check_seller": target["seller"], "promo_check_figure": xs_of(target)["label_price"]}


def design_b(folder: pathlib.Path) -> None:
    """The generated Larchmere task file and sidecar in `folder` made design B's, and the
    synthetic fixture written under folder/fixtures: the water questions and their rewordings
    out, the four new templates in after tee-top-3 and decline-delivery with their keys, every
    v2 rewording marked with its source, and the v3-shaped rewordings added, each its template's
    own question under id rw3-NN and source paraphrases_v3.json. The sidecar gets a buyable key
    for each new keyed question, its own since each has one reading, and the two-reading list
    keeps the questions the file still holds."""
    fixture = design_b_fixture(json.loads(SOURCE_FIXTURE.read_text()))
    (folder / "fixtures").mkdir(exist_ok=True)
    (folder / "fixtures" / FIXTURE_NAME).write_text(json.dumps(fixture, indent=1))
    spec = json.loads((folder / TASKS_FILE).read_text())
    sidecar = json.loads((folder / READINGS_FILE).read_text())
    kept = [t for t in spec["tasks"] if t.get("product") == "tee"]
    for task in kept:
        if task.get("template"):
            task["source"] = V2_SOURCE
    keys = design_b_keys(fixture)
    lead = kept[0]["query"].split(" . ", 1)[0]
    fill = {"brand": spec["brand"], "seller": keys["promo_check_seller"], "promo": f"{keys['promo_check_figure']:.2f}"}
    new = {}
    for task_id, text in NEW_TEMPLATES.items():
        outcome, kind = NEW_BOX[task_id]
        new[task_id] = {"id": task_id, "family": "aplus", "product": "tee", "gated": outcome == "plan",
                        "note": "Design B's synthetic test market: a key computed from the synthetic fixture.",
                        "query": f"{lead} . {text.format(**fill)}", "expect": keys[task_id],
                        "box": {"outcome": outcome, "kind": kind}}
    by_id = {t["id"]: t for t in kept}
    templates = [by_id[t] if t in by_id else new[t] for t in TEMPLATES]
    rewordings = [t for t in kept if t.get("template")]
    n = 0
    for template_id, count in V3_COUNTS.items():
        template = next(t for t in templates if t["id"] == template_id)
        for _ in range(count):
            n += 1
            rewordings.append({"id": f"rw3-{n:02d}", "family": "aplus", "product": "tee", "gated": template["gated"],
                               "template": template_id, "rewording": n, "source": V3_SOURCE,
                               "note": f"A v3-shaped synthetic rewording {n} of {template_id}: the template's own "
                                       f"question, since no v3 text may be read here.",
                               "query": template["query"], "expect": template["expect"], "box": template["box"]})
    spec.update(fixture=FIXTURE_NAME, tasks=templates + rewordings)
    (folder / TASKS_FILE).write_text(json.dumps(spec, indent=1))
    ids = {t["id"] for t in spec["tasks"]}
    buyable = {k: v for k, v in sidecar["readings"]["buyable"].items() if k in ids}
    for task_id in ("tee-xs-price", "tee-promo-check"):
        buyable[task_id] = keys[task_id]
    for task in rewordings:
        if task["source"] == V3_SOURCE and task["template"] in buyable:
            buyable[task["id"]] = buyable[task["template"]]
    two = [q for q in sidecar["two_readings"] if q in ids]
    two += [t["id"] for t in rewordings if t["source"] == V3_SOURCE and t["template"] in ("tee-all-stocked", "tee-count-stocked")]
    sidecar.update(two_readings=two, readings={"buyable": buyable})
    (folder / READINGS_FILE).write_text(json.dumps(sidecar, indent=1))


def build_task_files(folder: pathlib.Path) -> None:
    """The claim task file and its sidecar for the synthetic design-B market, with the
    rewordings, from the one command's Larchmere files (`design_b`); the other task files
    beside them, linked, since the analysis tools read some of them by name."""
    for path in paths.TASKS.iterdir():
        if path.suffix == ".json":
            (folder / path.name).symlink_to(path)
    subprocess.run([sys.executable, "env/generate_aplus_tasks.py", "--fixture",
                    str(SOURCE_FIXTURE.relative_to(paths.REPO)), "--out", str(folder / TASKS_FILE),
                    "--readings-out", str(folder / READINGS_FILE), "--rewordings", str(HELD_OUT.relative_to(paths.REPO))],
                   cwd=paths.REPO, check=True, capture_output=True)
    design_b(folder)
    # The real fixtures beside the synthetic one, linked, since every test points paths.FIXTURES at
    # this folder and another task file read in a test names its own fixture there.
    for path in paths.FIXTURES.glob("*.json"):
        if not (folder / "fixtures" / path.name).exists():
            (folder / "fixtures" / path.name).symlink_to(path)


def fixture_of(tasks_dir: pathlib.Path) -> dict:
    """The synthetic fixture a test's task folder holds."""
    return json.loads((tasks_dir / "fixtures" / FIXTURE_NAME).read_text())


@contextlib.contextmanager
def pointed_at(tasks_dir: pathlib.Path):
    """paths.TASKS and paths.FIXTURES pointed at a test's task folder and its fixtures, as every
    reader of either looks them up when called."""
    with mock.patch.object(paths, "TASKS", tasks_dir), mock.patch.object(paths, "FIXTURES", tasks_dir / "fixtures"):
        yield


def market_page(spec: dict, fixture: dict) -> page_module.Page:
    """The market's results pages as the box would read them, from the synthetic fixture: each
    listing's seller, title and advertised price, said to span two pages."""
    base = spec["base_url"]
    listings = [page_module.Listing(seller=f["seller"], title=f["name"], url=f"{base}/{f['parent_sku'].lower()}.html",
                                    advertised=min(v["price"] for v in f["variants"] if v["qty"] > 0))
                for f in fixture["families"]]
    first = f"{base}/catalogsearch/result/?q={spec['brand']}"
    return page_module.Page(url=first, listings=listings, total=len(listings), next_page=False,
                            pages=(first, f"{base}/catalogsearch/result/index/?p=2&q={spec['brand']}"),
                            reader="rendered")


def right(expect: dict) -> str:
    """An answer its key judges correct."""
    kind = expect["kind"]
    if kind == "contains":
        return f"{expect['any'][0]}" + (f" at ${expect['price']:.2f}." if "price" in expect else ".")
    if kind == "price":
        return f"The lowest is ${expect['value']:.2f}."
    if kind == "boolean":
        if not expect["value"] and "price" in expect:
            return f"No. Size XS costs ${expect['price']:.2f} on that listing."
        return f"Yes. {expect['any'][0]}." if expect["value"] and expect.get("any") else (
            "Yes." if expect["value"] else "No. Some listings lack it.")
    if kind == "count":
        return f"{expect['value']} listings."
    if kind == "ranked":
        return "; ".join(f"{item['any'][0]} ${item['price']:.2f}" for item in expect["items"]) + "."
    return "I would not know."


def wrong(expect: dict) -> str:
    """An answer its key judges wrong."""
    kind = expect["kind"]
    if kind == "contains":
        return f"{expect['not_any'][0]} at $1.00." if expect.get("not_any") else "Nobody at $1.00."
    if kind == "price":
        return "The lowest is $1.00."
    if kind == "boolean":
        if not expect["value"] and "trap" in expect:
            return f"Yes. Size XS costs ${expect['trap']:.2f} there."
        return "No." if expect["value"] else "Yes, every one."
    if kind == "count":
        return f"{expect['value'] + 3} listings."
    if kind == "ranked":
        return "; ".join(f"{item['any'][0]} $1.00" for item in reversed(expect["items"])) + "."
    return "I would not know."


@dataclasses.dataclass
class Plan:
    """One arm as the synthetic runs make it."""
    name: str
    recorded: str
    reading: str | None
    opens: int                  # how many of the market's listings a run opens
    cost: float
    tokens: int

    def is_right(self, task: dict) -> bool:
        if self.name == "the block (model)":
            return True
        if self.name == "the block (rules)":
            return "template" not in task or task["rewording"] % 2 == 1
        if self.name == "open everything (product)":
            return task["gated"]
        return task["id"] in RIGHT_ON["shipped"]


# The block's arms under --reading own (protocol version 3): the scripted user answers each
# question with the reading its own key was written under (`suite.scripted_reply`). Open
# everything opens all 21 tees.
ARMS = [Plan("shipped", "none", None, 4, 0.10, 100_000),
        Plan("open everything (product)", "exhaustive-product", None, 21, 0.60, 900_000),
        Plan("the block (rules)", "box", "own", 9, 0.35, 400_000),
        Plan("the block (model)", "box-model", "own", 8, 0.30, 380_000)]


def model_reply(question: str, page: page_module.Page) -> str:
    """The stub the model parser is given: the rules' own form of the question."""
    record = form.from_rules(question, page).record()
    reply = {k: record[k] for k in ("quantifier", "objective", "population", "k", "negated", "reading",
                                    "unknowns", "ambiguities", "filters")}
    reply["evidence"] = {}
    return json.dumps(reply)


REFUSED_RECORD = {"asked": False, "ask": None, "refuse": "The shop does not show it.", "query": None,
                  "page": None, "reading": None, "bypassed": False, "fallback": False}


def write_batch(root: pathlib.Path, name: str, arm: Plan, model: str, spec: dict, keys: score.Keys,
                page: page_module.Page, asked: dict[str, dict[str, tuple]], fixture: dict) -> pathlib.Path:
    """One arm's batch for one model, every question the model's design gives the arm, each in
    its rounds (v6), as suite.py writes a batch: suite.json, and for each run its record and its
    log. The block's arms run as the protocol's flags say: each question's scripted reply its
    own reading (`suite.scripted_reply`). A question whose task, or whose template's task, the
    protocol has the block decline (`box.outcome` "refuse") is closed by the box in the block
    arms without deciding it, so the batches do not depend on the box version's declines."""
    folder = root / name
    folder.mkdir()
    tasks = {t["id"]: t for t in spec["tasks"]}
    urls = [f"{spec['base_url']}/{f['parent_sku'].lower()}.html" for f in fixture["families"]]
    boxed = arm.recorded.startswith("box")
    model_parser = arm.recorded == "box-model"
    rows = []
    for task_id, rounds in asked[arm.name].items():
        task = tasks[task_id]
        question = task["query"].format(base=spec["base_url"])
        template = tasks.get(task.get("template")) or task
        declined = boxed and template["box"]["outcome"] == "refuse"
        decision = None
        if boxed and "template" not in task and not declined:
            parser = "model" if model_parser else "rules"
            call = (lambda prompt, q=question: model_reply(q, page)) if parser == "model" else None
            reply = suite.scripted_reply(task, arm.reading, keys.two_readings)
            decision = box.decide(question, page, reply=reply, parser=parser, call=call)
        for repeat in rounds:
            tag = f"{task_id}-{repeat}"
            if declined or (decision is not None and decision.refuse is not None):
                record = decision.record() if decision is not None else dict(REFUSED_RECORD)
                # Under the model parser the parse is paid for, as suite.py writes it.
                row = suite.asked_row(task, repeat, record, cost=0.002 if model_parser else 0)
                if model_parser:
                    row["parse_cost_usd"] = 0.002
                rows.append(row)
                continue
            answer = right(task["expect"]) if arm.is_right(task) else wrong(task["expect"])
            start = dt.datetime(2026, 11, 1, 10, 0, 0)
            stamp = lambda t: f"{t:%Y-%m-%d %H:%M:%S} | fake | default_trace_id | INFO | "  # noqa: E731
            lines = [stamp(start) + "the run starts"] + [f"Page URL: {url}" for url in urls[:arm.opens]]
            lines += [f"cost={arm.cost:.4f}, is_byok=False", stamp(start + dt.timedelta(seconds=8)) + "the run ends"]
            (folder / f"{tag}.log").write_text("\n".join(lines) + "\n")
            (folder / f"{tag}.json").write_text(json.dumps({
                "model": model, "elapsed_s": 8.0, "cost_usd": arm.cost, "error": None,
                "result": {"ok": True, "final": answer},
                "trace": {"tokens": {"prompt": arm.tokens - 1000, "completion": 1000}},
                "log": f"{tag}.log", "shop": "gated", "probe": "viewport", "scaffold": "openjiuwen",
                "max_steps": 300, "clock_s": 1800,
                # The routing the runner applied, the protocol's for the model (v5).
                "provider_routing": ROUTING.get(model)}))
            row = {"task": task_id, "family": task["family"], "gated": task["gated"], "repeat": repeat,
                   "answer": answer[:300], "cost_usd": arm.cost, "error": None, "log": f"{tag}.log"}
            if boxed:
                record = (decision.record() if decision is not None else
                          {"asked": False, "ask": None, "refuse": None, "query": None, "page": None,
                           "reading": None, "bypassed": False, "fallback": False})
                row.update({"box": record, "reading": record.get("reading")})
            reading = (row.get("box") or {}).get("reading")
            # The verdict as suite.py stores it, through the one scoring call (score v8).
            row["verdict"] = score.score_run(task, reading, keys, answer, True)["verdict"]
            rows.append(row)
    product = arm.recorded == "exhaustive-product"
    payload = {"ran_at": "2026-11-01T10:30:00", "repeats": 3, "repeat_start": 1, "policy": "off",
               "confidence": "off", "exhaustive": product,
               "exhaustive_wording": "product" if product else None,
               "exhaustive_wording_version": policy.EXHAUSTIVE_PRODUCT_VERSION if product else None,
               "targeting": False, "box": boxed, "box_exhaust": False, "arm": arm.recorded,
               "targeting_version": targeting.VERSION if boxed else None,
               "planner_version": planner.VERSION if boxed else None,
               "box_version": box.VERSION if boxed else None, "form_version": form.VERSION if boxed else None,
               "primitives_version": primitives.VERSION if boxed else None,
               "page_reader": "rendered" if boxed else None,
               "rate_plan": "bound" if boxed else None,
               "provider_routing": {"agent": ROUTING.get(model), "parser": ROUTING.get(model) if model_parser else None},
               "parser": ("model" if model_parser else "rules") if boxed else None,
               "parser_model": model if model_parser else None,
               "parser_temperature": suite.PARSER_TEMPERATURE if model_parser else None,
               "prompt_version": form.PROMPT_VERSION if model_parser else None,
               "normalise_version": normalise.VERSION if model_parser else None,
               "reading": arm.reading, "browser_tool": suite.BROWSER_TOOL, "browser_origins": suite.ALLOWED_ORIGINS,
               "browser_flags": suite.BROWSER_FLAGS, "scorer_version": score.VERSION,
               "rules_version": None, "model": model, "scaffold": "openjiuwen",
               **AGENT_CODE, "max_steps": 300, "clock_s": 1800,
               "tasks_file": TASKS_FILE, "draw": suite.draw_id(spec), "instance": spec["_instance"],
               "summary": {}, "rows": rows}
    (folder / "suite.json").write_text(json.dumps(payload))
    return folder


def build_run2(root: pathlib.Path, models=(DEEPSEEK,), plant=None, asks=None, again=(),
               protocol: pathlib.Path = FULL) -> pathlib.Path:
    """The task files and the synthetic fixture under root/tasks, the batch of every arm each
    model's design runs under `protocol`, the full design by default (v6), and the claim
    command's manifest naming them, whose path is returned. For a fault, `plant(model, arm,
    folder)` alters a batch once it is written, and `asks(model, design)` the questions and
    rounds each arm of a model is given. `again` names (model, arm) pairs whose batch is run a
    second time, after every other, as a void batch is re-run, with nothing planted in it. A
    model the protocol does not name runs the primary's design (`claim.whose_design`)."""
    tasks_dir = root / "tasks"
    tasks_dir.mkdir()
    build_task_files(tasks_dir)
    spec = json.loads((tasks_dir / TASKS_FILE).read_text())
    fixture = fixture_of(tasks_dir)
    config = json.loads(protocol.read_text())
    with pointed_at(tasks_dir):
        keys = score.keys_for(tasks_dir / TASKS_FILE)
        resolved = claim.resolve_protocol(protocol, config, spec)
    designs = {}
    for model in models:
        designs[model] = resolved.of(model).design
        if asks is not None:
            designs[model] = asks(model, designs[model])
    page = market_page(spec, fixture)
    lines, n = [], 0
    for model in models:
        for arm in ARMS:
            if arm.name not in designs[model]:
                continue
            n += 1
            folder = write_batch(root, f"202611{n:02d}T100000", arm, model, spec, keys, page, designs[model], fixture)
            if plant is not None:
                plant(model, arm, folder)
            lines.append(f"batch|{folder}|{config['arms'][arm.name]['flags']}")
    for model, name in again:
        n += 1
        arm = next(plan for plan in ARMS if plan.name == name)
        folder = write_batch(root, f"202611{n:02d}T100000", arm, model, spec, keys, page, designs[model], fixture)
        lines.append(f"batch|{folder}|{config['arms'][arm.name]['flags']}")
    manifest = root / "claim2-test.manifest"
    manifest.write_text("start 2026-11-01T10:00:00 usage 20.0 cap 60\n" + "\n".join(lines)
                        + "\nend 2026-11-01T16:00:00 usage 41.0\n")
    return manifest


def analyse(manifest: pathlib.Path, protocol: pathlib.Path = FULL, extra: tuple = ()) -> tuple[int, dict, str]:
    """claim.py --protocol on the manifest, as the command line runs it: its exit code, the
    analysis it writes beside the manifest, and what it prints."""
    with pointed_at(manifest.parent / "tasks"), contextlib.redirect_stdout(io.StringIO()) as out:
        code = claim.main(["--protocol", str(protocol), str(manifest), *extra])
    return code, json.loads(manifest.with_suffix(".analysis.json").read_text()), out.getvalue()


class SyntheticRun2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owner = tempfile.TemporaryDirectory()
        root = pathlib.Path(cls.owner.name)
        manifest = build_run2(root, models=(DEEPSEEK, HAIKU))
        cls.spec = json.loads((root / "tasks" / TASKS_FILE).read_text())
        cls.config = json.loads(FULL.read_text())
        cls.code, cls.result, cls.out = analyse(manifest)
        with pointed_at(root / "tasks"):
            cls.protocol = claim.resolve_protocol(FULL, cls.config, cls.spec)

    @classmethod
    def tearDownClass(cls):
        cls.owner.cleanup()

    def test_it_reads_the_protocol_and_every_arm(self):
        self.assertEqual(self.code, 0)
        self.assertEqual(self.result["problems"], [])
        # DeepSeek is the one model named; Haiku's runs are analysed apart, under the same design.
        self.assertEqual(sorted(self.result["models"]), sorted([DEEPSEEK, HAIKU]))
        self.assertEqual((self.result["models"][DEEPSEEK]["named"], self.result["models"][HAIKU]["named"]), (True, False))
        for model, m in self.result["models"].items():
            with self.subTest(model=model):
                self.assertEqual(list(m["arms"]), list(self.config["arms"]))
                # Shipped asks the 13 templates, open everything the 8 gated, each block the 13
                # and the 43 rewordings (18 of v2, 25 shaped as v3), three rounds each: 39, 24,
                # 168 and 168 runs, 399 slots.
                self.assertEqual({arm: a["runs"] for arm, a in m["arms"].items()},
                                 {"shipped": 39, "open everything (product)": 24,
                                  "the block (rules)": 168, "the block (model)": 168})
                self.assertEqual((m["exclusions"]["design"]["slots"], m["exclusions"]["design"]["filled"]),
                                 (399, 399))
                self.assertEqual((m["conditions"]["held"]["max_steps"], m["conditions"]["held"]["clock_s"]),
                                 (300, 1800))
                # What each arm was held to, every arm's and its own (protocol version 3), all met.
                self.assertEqual(m["conditions"]["required"],
                                 {name: {**self.config["require"], **(arm.get("require") or {})}
                                  for name, arm in self.config["arms"].items()})
                self.assertEqual(m["conditions"]["required"]["the block (model)"]["rate_plan"], "bound")

    def test_the_held_out_set_is_v2s_tee_entries_and_a_v3_shaped_set(self):
        # v2's meaning-kept entries whose template is a tee template or decline-delivery: 16
        # keyed and 2 declines (read by id and template only); the v3-shaped set: two a keyed
        # template, two each of decline-fit and decline-scarcity, one of decline-delivery, 25.
        held = [t for t in self.spec["tasks"] if t.get("template")]
        v2 = [t for t in held if t["source"] == V2_SOURCE]
        v3 = [t for t in held if t["source"] == V3_SOURCE]
        self.assertEqual((len(held), len(v2), len(v3)), (43, 18, 25))
        self.assertEqual(sum(t["expect"]["kind"] != "none" for t in v2), 16)
        self.assertEqual(sum(t["expect"]["kind"] != "none" for t in v3), 20)
        self.assertEqual(sorted(self.protocol.sets["held_out_v2"]), sorted(t["id"] for t in v2))
        self.assertEqual(sorted(self.protocol.sets["held_out_v3"]), sorted(t["id"] for t in v3))
        self.assertEqual(self.protocol.templates, TEMPLATES)
        # tee-promo-check is reading-independent and outside the gated set, which the protocol
        # loader allows (the first claim's `apply_sets` refused it); it is the lookup set.
        self.assertIn("tee-promo-check", self.protocol.sets["reading_independent"])
        self.assertNotIn("tee-promo-check", self.protocol.sets["gated"])
        self.assertEqual(self.protocol.sets["lookup"], ("tee-promo-check",))

    def test_h1_correct_on_the_reading_independent_questions(self):
        # The block under the model is right on all seven, 21 of 21; shipped right on none of
        # them, 0 of 21. Every stratum is 3 of 3 against 0 of 3, hypergeometric 1/20 each,
        # and the block's 21 is the only total as extreme: p = 2 x (1/20)^7.
        for model, m in self.result["models"].items():
            h1 = m["primary"]["H1"]
            with self.subTest(model=model):
                self.assertEqual((h1["a"], h1["b"], len(h1["per_question"])), ("the block (model)", "shipped", 7))
                self.assertIn("tee-promo-check", [row["task"] for row in h1["per_question"]])
                self.assertEqual((h1["pooled"]["a"], h1["pooled"]["b"]), ([21, 21], [0, 21]))
                self.assertAlmostEqual(h1["p"], 2 * (1 / 20) ** 7, places=16)

    def test_h2_and_h3_by_hand(self):
        # Opened: the block opens 8, open everything 21, in each of the eight gated questions;
        # the block's three take ranks 1 to 3, a sum of 6 against a null mean of 10.5 each, so
        # 48 against 84, and only the two most extreme of 20^8 joint splits are as far:
        # p = 2 x (1/20)^8. Cost and tokens the same, the block cheaper in each.
        for model, m in self.result["models"].items():
            h2, h3 = m["primary"]["H2"], m["primary"]["H3"]
            with self.subTest(model=model):
                self.assertEqual(len(h2["per_question"]), 8)
                self.assertEqual((h2["observed"], h2["expected"]), (48.0, 84.0))
                self.assertAlmostEqual(h2["p"], 2 * (1 / 20) ** 8, places=18)
                self.assertEqual((h3["observed"], h3["also"]["observed"], h3["also"]["measure"]),
                                 (48.0, 48.0, "tokens_total"))
                self.assertEqual(h3["also"]["pooled"]["a"][:3], [380_000] * 3)

    def test_h4_on_the_held_out_rewordings_by_template(self):
        # Ten keyed templates, 36 keyed rewordings, three rounds: three runs a rewording and
        # arm, 108 an arm. The model is right on all; the rules on the odd-numbered rewordings.
        # The templates differ in how many odd numbers they hold, so the counts are read from
        # the task file, by id only.
        held = {task["id"]: task for task in self.spec["tasks"] if task.get("template")}
        for model, m in self.result["models"].items():
            h4 = m["primary"]["H4"]
            with self.subTest(model=model):
                self.assertEqual((h4["a"], h4["b"], h4["strata"]), ("the block (model)", "the block (rules)", "template"))
                self.assertEqual(sorted(h4["questions"]), sorted(KEYED_TEMPLATES))
                for row in h4["per_question"]:
                    ids = [t for t in held.values() if t["template"] == row["task"]]
                    self.assertEqual(row["a"], [3 * len(ids), 3 * len(ids)])
                    self.assertEqual(row["b"], [3 * sum(t["rewording"] % 2 for t in ids), 3 * len(ids)])
                self.assertEqual(h4["pooled"]["a"], [108, 108])

    def test_the_audits_rules_stay_quiet_on_a_plain_run(self):
        # Protocol analysis v2: no closed slot on a gated question, nothing sorted or resized,
        # so the three sensitivities give the primary's p. No row or log names a provider, so
        # every run's is unknown, the two arms of H3 have one mix and H3 is not split (v3, v5).
        # And v8's measures: no clash, no leak, no label figure, no run that fell for the trap
        # on tee-xs-price, where every answer gives the key's price or $1.00.
        for model, m in self.result["models"].items():
            with self.subTest(model=model):
                self.assertEqual((m["primary"]["H2"]["closed"], m["primary"]["H3"]["closed"]), ([], []))
                self.assertEqual({arm: (row["sorted"], row["resized"]) for arm, row in m["secondary"]["toolbar"].items()},
                                 {arm: (0, 0) for arm in self.config["arms"]})
                for name in ("with the closed slots in H2 and H3", "without the runs that sorted or changed the page size",
                             "with the closed slots in H2 and H3 at open everything's median"):
                    self.assertEqual({t: v["p"] for t, v in m["sensitivity"][name].items()},
                                     {t: v["p"] for t, v in m["primary"].items()})
                providers = m["secondary"]["providers"]
                self.assertEqual({arm: list(row["by_provider"]) for arm, row in providers["by_arm"].items()},
                                 {arm: ["unknown"] for arm in self.config["arms"]})
                self.assertEqual((providers["h3"]["differs"], providers["h3"]["tests"]), (False, {}))
                self.assertEqual({arm: row["clash"] for arm, row in m["secondary"]["clash_asks"].items()},
                                 {arm: 0 for arm in self.config["arms"]})
                self.assertEqual({arm: row["leaked"] for arm, row in m["secondary"]["leaks"].items()},
                                 {arm: 0 for arm in self.config["arms"]})
                self.assertEqual(m["secondary"]["failure_breakdown"]["pooled"]["a label's figure taken"], 0)
                self.assertEqual({arm: (rows["tee-xs-price"]["template"]["fell_for"], rows["tee-xs-price"]["held_out"]["fell_for"])
                                  for arm, rows in m["secondary"]["promo_traps"].items()},
                                 {arm: (0, 0) for arm in self.config["arms"]})

    def test_the_shipped_failures_on_the_h1_questions_by_where_the_key_renders(self):
        # The breakdown is on H1's seven reading-independent questions (v3, R5): shipped is wrong
        # on all, 21 runs, and no log reaches a second results page. On the synthetic market's
        # results order (Larchmere's accepted live search, the tees where it put them), the keys
        # of tee-count-buyable (one of its listings 39th) and tee-top-3 (Bexhill 39th) need a
        # listing past the 36th; those of tee-target-price, tee-cheapest-target and
        # tee-exists-under (Elmsworth 8th) do not, nor tee-xs-price's, and tee-promo-check's key
        # names no listing to render (every tee lists XS), so those are coded by the rules after,
        # and their wrong answers give no card, sold-out or label figure: "other".
        later = {"tee-count-buyable", "tee-top-3"}
        for model, m in self.result["models"].items():
            fb = m["secondary"]["failure_breakdown"]
            with self.subTest(model=model):
                self.assertEqual((fb["on"], fb["failures"], fb["of"]), ("reading_independent", 21, 21))
                self.assertEqual(fb["pooled"], {"page 2 never reached": 6, "sorted or resized, its first page alone": 0,
                                                "a card or sold-out price taken": 0, "a label's figure taken": 0,
                                                "other": 15})
                self.assertEqual({q: next(code for code, n in row.items() if n) for q, row in fb["by_question"].items()},
                                 {q: "page 2 never reached" if q in later else "other"
                                  for q in self.config["sets"]["reading_independent"]})
                where = {run["run"].split("/")[1]: run["evidence"] for run in fb["runs"]}
                top3 = next(run for run in m["runs"] if (run["arm"], run["task"], run["repeat"]) == ("shipped", "tee-top-3", 1))
                self.assertTrue(any(position > 36 for position in top3["key_where"]["positions"]))
                self.assertEqual(where["tee-top-3-1"], f"the key's listings at {top3['key_where']['positions']} (any); "
                                                       f"no results page numbered")

    def test_the_asks_by_the_sidecars_label(self):
        # The box asks on the two two-reading templates, three rounds, 6 of the 30 runs on the
        # two-reading questions (the templates and their 8 rewordings, three rounds); the
        # rewordings have no box record. Wilson's interval for 6 of 30, by hand: centre
        # (1/5 + z^2/60) / (1 + z^2/30) and half-width z sqrt(4/750 + z^2/3600) / (1 + z^2/30),
        # z = 1.95996, so 0.0951 to 0.3731. Shipped and open everything ask nothing.
        for model, m in self.result["models"].items():
            labelled = m["secondary"]["asks_by_label"]
            with self.subTest(model=model):
                row = labelled["the block (model)"]["ambiguous"]
                self.assertEqual((row["runs"], row["asked"], row["box"], row["agent"]), (30, 6, 6, 0))
                self.assertAlmostEqual(row["interval"][0], 0.0951, places=4)
                self.assertAlmostEqual(row["interval"][1], 0.3731, places=4)
                self.assertEqual({label: r["asked"] for label, r in labelled["shipped"].items()},
                                 {"clear": 0, "ambiguous": 0})
                self.assertEqual(labelled["shipped"]["clear"]["runs"] + labelled["shipped"]["ambiguous"]["runs"], 39)
        self.assertIn("g. Asks on the questions the sidecar labels clear and ambiguous", self.out)

    def test_h4_on_each_part_of_each_split(self):
        # Two splits, each within a set (v8). "v2 against v3, within the kept eight templates":
        # parts of rewordings, the model right on all, the rules on the odd-numbered: v2's 16
        # keyed rewordings, 48 runs, and v3's 16 of the kept templates, 48 runs, each part's
        # strata the eight kept templates. "the two new templates against the kept eight, within
        # v3": parts of templates, v3's 4 rewordings of the new templates, 12 runs, against its
        # 16 of the kept, 48 runs.
        held = [t for t in self.spec["tasks"] if t.get("template") and t["expect"]["kind"] != "none"]

        def expected(tasks):
            return [3 * len(tasks)] * 2, [3 * sum(t["rewording"] % 2 for t in tasks), 3 * len(tasks)]
        kept = set(self.config["sets"]["kept_templates"])
        for model, m in self.result["models"].items():
            splits = {s["split"]: s for s in m["splits"]["H4"]}
            with self.subTest(model=model):
                self.assertEqual(list(splits), list(self.config["splits"]["H4"]))
                by_source = splits["v2 against v3, within the kept eight templates"]
                self.assertEqual((by_source["within"], by_source["kind"]), ("kept_templates", "rewordings"))
                for part in by_source["parts"]:
                    mine = [t for t in held if t["source"] == {"held_out_v2": V2_SOURCE, "held_out_v3": V3_SOURCE}[part["set"]]
                            and t["template"] in kept]
                    self.assertEqual(sorted(part["questions"]), sorted(kept))
                    self.assertEqual((part["pooled"]["a"], part["pooled"]["b"]), expected(mine))
                by_kind = splits["the two new templates against the kept eight, within v3"]
                self.assertEqual((by_kind["within"], by_kind["kind"]), ("held_out_v3", "templates"))
                for part in by_kind["parts"]:
                    templates = set(self.config["sets"][part["set"]])
                    mine = [t for t in held if t["source"] == V3_SOURCE and t["template"] in templates]
                    self.assertEqual(sorted(part["questions"]), sorted(templates))
                    self.assertEqual((part["pooled"]["a"], part["pooled"]["b"]), expected(mine))
                self.assertEqual(by_kind["parts"][0]["pooled"]["a"], [12, 12])
        self.assertIn("H4 on the pre-specified splits, secondary and unadjusted", self.out)
        self.assertIn("(within held_out_v3, parts of templates)", self.out)

    def test_h4_by_rewording(self):
        # One unit a rewording: the model's share is 1 on every one, the rules' 1 on the odd
        # ones and 0 on the even, 36 units an arm; H1 to H3 are the primary's.
        held = [task for task in self.spec["tasks"] if task.get("template") and task["expect"]["kind"] != "none"]
        for model, m in self.result["models"].items():
            tests = m["sensitivity"]["H4 by rewording, not by run"]
            h4 = tests["H4"]
            with self.subTest(model=model):
                self.assertEqual((h4.get("unit"), len(h4["pooled"]["a"]), len(h4["pooled"]["b"])), ("rewording", 36, 36))
                for row in h4["per_question"]:
                    ids = [t for t in held if t["template"] == row["task"]]
                    self.assertEqual(row["a"], [1.0] * len(ids))
                    self.assertEqual(sorted(row["b"]), sorted(float(t["rewording"] % 2) for t in ids))
                self.assertEqual({t: tests[t]["p"] for t in ("H1", "H2", "H3")},
                                 {t: m["primary"][t]["p"] for t in ("H1", "H2", "H3")})

    def test_a_split_that_does_not_divide_its_questions_is_refused(self):
        with pointed_at(pathlib.Path(self.owner.name) / "tasks"):
            for label, change, words in (
                    ("a template in neither part", lambda c: c["sets"]["kept_templates"].pop(), "in neither part"),
                    ("a template in both", lambda c: c["sets"]["new_templates"].append("tee-headline"), "overlap"),
                    ("parts of two kinds", lambda c: c["splits"]["H4"].update(
                        {"mixed": {"within": None, "parts": ["held_out_v2", "new_templates"]}}),
                     "not both templates or both held-out rewordings"),
                    ("a within set of a mixed kind", lambda c: (c["sets"].update(odd=["tee-headline", "rw-01"]),
                                                               c["splits"]["H4"].update(
                        {"odd": {"within": "odd", "parts": ["held_out_v2", "held_out_v3"]}})),
                     "neither templates nor held-out rewordings"),
                    # A rewording with no source is in no selection: it is in neither part.
                    ("a rewording without its source", lambda c: c["sets"].update(
                        held_out_v3={"rewordings": {"source": V3_SOURCE, "rewording": 1}}), "in neither part"),
                    ("a selection no task matches", lambda c: c["sets"].update(
                        held_out_v3={"rewordings": {"source": "paraphrases_v9.json"}}), "holds none")):
                with self.subTest(fault=label):
                    broken = json.loads(json.dumps(self.config))
                    change(broken)
                    with self.assertRaises(SystemExit) as raised:
                        claim.resolve_protocol(FULL, broken, self.spec)
                    self.assertIn(words, str(raised.exception))

    def test_holm_over_the_four(self):
        for model, m in self.result["models"].items():
            tests = m["primary"]
            with self.subTest(model=model):
                self.assertEqual(list(tests), ["H1", "H2", "H3", "H4"])
                ps = {name: t["p"] for name, t in tests.items()}
                self.assertEqual({name: t["p_holm"] for name, t in tests.items()}, claim.holm(ps))
                # Four tests, so the smallest p is multiplied by four.
                self.assertAlmostEqual(min(t["p_holm"] for t in tests.values()), 4 * min(ps.values()), places=30)
                self.assertEqual([name for name, t in tests.items() if t["rejected"]], ["H1", "H2", "H3", "H4"])

    def test_each_model_is_its_own_result(self):
        # The two models' runs are the same here, so their figures are, and neither pools the
        # other: each counts its own 399 runs.
        a, b = (self.result["models"][m] for m in (DEEPSEEK, HAIKU))
        self.assertEqual(len(a["runs"]), 399)
        self.assertEqual(len(b["runs"]), 399)
        self.assertEqual(a["primary"]["H1"]["p"], b["primary"]["H1"]["p"])
        self.assertIn(f"Model {HAIKU}, which the protocol does not name", self.out)

    def test_the_tables_and_the_secondary_figures(self):
        m = self.result["models"][DEEPSEEK]
        model, shipped = m["tables"]["the block (model)"], m["tables"]["shipped"]
        # Every template question is a row, the lookup tee-promo-check included (v8), then the pool.
        self.assertEqual(list(shipped), list(TEMPLATES) + ["pooled, gated"])
        self.assertEqual((model["tee-target-price"]["correct"], model["tee-target-price"]["opened"]), (3, [8, 8, 8]))
        self.assertEqual((model["tee-promo-check"]["correct"], model["tee-promo-check"]["scored"]), (3, 3))
        self.assertEqual((shipped["tee-headline"]["correct"], shipped["pooled, gated"]["correct"]), (3, 0))
        # The declines: the box refuses the three templates and their seven rewordings, three
        # rounds, 30; shipped answers the three templates without a plan, 9.
        self.assertEqual(m["secondary"]["declines"]["the block (model)"]["refused"], 30)
        self.assertEqual(m["secondary"]["declines"]["shipped"]["answered without a plan"], 9)
        # Two readings are the sidecar's `two_readings`: the two templates and their eight
        # rewordings, three rounds, 30 of the block's 168 runs.
        row = m["secondary"]["asks"]["the block (model)"]
        self.assertEqual((row["clear"]["runs"], row["ambiguous"]["runs"], row["ambiguous"]["asks"]), (138, 30, 6))
        table = m["secondary"]["count_two_readings"]["table"]
        self.assertEqual(table["the block (model)"]["menu_key"], 3)
        # The answer check replayed the block's template plans: ten planned questions, three
        # rounds, every stored text reproduced, tee-xs-price's bound and tee-promo-check's lookup
        # among them. The synthetic logs hold no tool reply, so the check sees no observation and
        # refuses every answer, which shows it ran.
        check = m["secondary"]["answer_check"]["the block (model)"]
        self.assertEqual((check["runs"], check["planned"], check["not_reproduced"]), (30, 30, []))
        self.assertEqual(len(check["correct_refused"]), 30)
        self.assertEqual(model["tee-target-price"]["tokens_mean"], 380_000)
        # A slot the box closed costs its parse under the model parser, nothing under the rules.
        rules = m["tables"]["the block (rules)"]
        self.assertEqual((model["decline-fit"]["cost_mean"], rules["decline-fit"]["cost_mean"]), (0.002, 0.0))
        # A question with no key has no count of correct answers to show: "-", never 0.
        self.assertEqual((model["decline-scarcity"]["keyed"], model["tee-xs-price"]["keyed"]), (False, True))
        self.assertRegex(self.out, r"\n    decline-scarcity +3 +-  ")
        self.assertRegex(self.out, r"\n    tee-xs-price +3 +3/3  ")
        self.assertEqual(list(m["sensitivity"]), self.config["sensitivity"])

    def test_tee_promo_check_against_open_everything_is_not_run_by_design(self):
        # Open everything asks the gated set alone, so on the reading-independent set the lookup
        # is reported as not run by design, by question, and the six others are compared (v8).
        for model, m in self.result["models"].items():
            o = m["against_open_everything"]
            with self.subTest(model=model):
                self.assertEqual(o["not_run_by_design"], ["tee-promo-check"])
                self.assertEqual([row["task"] for row in o["per_question"]],
                                 [q for q in self.config["sets"]["reading_independent"] if q != "tee-promo-check"])
                self.assertEqual(o["pooled"]["a"], [18, 18])
        self.assertIn("tee-promo-check        not run by design: an arm's design does not ask it", self.out)

    def test_the_report_prints_every_section(self):
        for words in ("The claim analysis under", "Problems found: 0", "Model deepseek/deepseek-v4-flash",
                      "Held constant across the arms:", "max_steps 300",
                      "clock_s 1800", "1. Each arm by question", "2. Primary tests, two-sided, with Holm's "
                      "correction over the 4", "H1 correct, the block (model) against shipped",
                      "H4 correct, the block (model) against the block (rules), on held_out, by template",
                      "stratified exact test by template", "380k",
                      "and on the run's tokens, the model parser's included, outside Holm",
                      "3. Correct, the block (model) against open everything",
                      "4. The held-out rewordings, by template", "5. Secondary and exploratory",
                      "c. The questions the block should not plan", "6. Sensitivity",
                      f"every log's results pages read by toolbar.py v{toolbar.VERSION}", "i. The parse's fallbacks",
                      # v8: the three new measures.
                      "j. Asks caused by the word-list clash", "k. Promo traps fallen for, by arm and question",
                      "l. Hidden-price leaks by arm"):
            with self.subTest(words=words):
                self.assertIn(words, self.out)
        self.assertEqual(self.result["toolbar_version"], toolbar.VERSION)
        self.assertEqual(self.result["protocol_analysis_version"], 9)

    def test_no_fallback_in_a_plain_run(self):
        # Every template decision of the block's arms has its record, the rewordings' a record
        # with no plan: 168 runs an arm, none by the survey fallback, and the model's form used
        # wherever the model read the question. The arms without the box have no record.
        for model, m in self.result["models"].items():
            with self.subTest(model=model):
                self.assertEqual({arm: (row["runs"], row["survey_fallback"], row["parse_fallback"])
                                  for arm, row in m["secondary"]["fallbacks"].items()},
                                 {"shipped": (0, 0, 0), "open everything (product)": (0, 0, 0),
                                  "the block (rules)": (168, 0, 0), "the block (model)": (168, 0, 0)})

    def test_no_rewording_text_is_printed_or_stored(self):
        # Checked without showing any: only whether one appears.
        held = json.loads(HELD_OUT.read_text())["paraphrases"]
        limit = self.spec["_instance"]["exists_limit"]
        texts = [entry["text"].format(brand=self.spec["brand"], limit=limit) for entry in held]
        report = self.out + json.dumps(self.result)
        self.assertFalse(any(text in report for text in texts))


def set_conditions(folder: pathlib.Path, **values) -> None:
    """A written batch's conditions changed: in its payload, and in each run record that
    holds them."""
    for path in folder.glob("*.json"):
        data = json.loads(path.read_text())
        data.update({key: value for key, value in values.items() if path.name == "suite.json" or key in data})
        path.write_text(json.dumps(data))


def set_routing(folder: pathlib.Path, batch, records) -> None:
    """A written batch's provider routing: its payload's {agent, parser} and every run record's,
    each left out where "absent", as a batch from before 23 October 2026 has none."""
    for path in folder.glob("*.json"):
        data = json.loads(path.read_text())
        value = batch if path.name == "suite.json" else records
        if value == "absent":
            data.pop("provider_routing", None)
        else:
            data["provider_routing"] = value
        path.write_text(json.dumps(data))


def drop_run(folder: pathlib.Path, task: str, repeat: int) -> None:
    """A run taken out of a written batch, row, record and log, as if never run."""
    payload = json.loads((folder / "suite.json").read_text())
    payload["rows"] = [row for row in payload["rows"] if (row["task"], row["repeat"]) != (task, repeat)]
    (folder / "suite.json").write_text(json.dumps(payload))
    for suffix in (".json", ".log"):
        (folder / f"{task}-{repeat}{suffix}").unlink()


def void_run(folder: pathlib.Path, task: str, repeat: int) -> None:
    """A run of a written batch made void: the provider failed and no answer came back."""
    path = folder / f"{task}-{repeat}.json"
    record = json.loads(path.read_text())
    record.update(result={"ok": False, "final": ""}, error="Error code: 429, rate limited")
    path.write_text(json.dumps(record))
    payload = json.loads((folder / "suite.json").read_text())
    for row in payload["rows"]:
        if (row["task"], row["repeat"]) == (task, repeat):
            row.update(answer="", verdict="failed", error=record["error"])
    (folder / "suite.json").write_text(json.dumps(payload))


def task_of(folder: pathlib.Path, task_id: str) -> dict:
    return next(t for t in json.loads((folder.parent / "tasks" / TASKS_FILE).read_text())["tasks"]
                if t["id"] == task_id)


def task_keys(folder: pathlib.Path) -> score.Keys:
    """The written task file's `Keys`, its fixture the synthetic one."""
    with pointed_at(folder.parent / "tasks"):
        return score.keys_for(folder.parent / "tasks" / TASKS_FILE)


def answer_under(folder: pathlib.Path, task_id: str, repeat: int, reading: str, answer: str) -> None:
    """A run of a written batch answered under `reading`, as its box record now says, with
    `answer`, and the verdict the batch would have stored for it."""
    task, keys = task_of(folder, task_id), task_keys(folder)
    path = folder / f"{task_id}-{repeat}.json"
    record = json.loads(path.read_text())
    record["result"]["final"] = answer
    path.write_text(json.dumps(record))
    payload = json.loads((folder / "suite.json").read_text())
    for row in payload["rows"]:
        if (row["task"], row["repeat"]) == (task_id, repeat):
            row["box"]["reading"] = row["reading"] = reading
            row.update(answer=answer[:300], verdict=score.score_run(task, reading, keys, answer, True)["verdict"])
    (folder / "suite.json").write_text(json.dumps(payload))


def close_slot(folder: pathlib.Path, task_id: str, repeat: int, cost: float = 0.002, reason: str | None = None) -> None:
    """A run of a written batch turned into a slot the box closed: it asked, no reply came, no
    agent ran, and the model parser's parse was paid for, as suite.py writes such a slot. With
    `reason`, the box record says why it asked (box v19, `ask_reason`)."""
    for suffix in (".json", ".log"):
        (folder / f"{task_id}-{repeat}{suffix}").unlink()
    record = {"asked": True, "ask": "Do you mean listed, or in stock now?", "refuse": None, "query": None,
              "page": None, "reading": None, "bypassed": False, "fallback": False}
    if reason is not None:
        record["ask_reason"] = reason
    payload = json.loads((folder / "suite.json").read_text())
    payload["rows"] = [suite.asked_row(task_of(folder, task_id), repeat, record, cost=cost) | {"parse_cost_usd": cost}
                       if (row["task"], row["repeat"]) == (task_id, repeat) else row for row in payload["rows"]]
    (folder / "suite.json").write_text(json.dumps(payload))


def set_ask_reason(folder: pathlib.Path, task_id: str, repeat: int, reason: str) -> None:
    """A run's box record given the reason the box asked (box v19, `ask_reason`), on a run the
    box asked and the scripted shopper answered."""
    payload = json.loads((folder / "suite.json").read_text())
    for row in payload["rows"]:
        if (row["task"], row["repeat"]) == (task_id, repeat):
            assert row["box"]["asked"], f"{task_id}-{repeat} was not asked"
            row["box"]["ask_reason"] = reason
    (folder / "suite.json").write_text(json.dumps(payload))


def set_clash_settled(folder: pathlib.Path, task_id: str, repeat: int) -> None:
    """A run's box record saying the box settled a clash of the word list and the model itself,
    taking the one reading the shop can answer, with no ask put (box v20, `clash_settled`)."""
    payload = json.loads((folder / "suite.json").read_text())
    for row in payload["rows"]:
        if (row["task"], row["repeat"]) == (task_id, repeat):
            assert not row["box"]["asked"], f"{task_id}-{repeat} was asked"
            row["box"].update(clash_settled=True, clash={"word": "listed"})
    (folder / "suite.json").write_text(json.dumps(payload))


def add_pages(folder: pathlib.Path, task_id: str, repeat: int, *urls: str) -> None:
    """Pages a run of a written batch was on, as its log reports them, before its last line."""
    path = folder / f"{task_id}-{repeat}.log"
    lines = path.read_text().splitlines()
    path.write_text("\n".join(lines[:-1] + [f"Page URL: {url}" for url in urls] + lines[-1:]) + "\n")


def add_leak(folder: pathlib.Path, task_id: str, repeat: int) -> None:
    """A sign in a run's log that it read the prices the gated theme hides: the variant store's
    own marker (leaks.py, "the store")."""
    path = folder / f"{task_id}-{repeat}.log"
    lines = path.read_text().splitlines()
    path.write_text("\n".join(lines[:-1] + ['<div id="igr-variant-store" data-igr="eyJ...">'] + lines[-1:]) + "\n")


def answer_with(folder: pathlib.Path, task_id: str, repeat: int, answer: str, stored: str | None = None) -> None:
    """A run of a written batch given another answer, and the verdict the batch would have
    stored for it, as suite.py stores it today, or `stored`, as an older scorer stored it."""
    path = folder / f"{task_id}-{repeat}.json"
    record = json.loads(path.read_text())
    record["result"]["final"] = answer
    path.write_text(json.dumps(record))
    keys = task_keys(folder)
    payload = json.loads((folder / "suite.json").read_text())
    for row in payload["rows"]:
        if (row["task"], row["repeat"]) == (task_id, repeat):
            reading = (row.get("box") or {}).get("reading")
            row.update(answer=answer[:300], verdict=stored or score.score_run(
                task_of(folder, task_id), reading, keys, answer, True)["verdict"])
    (folder / "suite.json").write_text(json.dumps(payload))


def fixture_prices(folder: pathlib.Path) -> tuple[float, float]:
    """The synthetic market's cheapest tee card and its cheapest size M that is sold out, from
    its fixture: a price a card shows and one a sold-out size shows."""
    tees = fixture_of(folder.parent / "tasks")["families"]
    card = min(min(v["price"] for v in f["variants"] if v["qty"] > 0) for f in tees)
    sold_out = min(v["price"] for f in tees for v in f["variants"] if v["option"] == "M" and v["qty"] == 0)
    return card, sold_out


def promo_figures(folder: pathlib.Path) -> list[float]:
    """The synthetic market's promo label figures, lowest first."""
    return sorted(xs_of(f)["label_price"] for f in fixture_of(folder.parent / "tasks")["families"]
                  if xs_of(f).get("label_kind") == "promo")


SEARCH = "http://localhost:7770/catalogsearch/result/index/?q=Larchmere"


def another_seller(folder: pathlib.Path, expect: dict) -> str:
    """A tee seller of the synthetic market that a contains key neither wants nor excludes."""
    named = {token.lower() for token in expect["any"] + expect.get("not_any", [])}
    return next(f["seller"] for f in fixture_of(folder.parent / "tasks")["families"]
                if f["seller"].split()[0].lower() not in named)


def serve(folder: pathlib.Path, task_id: str, repeat: int, *providers: str) -> None:
    """Model calls in a run's log, one a provider named, as openJiuwen logs each response: its
    repr with its usage and ending with the provider that served it, before the log's last line,
    as a batch from before suite.py recorded the count in its row has them (v5)."""
    path = folder / f"{task_id}-{repeat}.log"
    lines = path.read_text().splitlines()
    calls = [f"ChatCompletion(id='gen-{n}', object='chat.completion', usage=CompletionUsage(completion_tokens=10, "
             f"prompt_tokens=100, total_tokens=110), provider='{name}')" for n, name in enumerate(providers)]
    path.write_text("\n".join(lines[:-1] + calls + lines[-1:]) + "\n")


def served_rows(folder: pathlib.Path, providers, parse_provider=None) -> None:
    """Every row of a written batch given the count suite.py records of who served the agent's
    calls, `providers(row)`, where the agent ran, and the parse call's provider where given,
    as a batch since 23 October 2026 records them (`providers`, `parse_provider`)."""
    payload = json.loads((folder / "suite.json").read_text())
    for row in payload["rows"]:
        if row.get("log"):
            row["providers"] = providers(row)
        if parse_provider is not None:
            row["parse_provider"] = parse_provider(row)
    (folder / "suite.json").write_text(json.dumps(payload))


def rewording_of(folder: pathlib.Path, template: str, source: str = V3_SOURCE) -> str:
    """The id of the first held-out rewording of `template` from `source` in the written task file."""
    return next(t["id"] for t in json.loads((folder.parent / "tasks" / TASKS_FILE).read_text())["tasks"]
                if t.get("template") == template and t.get("source") == source)


class Run2Faults(unittest.TestCase):
    """The run-2 analysis's own checks, each firing on a fault planted in the synthetic
    batches, and quiet without it. One model's batches, DeepSeek's, the one the file names."""

    def run2(self, plant=None, models=(DEEPSEEK,), asks=None, again=(), protocol=None) -> tuple[int, dict, str]:
        """The synthetic run with `plant`, analysed. `protocol`, if given, changes a copy of the
        protocol file first, which the run is then analysed under."""
        with tempfile.TemporaryDirectory() as tmp:
            path = FULL
            if protocol is not None:
                config = json.loads(FULL.read_text())
                protocol(config)
                path = pathlib.Path(tmp) / "claim2_changed.json"
                path.write_text(json.dumps(config))
            return analyse(build_run2(pathlib.Path(tmp), models, plant, asks, again), path)

    def test_quiet_on_the_plain_run_of_the_one_model_named(self):
        code, result, out = self.run2()
        self.assertEqual((code, result["problems"]), (0, []))
        self.assertIn("Problems found: 0", out)
        self.assertEqual(list(result["models"]), [DEEPSEEK])

    def test_a_named_model_with_no_run_is_a_problem(self):
        # Haiku's batches alone: the file names DeepSeek, which has no run, and Haiku is unnamed.
        code, result, out = self.run2(models=(HAIKU,))
        self.assertEqual(result["problems"], [f"the protocol's model {DEEPSEEK} has no run"])
        self.assertIn("Problems found: 1", out)
        self.assertEqual(list(result["models"]), [HAIKU])

    def test_a_batch_outside_require_is_void_and_its_model_refused(self):
        # Until protocol analysis v3 it was listed among the problems and analysed all the same,
        # and in v3 it stopped the whole analysis. Since v4 the batch is void as a whole, and a
        # model it leaves a slot empty for is refused: the exit says so.
        def plant(model, arm, folder):
            if arm.name == "shipped":
                set_conditions(folder, max_steps=150)
        code, result, out = self.run2(plant)
        self.assertEqual(code, 1)
        refused = result["models"][DEEPSEEK]["refused"]
        self.assertEqual(len(refused), 1)
        self.assertIn("20261101T100000 ran outside what the protocol requires (shipped with max_steps 150, where "
                      "the protocol requires 300), so it is void as a whole, and 39 of its slots have no re-run",
                      refused[0])
        self.assertIn(f"{DEEPSEEK}: refused: 20261101T100000 ran outside", " ".join(result["problems"]))
        self.assertEqual([(v["batch"], v["re_run"]) for v in result["void_batches"]], [("20261101T100000", False)])
        self.assertIn("REFUSED: this model's analysis is not made", out)

    def test_a_batch_outside_require_refuses_its_own_model_alone(self):
        def plant(model, arm, folder):
            if model == HAIKU and arm.name == "the block (model)":
                set_conditions(folder, rate_plan="every")
        code, result, out = self.run2(plant, models=(DEEPSEEK, HAIKU))
        self.assertEqual(code, 1)
        self.assertIn("the block (model) with rate_plan every, where the protocol requires bound",
                      result["models"][HAIKU]["refused"][0])
        deepseek = result["models"][DEEPSEEK]
        self.assertNotIn("refused", deepseek)
        self.assertEqual({arm: a["runs"] for arm, a in deepseek["arms"].items()},
                         {"shipped": 39, "open everything (product)": 24, "the block (rules)": 168,
                          "the block (model)": 168})
        self.assertEqual(list(deepseek["primary"]), ["H1", "H2", "H3", "H4"])
        self.assertEqual(deepseek["exclusions"]["void_batches"], [])
        self.assertIn("1. Each arm by question", out)

    def test_two_conditions_in_one_arm_refuse_that_model_alone(self):
        # Haiku's shipped batch run twice, the first on another market draw: one arm under two
        # conditions is two arms (LESSONS 7). Until v4 that stopped every model's analysis.
        def plant(model, arm, folder):
            if model == HAIKU and arm.name == "shipped":
                set_conditions(folder, draw="Larchmere:another")
        code, result, _ = self.run2(plant, models=(DEEPSEEK, HAIKU), again=((HAIKU, "shipped"),))
        self.assertEqual(code, 1)
        self.assertIn("shipped under anthropic/claude-haiku-4.5 has runs under more than one condition",
                      result["models"][HAIKU]["refused"][0])
        self.assertEqual(list(result["models"][DEEPSEEK]["primary"]), ["H1", "H2", "H3", "H4"])

    def test_a_void_batch_run_again_is_listed_and_its_model_analysed(self):
        # The protocol's note: void as a whole, re-run, and listed. The re-run fills every slot.
        def plant(model, arm, folder):
            if arm.name == "shipped":
                set_conditions(folder, max_steps=150)
        code, result, out = self.run2(plant, again=((DEEPSEEK, "shipped"),))
        self.assertEqual(code, 0)
        m = result["models"][DEEPSEEK]
        self.assertEqual((m["arms"]["shipped"]["runs"], m["arms"]["shipped"]["batches"]), (39, ["20261105T100000"]))
        self.assertEqual([(v["batch"], v["re_run"]) for v in m["exclusions"]["void_batches"]], [("20261101T100000", True)])
        self.assertEqual(result["problems"], [])
        self.assertIn("void as a whole, outside what the protocol requires, and run again: 20261101T100000", out)

    def test_each_condition_an_arm_is_required_to_run_under(self):
        # The re-audit's R4: every arm's browser and agent code, and each arm's own conditions.
        # A batch run under another is void, and its model's refusal names the arm and the
        # condition. The model arm's parser is held to the run's own model (v4). Since v8 the
        # rate plan required is the default, "bound", since design B asks no rate question.
        for arm_name, change, words in (
                ("shipped", {"browser_tool": "0.0.84"}, "shipped with browser_tool 0.0.84, where the protocol "
                                                        "requires 0.0.83"),
                ("shipped", {"browser_flags": "--isolated"}, "shipped with browser_flags --isolated"),
                ("shipped", {"browser_origins": "http://localhost:7770 https://example.com"},
                 "shipped with browser_origins http://localhost:7770 https://example.com"),
                ("open everything (product)", {"agent_core_commit": "c" * 40},
                 f"open everything (product) with agent_core_commit {'c' * 40}"),
                ("the block (rules)", {"agent_core_patch": "unknown"}, "the block (rules) with agent_core_patch unknown"),
                ("open everything (product)", {"exhaustive_wording_version": 1},
                 "open everything (product) with exhaustive_wording_version 1"),
                ("the block (rules)", {"rate_plan": "every"}, "the block (rules) with rate_plan every, where the "
                                                              "protocol requires bound"),
                ("the block (rules)", {"page_reader": "fetch"}, "the block (rules) with page_reader fetch"),
                ("the block (rules)", {"box_version": 17}, "the block (rules) with box_version 17"),
                ("the block (rules)", {"form_version": 12}, "the block (rules) with form_version 12"),
                ("the block (model)", {"prompt_version": 2}, "the block (model) with prompt_version 2"),
                ("the block (model)", {"parser_temperature": 0.2}, "the block (model) with parser_temperature 0.2"),
                ("the block (model)", {"rate_plan": "every"}, "the block (model) with rate_plan every"),
                ("the block (model)", {"parser_model": "x-ai/grok-5-mini"},
                 f"the block (model) with parser_model x-ai/grok-5-mini, where the protocol requires its model, {DEEPSEEK}")):
            with self.subTest(arm=arm_name, change=change):
                def plant(model, arm, folder, arm_name=arm_name, change=change):
                    if arm.name == arm_name:
                        set_conditions(folder, **change)
                code, result, _ = self.run2(plant)
                self.assertEqual(code, 1)
                self.assertIn(words, " ".join(result["models"][DEEPSEEK]["refused"]))

    def test_a_batch_routed_otherwise_than_the_protocol_names_for_its_model(self):
        # The pilot coder's point a (v5): DeepSeek's routing, the agent's and in the model arm
        # the parse's, as the batch's payload and its runs' records say. Quiet on the plain run
        # (SyntheticRun2), where DeepSeek's are routed. Haiku is a model the file does not name
        # since version 7, so the file requires null of it.
        proposed = ROUTING[DEEPSEEK]
        for label, model, arm_name, batch, records, words in (
                ("DeepSeek run unrouted", DEEPSEEK, "shipped", {"agent": None, "parser": None}, None,
                 f"shipped with agent provider routing null, where the protocol requires {json.dumps(proposed)}"),
                ("an unnamed model routed", HAIKU, "open everything (product)", {"agent": proposed, "parser": None}, proposed,
                 f"open everything (product) with agent provider routing {json.dumps(proposed)}, where the protocol "
                 f"requires null for {HAIKU}"),
                ("DeepSeek's parse unrouted", DEEPSEEK, "the block (model)", {"agent": proposed, "parser": None}, proposed,
                 "the block (model) with parser provider routing null"),
                # The verifier's point 1: the parse's routing is per arm, null outside the model arm.
                ("a parse routing recorded in the rules arm", DEEPSEEK, "the block (rules)",
                 {"agent": proposed, "parser": proposed}, proposed,
                 f"the block (rules) with parser provider routing {json.dumps(proposed)}, where the protocol "
                 f"requires null"),
                ("a batch from before routing, for DeepSeek", DEEPSEEK, "the block (rules)", "absent", "absent",
                 "the block (rules) with agent provider routing null")):
            with self.subTest(fault=label):
                def plant(planted_model, arm, folder, model=model, arm_name=arm_name, batch=batch, records=records):
                    if planted_model == model and arm.name == arm_name:
                        set_routing(folder, batch, records)
                code, result, _ = self.run2(plant, models=(model,))
                self.assertEqual(code, 1)
                self.assertIn(words, " ".join(result["models"][model]["refused"]))

    def test_a_record_routed_otherwise_than_its_batch(self):
        # The pilot coder's point b (v5): a run's record holds what its runner applied, held to
        # what its batch's payload says the agent ran under.
        def plant(model, arm, folder):
            if arm.name == "shipped":
                record = folder / "tee-top-3-2.json"
                data = json.loads(record.read_text())
                data["provider_routing"] = {"order": ["deepinfra"]}
                record.write_text(json.dumps(data))
        code, result, _ = self.run2(plant)
        self.assertEqual(code, 1)
        self.assertIn(f"provider routing {json.dumps({'order': ['deepinfra']})} in the record of tee-top-3-2, where "
                      f"its batch says the agent ran under {json.dumps(ROUTING[DEEPSEEK])}",
                      " ".join(result["models"][DEEPSEEK]["refused"]))

    def test_a_condition_that_differs_between_the_arms(self):
        # One the protocol requires of no arm, in a copy of the file that does not require the
        # patch's digest: listed among the problems, and the analysis goes on.
        def plant(model, arm, folder):
            if arm.name == "open everything (product)":
                set_conditions(folder, agent_core_patch="c" * 40)
        code, result, out = self.run2(plant, protocol=lambda config: config["require"].pop("agent_core_patch"))
        patch = AGENT_CODE["agent_core_patch"]
        self.assertEqual(code, 0)
        self.assertIn(f"{DEEPSEEK}: agent_core_patch differs between the arms: shipped {patch}; open everything "
                      f"(product) {'c' * 40}; the block (rules) {patch}; the block (model) {patch}",
                      result["problems"])
        self.assertIn("DIFFERS between arms, agent_core_patch", out)

    def test_a_slot_never_run_is_a_problem_and_a_void_is_not(self):
        def plant(model, arm, folder):
            if arm.name == "shipped":
                drop_run(folder, "tee-top-3", 2)
            if arm.name == "the block (rules)":
                void_run(folder, "tee-top-3", 2)
        _, result, _ = self.run2(plant)
        design = result["models"][DEEPSEEK]["exclusions"]["design"]
        self.assertEqual(design["missing"], ["shipped, tee-top-3 repeat 2", "the block (rules), tee-top-3 repeat 2"])
        self.assertEqual(design["never_run"], ["shipped, tee-top-3 repeat 2"])
        self.assertEqual([v["task"] for v in result["models"][DEEPSEEK]["exclusions"]["voids"]], ["tee-top-3"])
        self.assertEqual(result["problems"], [f"{DEEPSEEK}: the design's slot shipped, tee-top-3 repeat 2 has no "
                                              f"run, void or not"])

    def test_a_run_the_design_does_not_ask_for(self):
        _, result, _ = self.run2(asks=lambda model, design: {**design, "shipped": {**design["shipped"], "rw-03": (1, 2, 3)}})
        self.assertEqual([p for p in result["problems"] if "does not ask for" in p],
                         [f"{DEEPSEEK}: a run the design does not ask for, shipped, rw-03 repeat {r}" for r in (1, 2, 3)])

    def test_a_model_the_protocol_does_not_name_is_analysed_apart(self):
        other = "x-ai/grok-5-mini"
        _, result, out = self.run2(models=(DEEPSEEK, other))
        self.assertEqual((result["models"][DEEPSEEK]["named"], result["models"][other]["named"]), (True, False))
        self.assertIn(f"Model {other}, which the protocol does not name", out)
        self.assertEqual(result["problems"], [])
        self.assertEqual(len(result["models"][other]["runs"]), 399)

    def the_run(self, result: dict, arm: str, task: str, repeat: int) -> dict:
        return next(run for run in result["models"][DEEPSEEK]["runs"]
                    if (run["arm"], run["task"], run["repeat"]) == (arm, task, repeat))

    def test_a_run_is_scored_under_the_reading_it_answered(self):
        # The block (model)'s first round of tee-count-stocked answered under the buyable
        # reading, as its box record now says, with the buyable count: correct under that
        # key, wrong under the question's own (score v4), and so correct.
        def plant(model, arm, folder):
            if arm.name == "the block (model)":
                readings = json.loads((folder.parent / "tasks" / READINGS_FILE).read_text())["readings"]
                answer_under(folder, "tee-count-stocked", 1, "buyable", right(readings["buyable"]["tee-count-stocked"]))
        _, result, _ = self.run2(plant)
        run = self.the_run(result, "the block (model)", "tee-count-stocked", 1)
        self.assertEqual((run["answered"], run["own"], run["buyable"], run["verdict"]),
                         ("buyable", "wrong", "correct", "correct"))
        self.assertEqual(result["problems"], [])

    def test_a_run_with_no_key_for_its_reading_is_in_no_test_of_correct(self):
        # A rewording of tee-count-stocked answered under the buyable reading where the
        # sidecar has no buyable key for it: unscored, so H4's tee-count-stocked stratum
        # holds the block (model)'s other runs, and the run is listed as a problem.
        found = {}

        def plant(model, arm, folder):
            if arm.name == "the block (model)":
                found["id"] = rw = rewording_of(folder, "tee-count-stocked", V2_SOURCE)
                key = drop_key(folder.parent / "tasks", rw)
                answer_under(folder, rw, 1, "buyable", right(key))
                found["batch"] = folder.name
                found["rewordings"] = sum(1 for t in json.loads((folder.parent / "tasks" / TASKS_FILE).read_text())["tasks"]
                                          if t.get("template") == "tee-count-stocked")
        _, result, out = self.run2(plant)
        run = self.the_run(result, "the block (model)", found["id"], 1)
        self.assertEqual((run["answered"], run["verdict"]), ("buyable", "unscored"))
        # The stratum holds the template's rewordings, three rounds each, less the unscored run.
        h4 = result["models"][DEEPSEEK]["primary"]["H4"]
        judged = 3 * found["rewordings"] - 1
        self.assertEqual(next(row["a"] for row in h4["per_question"] if row["task"] == "tee-count-stocked"),
                         [judged, judged])
        self.assertIn(f"{DEEPSEEK}: {found['batch']}/{found['id']}-1 has no key for the reading it answered, buyable, "
                      f"so it is unscored and in no test of correct", result["problems"])
        self.assertRegex(out, rf"\n     tee-count-stocked +{judged}/{judged}  asked")

    def test_the_parses_fallbacks_are_counted_by_arm_with_their_reasons(self):
        # One planted of each kind: the block (model) left the model's form for the rules' on
        # one run, and the block (rules) planned one question by the survey fallback.
        def plant(model, arm, folder):
            payload = json.loads((folder / "suite.json").read_text())
            for row in payload["rows"]:
                if arm.name == "the block (model)" and (row["task"], row["repeat"]) == ("tee-target-price", 1):
                    row["box"]["parse"].update(used="rules", fallback_reason="the reply is not a form")
                if arm.name == "the block (rules)" and (row["task"], row["repeat"]) == ("tee-top-3", 2):
                    row["box"]["fallback"] = True
            (folder / "suite.json").write_text(json.dumps(payload))
        _, result, out = self.run2(plant)
        fallbacks = result["models"][DEEPSEEK]["secondary"]["fallbacks"]
        self.assertEqual((fallbacks["the block (model)"]["parse_fallback"], fallbacks["the block (model)"]["reasons"],
                          fallbacks["the block (model)"]["survey_fallback"]), (1, {"the reply is not a form": 1}, 0))
        self.assertEqual((fallbacks["the block (rules)"]["survey_fallback"], fallbacks["the block (rules)"]["parse_fallback"]),
                         (1, 0))
        self.assertIn("1 the reply is not a form", out)

    def test_a_closed_slot_with_no_charge_is_unknown_not_free(self):
        def plant(model, arm, folder):
            if arm.name == "the block (model)":
                payload = json.loads((folder / "suite.json").read_text())
                for row in payload["rows"]:
                    if (row["task"], row["repeat"]) == ("decline-fit", 1):
                        row["cost_usd"] = row["parse_cost_usd"] = None
                (folder / "suite.json").write_text(json.dumps(payload))
        _, result, _ = self.run2(plant)
        row = result["models"][DEEPSEEK]["tables"]["the block (model)"]["decline-fit"]
        self.assertEqual((row["cost_mean"], row["cost_missing"]), (0.002, 1))
        self.assertIsNone(self.the_run(result, "the block (model)", "decline-fit", 1)["cost"])

    def test_batches_on_two_task_files_are_refused(self):
        # The same questions under another file's name: the sets are one task file's ids.
        def plant(model, arm, folder):
            if arm.name == "shipped":
                tasks_dir = folder.parent / "tasks"
                for name in (TASKS_FILE, READINGS_FILE):
                    (tasks_dir / name.replace("claim2dev", "claim2other")).write_text((tasks_dir / name).read_text())
                set_conditions(folder, tasks_file=TASKS_FILE.replace("claim2dev", "claim2other"))
        with self.assertRaises(SystemExit) as raised:
            self.run2(plant)
        self.assertIn("the batches read 2 task files", str(raised.exception))


def drop_key(tasks_dir: pathlib.Path, task_id: str) -> dict:
    """A question's buyable key taken out of the sidecar; the key is returned."""
    path = tasks_dir / READINGS_FILE
    sidecar = json.loads(path.read_text())
    key = sidecar["readings"]["buyable"].pop(task_id)
    path.write_text(json.dumps(sidecar))
    return key


def showcase(model: str, arm: Plan, folder: pathlib.Path) -> None:
    """Every fault the verifier's fairness audit of 23 October 2026 named, planted in one run
    of the synthetic batches: the block (model) closes two slots on the gated questions, an
    ask no reply answered; shipped sorts one run and sets 60 a page in another, gives a card
    price, a sold-out price and a plain wrong one after reaching page 2, and a card price
    without reaching it; open everything sorts one run; and the block (rules) names as the
    cheapest a seller its key never excluded, which the batch stored as correct.

    And its re-audit's (protocol analysis v3): shipped reaches page 2 on a question whose key
    is there; and the provider that served each call, GMICloud every one of the block
    (model)'s, GMICloud open everything's in rounds 1 and 2 and Relace in round 3, both in one
    of shipped's runs, and none named anywhere else. Since v5 the block (model)'s and open
    everything's are counted in their rows, as suite.py records them, and shipped's in its
    log alone, as a batch from before; the block (model)'s parse calls were served by
    DeepInfra, but one whose row names no provider.

    And design B's (v8, 24 October 2026): shipped gives a label's promo figure on tee-xs-price
    after reaching page 2, and affirms the label on tee-promo-check; the block (rules) gives
    the promo figure as its answer on tee-xs-price once and names it as working beside the
    right price once, affirms the label on tee-promo-check in two ways and refutes it in a
    third, and falls for it on a v3-shaped rewording of tee-xs-price; the block (model) asks
    on tee-target-price for a clash of the word list and the model, the ask closing the slot,
    and its round-2 ask on tee-count-stocked, answered by the scripted shopper, was a clash
    too; and one run of open everything read the page's variant store."""
    card, sold_out = fixture_prices(folder)
    promos = promo_figures(folder)
    xs = task_of(folder, "tee-xs-price")["expect"]
    check = task_of(folder, "tee-promo-check")["expect"]
    if arm.name == "the block (model)":
        close_slot(folder, "tee-count-stocked", 1)
        close_slot(folder, "tee-all-stocked", 2)
        close_slot(folder, "tee-target-price", 3, reason="clash")
        set_ask_reason(folder, "tee-count-stocked", 2, "clash")
        set_clash_settled(folder, "tee-exists-under", 1)
        set_ask_reason(folder, "tee-count-stocked", 3, "ambiguous")
        served_rows(folder, lambda row: {"GMICloud": 2},
                    lambda row: None if (row["task"], row["repeat"]) == ("decline-fit", 1) else "DeepInfra")
    if arm.name == "shipped":
        add_pages(folder, "tee-target-price", 1, f"{SEARCH}&p=2")
        answer_with(folder, "tee-target-price", 1, f"The lowest is ${card:.2f}.")
        add_pages(folder, "tee-target-price", 2, f"{SEARCH}&p=2")
        answer_with(folder, "tee-target-price", 2, f"The lowest is ${sold_out:.2f}.")
        add_pages(folder, "tee-target-price", 3, f"{SEARCH}&product_list_limit=60")
        add_pages(folder, "tee-cheapest-target", 1, f"{SEARCH}&product_list_order=price")
        # A card price, on a question whose key renders on page 1, so page 1 alone is no code.
        answer_with(folder, "tee-exists-under", 1, f"Yes, at ${card:.2f}.")
        # Bexhill, tee-top-3's key, renders 39th: this run saw page 2.
        add_pages(folder, "tee-top-3", 1, f"{SEARCH}&p=2")
        serve(folder, "tee-headline", 1, "GMICloud", "Relace")
        # The label's figure taken, after page 2, so the page code cannot come first; and the
        # label affirmed where the question quotes its figure, which is no label code.
        add_pages(folder, "tee-xs-price", 1, f"{SEARCH}&p=2")
        answer_with(folder, "tee-xs-price", 1, f"The lowest is ${promos[0]:.2f}.")
        answer_with(folder, "tee-promo-check", 1, f"Yes, ${check['trap']:.2f}.")
    if arm.name == "open everything (product)":
        add_pages(folder, "tee-count-buyable", 2, f"{SEARCH}&product_list_order=name")
        served_rows(folder, lambda row: {"GMICloud" if row["repeat"] < 3 else "Relace": 1})
        add_leak(folder, "tee-count-buyable", 1)
    if arm.name == "the block (rules)":
        # Stored correct, as a scorer without the market's sellers stored it before score v7.
        expect = task_of(folder, "tee-cheapest-target")["expect"]
        answer_with(folder, "tee-cheapest-target", 1, f"{another_seller(folder, expect)} is the cheapest for size M at "
                                                      f"$1.00. {expect['any'][0]} is next at ${expect['price']:.2f}.",
                    stored="correct")
        answer_with(folder, "tee-xs-price", 1, f"The lowest is ${promos[0]:.2f}.")
        answer_with(folder, "tee-xs-price", 2, f"A label says promo ${promos[0]:.2f}, but the lowest price that can "
                                               f"be bought is ${xs['value']:.2f}.")
        answer_with(folder, "tee-promo-check", 1, f"Yes. Size XS costs ${check['trap']:.2f} there.")
        answer_with(folder, "tee-promo-check", 2, f"The promotion claim is accurate: ${check['trap']:.2f}.")
        answer_with(folder, "tee-promo-check", 3, "No.")
        answer_with(folder, rewording_of(folder, "tee-xs-price"), 1, f"The lowest is ${promos[1]:.2f}.")


# The slots the showcase closes in the block (model)'s batch, besides the declines.
SHOWCASE_CLOSED = 3


class AuditItems(unittest.TestCase):
    """Protocol analysis v2 (23 October 2026): each rule the verifier's fairness audit asked
    for, firing on the synthetic run that carries its fault (`showcase`), and design B's three
    measures and failure code (v8). The plain run, where each must stay quiet, is
    SyntheticRun2's."""

    @classmethod
    def setUpClass(cls):
        cls.owner = tempfile.TemporaryDirectory()
        root = pathlib.Path(cls.owner.name)
        cls.code, cls.result, cls.out = analyse(build_run2(root, plant=showcase))
        cls.m = cls.result["models"][DEEPSEEK]
        cls.spec = json.loads((root / "tasks" / TASKS_FILE).read_text())
        cls.promos = sorted(xs_of(f)["label_price"] for f in fixture_of(root / "tasks")["families"]
                            if xs_of(f).get("label_kind") == "promo")

    @classmethod
    def tearDownClass(cls):
        cls.owner.cleanup()

    def row(self, test: dict, task: str) -> dict:
        return next(row for row in test["per_question"] if row["task"] == task)

    def test_h2_and_h3_count_only_the_slots_where_the_agent_ran(self):
        # The block (model) closed tee-count-stocked's first round and tee-all-stocked's
        # second: each stratum holds its two runs, 8 opened at $0.30, and the closed slots are
        # listed. Put back, each is 0 listings at the parse's $0.002.
        for name, value, closed_value in (("H2", 8, 0), ("H3", 0.30, 0.002)):
            test = self.m["primary"][name]
            with self.subTest(test=name):
                for task in ("tee-count-stocked", "tee-all-stocked"):
                    self.assertEqual(self.row(test, task)["a"], [value, value])
                self.assertEqual(test["closed"], [{"task": "tee-target-price", "a": 1, "b": 0},
                                                  {"task": "tee-all-stocked", "a": 1, "b": 0},
                                                  {"task": "tee-count-stocked", "a": 1, "b": 0}])
                back = self.m["sensitivity"]["with the closed slots in H2 and H3"][name]
                self.assertEqual(sorted(self.row(back, "tee-count-stocked")["a"]), [closed_value, value, value])
        self.assertIn("slots the box closed, no agent run, left out (a the block (model), b open everything "
                      "(product)): tee-target-price 1/0, tee-all-stocked 1/0, tee-count-stocked 1/0", self.out)

    def test_sorting_and_page_size_are_counted_by_arm(self):
        table = self.m["secondary"]["toolbar"]
        got = {arm: (row["sorted"], row["resized"]) for arm, row in table.items()}
        self.assertEqual(got, {"shipped": (1, 1), "open everything (product)": (1, 0),
                               "the block (rules)": (0, 0), "the block (model)": (0, 0)})
        named = {n["run"].split("/")[1]: (n["sorted"], n["page size"]) for n in table["shipped"]["named"]}
        self.assertEqual(named, {"tee-cheapest-target-1": (["price"], []), "tee-target-price-3": ([], ["60"])})
        # Dropped in the sensitivity: shipped's tee-target-price and tee-cheapest-target keep
        # two runs each in H1, open everything's tee-count-buyable two in H2.
        dropped = self.m["sensitivity"]["without the runs that sorted or changed the page size"]
        self.assertEqual(self.row(dropped["H1"], "tee-cheapest-target")["b"], [0, 2])
        self.assertEqual(self.row(dropped["H1"], "tee-target-price")["b"], [0, 2])
        self.assertEqual(len(self.row(dropped["H2"], "tee-count-buyable")["b"]), 2)
        self.assertEqual(self.row(self.m["primary"]["H1"], "tee-target-price")["b"], [0, 3])

    def test_the_shipped_failures_are_coded_by_the_written_rules(self):
        fb = self.m["secondary"]["failure_breakdown"]
        codes = {run["run"].split("/")[1]: run["code"] for run in fb["runs"]}
        self.assertEqual((fb["failures"], fb["of"]), (21, 21))
        card, sold_out = fixture_prices(pathlib.Path(self.owner.name) / "x")
        self.assertEqual({tag: codes[tag] for tag in ("tee-target-price-1", "tee-target-price-2", "tee-target-price-3",
                                                      "tee-cheapest-target-1", "tee-exists-under-1", "tee-top-3-1",
                                                      "tee-top-3-2", "tee-xs-price-1", "tee-promo-check-1")},
                         {"tee-target-price-1": "a card or sold-out price taken",
                          "tee-target-price-2": "a card or sold-out price taken",
                          # 60 a page shows every listing: past page 1, and $1.00 is no price shown.
                          "tee-target-price-3": "other",
                          # Sorted by price and never past its first page: whether it needed
                          # a later page is not known (v4); "other" in v3, and before that
                          # "page 2 never reached".
                          "tee-cheapest-target-1": "sorted or resized, its first page alone",
                          # Page 1 alone too, where its key is: the card price decides (v3).
                          "tee-exists-under-1": "a card or sold-out price taken",
                          # Its key is on page 2 (Bexhill, 39th): reached in round 1, not in 2.
                          "tee-top-3-1": "other",
                          "tee-top-3-2": "page 2 never reached",
                          # The label's figure, after page 2 (v8); and the figure the question
                          # quotes, repeated in a yes, which is no label code.
                          "tee-xs-price-1": "a label's figure taken",
                          "tee-promo-check-1": "other"})
        evidence = {run["run"].split("/")[1]: run["evidence"] for run in fb["runs"]}
        self.assertEqual(evidence["tee-target-price-1"], f"card ${card:.2f}")
        self.assertEqual(evidence["tee-target-price-2"], f"sold out ${sold_out:.2f}")
        self.assertEqual(evidence["tee-cheapest-target-1"], "sorted price, page size -; results pages seen: []")
        self.assertEqual(evidence["tee-xs-price-1"], f"label ${self.promos[0]:.2f}")
        # The plain run's 6, 0, 0, 0 and 15 (SyntheticRun2), less tee-top-3-1 from the first, and
        # tee-cheapest-target-1, tee-target-price-1 and -2, tee-exists-under-1 and tee-xs-price-1
        # from the last.
        self.assertEqual(fb["pooled"], {"page 2 never reached": 5, "sorted or resized, its first page alone": 1,
                                        "a card or sold-out price taken": 3, "a label's figure taken": 1, "other": 11})
        self.assertIn("f. Why shipped was not correct", self.out)

    def test_the_cautious_sensitivity_puts_a_closed_slot_at_open_everythings_median(self):
        # The block (model)'s closed slots on the gated questions, each back at open
        # everything's median for its question, 21 listings and $0.60, its tokens 900k: as if
        # each had run as open everything runs (R6).
        tests = self.m["sensitivity"]["with the closed slots in H2 and H3 at open everything's median"]
        for name, value, median in (("H2", 8, 21), ("H3", 0.30, 0.60)):
            with self.subTest(test=name):
                for task in ("tee-count-stocked", "tee-all-stocked", "tee-target-price"):
                    self.assertEqual(sorted(self.row(tests[name], task)["a"]), [value, value, median])
                    self.assertEqual(self.row(tests[name], task)["b"], [median] * 3)
                self.assertEqual(tests[name]["closed_rule"], "in at the other arm's median")
        self.assertEqual(sorted(self.row(tests["H3"]["also"], "tee-count-stocked")["a"]), [380_000, 380_000, 900_000])
        # The primary's own leave them out, and the other sensitivity puts them in as recorded.
        self.assertEqual(self.m["primary"]["H2"]["closed_rule"], "left out")
        self.assertEqual(sorted(self.row(self.m["sensitivity"]["with the closed slots in H2 and H3"]["H2"],
                                         "tee-count-stocked")["a"]), [0, 8, 8])

    def test_the_serving_provider_by_arm_and_h3_by_provider(self):
        providers = self.m["secondary"]["providers"]
        by_arm = {arm: row["by_provider"] for arm, row in providers["by_arm"].items()}
        # The block (model) ran 135 of its 168 slots: three closed, and the 30 declines refused.
        # Open everything's 24 are its 16 runs of rounds 1 and 2 and 8 of round 3, from their
        # rows. Shipped's one run is mixed, read from its log, and the rest unknown: no row or
        # log counts them.
        self.assertEqual(by_arm, {"shipped": {"mixed: GMICloud, Relace": 1, "unknown": 38},
                                  "open everything (product)": {"GMICloud": 16, "Relace": 8},
                                  "the block (rules)": {"unknown": 138},
                                  "the block (model)": {"GMICloud": 135}})
        rows = providers["by_arm"]
        self.assertEqual((rows["the block (model)"]["calls"], rows["the block (model)"]["calls_unknown"]),
                         ({"GMICloud": 270}, 0))
        # A run whose count is missing is unknown, never zero calls (v5).
        self.assertEqual((rows["shipped"]["calls"], rows["shipped"]["calls_unknown"]),
                         ({"GMICloud": 1, "Relace": 1}, 38))
        # The parse calls, every slot of the model arm, the closed ones too, by their rows: one
        # names no provider and is unknown. No other arm parses.
        self.assertEqual(rows["the block (model)"]["parse_calls"], {"DeepInfra": 167, "unknown": 1})
        self.assertEqual({arm: row["parse_calls"] for arm, row in rows.items() if arm != "the block (model)"},
                         {"shipped": {}, "open everything (product)": {}, "the block (rules)": {}})
        h3 = providers["h3"]
        self.assertEqual((h3["test"], h3["a"], h3["b"], h3["differs"]),
                         ("H3", "the block (model)", "open everything (product)", True))
        # Within GMICloud, the only provider that served whole runs of both: the eight gated
        # questions, open everything's two runs of each. Relace served only open everything's.
        self.assertEqual(list(h3["tests"]), ["GMICloud"])
        within = h3["tests"]["GMICloud"]
        self.assertEqual([row["task"] for row in within["per_question"]], self.result["sets"]["gated"])
        self.assertEqual((self.row(within, "tee-count-stocked")["a"], self.row(within, "tee-count-stocked")["b"]),
                         ([0.30, 0.30], [0.60, 0.60]))
        self.assertIn("h. Who served the model's calls, by arm", self.out)
        self.assertIn("H3 by provider, the block (model) against open everything (product): the mixes differ", self.out)

    def test_a_verdict_the_markets_sellers_move_is_listed(self):
        # The block (rules) named a seller the key never excluded the cheapest: the batch
        # stored it correct, scored without the market's sellers as suite.py scored before
        # score v7; this analysis scores it with them, wrong, and says so rather than applying
        # it unseen.
        run = next(r for r in self.m["runs"] if (r["arm"], r["task"], r["repeat"])
                   == ("the block (rules)", "tee-cheapest-target", 1))
        self.assertEqual(run["verdict"], "wrong")
        moved = [p for p in self.result["problems"] if "stored verdict correct, re-scored wrong" in p]
        self.assertEqual([p.split(": ")[0].split("/")[1] for p in moved], ["tee-cheapest-target-1"])
        self.assertEqual(len(self.result["problems"]), 1)

    def test_the_asks_the_word_list_clash_caused(self):
        # The block (model) asked on tee-target-price, a clear question, for a clash, and no reply
        # closed the slot; its round-2 ask on tee-count-stocked, a two-reading question answered by
        # the scripted shopper, was a clash too. Every ask the box itself made says "ambiguous",
        # the question's own two readings (box v19, every ask says why; until the box branch was
        # merged on 24 October 2026 the box recorded no reason and these read "not recorded").
        # The two slots the fixture closes by hand without a reason (`close_slot`) still read
        # "not recorded", as a record from a box before v19 does. The rules arm's six asks are
        # the box's own, so each says "ambiguous".
        clashes = self.m["secondary"]["clash_asks"]
        model = clashes["the block (model)"]
        # Seven asks: the two two-reading templates' six (two of them closed), and the clash's.
        self.assertEqual((model["asks"], model["clash"], model["clash_by_label"]),
                         (7, 2, {"clear": 1, "ambiguous": 1}))
        self.assertEqual(model["reasons"], {"ambiguous": 3, "clash": 2, "not recorded": 2})
        # The closed slot has no record, so it is read after the runs that have one.
        self.assertEqual(sorted((n["run"].split("/")[1], n["closed"]) for n in model["named"]),
                         [("tee-count-stocked-2", False), ("tee-target-price-3", True)])
        self.assertEqual((clashes["the block (rules)"]["asks"], clashes["the block (rules)"]["clash"],
                          clashes["the block (rules)"]["reasons"]), (6, 0, {"ambiguous": 6}))
        self.assertEqual({arm: row["asks"] for arm, row in clashes.items() if not arm.startswith("the block")},
                         {"shipped": 0, "open everything (product)": 0})
        self.assertIn("clashes 2 (on clear questions 1, on two-reading questions 1)", self.out)
        # A clash the box settled itself, no ask put (box v20): counted beside, by arm (v9).
        self.assertEqual((model["settled"], [n.split("/")[1] for n in model["settled_named"]]), (1, ["tee-exists-under-1"]))
        self.assertEqual((clashes["the block (rules)"]["settled"], clashes["shipped"]["settled"]), (0, 0))
        self.assertIn("and 1 clashes the box settled itself, no ask put", self.out)
        self.assertIn("tee-target-price-3, the ask closed the slot", self.out)

    def test_the_promo_traps_fallen_for_by_arm(self):
        # The rules arm on tee-xs-price: 9 runs that answered (the template and its two v3-shaped
        # rewordings, three rounds each); the round-1 template run gave the promo figure as its
        # answer, and the rewording's round 1 the second promo figure, 2; the round-2 run named
        # the figure as working and gave the right price, not fallen. On tee-promo-check: "Yes"
        # and "the claim is accurate" fell, "No." did not; the odd-numbered rewording's three runs
        # are right and the even-numbered one's three wrong answers affirm the label, so 5 of 9.
        # Shipped affirmed the label on every tee-promo-check run, 3 of 3, and gave the figure on
        # tee-xs-price once, 1 of 3. The model arm fell for nothing.
        # Since protocol analysis v9 the template's runs and the held-out rewordings' are apart.
        traps = self.m["secondary"]["promo_traps"]
        rules = traps["the block (rules)"]
        xs = rules["tee-xs-price"]
        self.assertEqual((xs["template"]["runs"], xs["template"]["fell_for"], xs["held_out"]["runs"], xs["held_out"]["fell_for"]),
                         (3, 1, 6, 1))
        self.assertEqual([n.split("/")[1] for n in xs["template"]["named"]], ["tee-xs-price-1"])
        self.assertEqual([n.split("/")[1] for n in xs["held_out"]["named"]],
                         [f"{rewording_of(pathlib.Path(self.owner.name) / 'x', 'tee-xs-price')}-1"])
        # The rules are wrong on the even-numbered rewording, whose wrong answer affirms the label.
        check = rules["tee-promo-check"]
        self.assertEqual((check["template"]["runs"], check["template"]["fell_for"], check["held_out"]["runs"],
                          check["held_out"]["fell_for"]), (3, 2, 6, 3))
        self.assertEqual([n.split("/")[1] for n in check["template"]["named"]], ["tee-promo-check-1", "tee-promo-check-2"])
        shipped = traps["shipped"]
        self.assertEqual((shipped["tee-xs-price"]["template"]["fell_for"], shipped["tee-promo-check"]["template"]["fell_for"]),
                         (1, 3))
        self.assertEqual(shipped["tee-promo-check"]["template"]["interval"], list(claim.wilson(3, 3)))
        # Shipped asks no rewording: its held-out rows are empty, never pooled with the block's.
        self.assertEqual(shipped["tee-xs-price"]["held_out"]["runs"], 0)
        self.assertEqual({q: (row["template"]["fell_for"], row["held_out"]["fell_for"]) for q, row in traps["the block (model)"].items()},
                         {"tee-xs-price": (0, 0), "tee-promo-check": (0, 0)})
        # Open everything does not ask the lookup: no run, no share.
        self.assertEqual(traps["open everything (product)"]["tee-promo-check"]["template"],
                         {"runs": 0, "fell_for": 0, "share": None, "interval": None, "named": []})
        self.assertIn("k. Promo traps fallen for", self.out)
        self.assertIn("the template's runs and its held-out rewordings' apart", self.out)
        self.assertRegex(self.out, r"the block \(rules\) +tee-xs-price +held_out +1 of 6")

    def test_the_hidden_price_leaks_by_arm(self):
        leaks = self.m["secondary"]["leaks"]
        self.assertEqual({arm: row["leaked"] for arm, row in leaks.items()},
                         {"shipped": 0, "open everything (product)": 1, "the block (rules)": 0, "the block (model)": 0})
        named = leaks["open everything (product)"]["named"]
        self.assertEqual(named[0]["run"].split("/")[1], "tee-count-buyable-1")
        self.assertIn("the store", named[0]["found"])
        # The sensitivity drops the run: open everything keeps two runs of that question in H2.
        dropped = self.m["sensitivity"]["without the runs that saw a hidden price"]
        self.assertEqual(len(self.row(dropped["H2"], "tee-count-buyable")["b"]), 2)
        self.assertEqual(len(self.row(self.m["primary"]["H2"], "tee-count-buyable")["b"]), 3)
        self.assertIn("l. Hidden-price leaks by arm", self.out)

    def test_each_model_has_its_role_and_its_own_holm(self):
        self.assertEqual(list(self.result["models"]), [DEEPSEEK])
        self.assertEqual(self.m["role"], "primary")
        self.assertIn(f"Model {DEEPSEEK}, the primary: its four tests are the claim, Holm over the four.", self.out)
        ps = {name: t["p"] for name, t in self.m["primary"].items()}
        self.assertEqual({name: t["p_holm"] for name, t in self.m["primary"].items()}, claim.holm(ps))


# The design the protocol file holds (version 7, design B): DeepSeek alone, plan 2a's rounds.
DESIGN_B = {DEEPSEEK: {"asks": {"shipped": {"templates": [1, 2, 3]},
                                "open everything (product)": {"gated": [1, 2, 3]},
                                "the block (rules)": {"templates": [1, 2, 3], "held_out": [1]},
                                "the block (model)": {"templates": [1, 2, 3], "held_out": [1]}},
                       "tests": ["H1", "H2", "H3", "H4"]}}


class DesignB(unittest.TestCase):
    """The protocol file's own design (version 7): DeepSeek alone, the templates in rounds 1 to 3
    under all four arms and the held-out rewordings in round 1 alone under both block arms, on
    synthetic batches written as it asks."""

    @classmethod
    def setUpClass(cls):
        cls.owner = tempfile.TemporaryDirectory()
        root = pathlib.Path(cls.owner.name)
        manifest = build_run2(root, protocol=PROTOCOL)
        cls.spec = json.loads((root / "tasks" / TASKS_FILE).read_text())
        cls.config = json.loads(PROTOCOL.read_text())
        cls.code, cls.result, cls.out = analyse(manifest, PROTOCOL)
        cls.m = cls.result["models"][DEEPSEEK]

    @classmethod
    def tearDownClass(cls):
        cls.owner.cleanup()

    def test_the_one_model_runs_its_design_and_no_slot_is_missing(self):
        self.assertEqual((self.code, self.result["problems"]), (0, []))
        # Shipped the 13 templates and open everything the 8 gated, three rounds each; each block
        # arm the 13 templates in three rounds and the 43 rewordings in one: 39, 24, 82 and 82
        # runs, 227 slots.
        self.assertEqual({arm: a["runs"] for arm, a in self.m["arms"].items()},
                         {"shipped": 39, "open everything (product)": 24, "the block (rules)": 82,
                          "the block (model)": 82})
        design = self.m["exclusions"]["design"]
        self.assertEqual((design["slots"], design["filled"], design["missing"]), (227, 227, []))
        self.assertEqual(self.result["design"], {DEEPSEEK: {"shipped": 39, "open everything (product)": 24,
                                                            "the block (rules)": 82, "the block (model)": 82}})
        self.assertEqual((self.result["families"], self.result["models_named"]), ({DEEPSEEK: ["H1", "H2", "H3", "H4"]}, [DEEPSEEK]))
        self.assertEqual(self.m["not_run_by_design"], {"arms": [], "tests": [], "sensitivities": []})
        self.assertIn("shipped 39, open everything (product) 24, the block (rules) 82, the block (model) 82", self.out)

    def test_h4_reads_the_one_round_of_the_rewordings(self):
        # Round 1 alone: one run a rewording and arm, 36 an arm. The model is right on all, the
        # rules on the odd-numbered rewordings.
        held = {task["id"]: task for task in self.spec["tasks"] if task.get("template")}
        h4 = self.m["primary"]["H4"]
        for row in h4["per_question"]:
            ids = [t for t in held.values() if t["template"] == row["task"]]
            self.assertEqual(row["a"], [len(ids), len(ids)])
            self.assertEqual(row["b"], [sum(t["rewording"] % 2 for t in ids), len(ids)])
        self.assertEqual(h4["pooled"]["a"], [36, 36])
        by_rewording = self.m["sensitivity"]["H4 by rewording, not by run"]["H4"]
        self.assertEqual((len(by_rewording["pooled"]["a"]), len(by_rewording["pooled"]["b"])), (36, 36))
        # The two splits read the one round too: v3's new-template rewordings, 4 runs an arm.
        by_kind = next(s for s in self.m["splits"]["H4"] if s["within"] == "held_out_v3")
        self.assertEqual(by_kind["parts"][0]["pooled"]["a"], [4, 4])

    def test_a_rewording_run_in_a_round_the_design_has_not_is_in_no_figure(self):
        # The block (model) asked rw-01 in round 2 too: listed, and H4's stratum of its template
        # still holds the one round.
        template = next(t["template"] for t in self.spec["tasks"] if t["id"] == "rw-01")
        held = sum(1 for t in self.spec["tasks"] if t.get("template") == template)

        def asks(model, design):
            arm = design["the block (model)"]
            return {**design, "the block (model)": {**arm, "rw-01": (1, 2)}}
        with tempfile.TemporaryDirectory() as tmp:
            _, result, _ = analyse(build_run2(pathlib.Path(tmp), asks=asks, protocol=PROTOCOL), PROTOCOL)
        self.assertIn(f"{DEEPSEEK}: a run the design does not ask for, the block (model), rw-01 repeat 2",
                      result["problems"])
        h4 = result["models"][DEEPSEEK]["primary"]["H4"]
        self.assertEqual(next(row["a"] for row in h4["per_question"] if row["task"] == template), [held, held])
        self.assertEqual(result["models"][DEEPSEEK]["arms"]["the block (model)"]["runs"], 82)


class TheDesign(unittest.TestCase):
    """The protocol file's design (version 7), and a design that does not hold together is
    refused before any batch is read, by `check_protocol` or, against the task file, by
    `resolve_protocol`."""

    @classmethod
    def setUpClass(cls):
        cls.owner = tempfile.TemporaryDirectory()
        build_task_files(pathlib.Path(cls.owner.name))
        cls.spec = json.loads((pathlib.Path(cls.owner.name) / TASKS_FILE).read_text())
        cls.config = json.loads(PROTOCOL.read_text())

    @classmethod
    def tearDownClass(cls):
        cls.owner.cleanup()

    def changed(self, change) -> dict:
        config = json.loads(json.dumps(self.config))
        change(config)
        return config

    def test_the_file_holds_design_b(self):
        self.assertEqual(self.config["design"], DESIGN_B)
        self.assertEqual((self.config["version"], self.config["models"], self.config["roles"]),
                         (8, [DEEPSEEK], {DEEPSEEK: "primary"}))
        with pointed_at(pathlib.Path(self.owner.name)):
            self.assertEqual(claim.check_protocol(self.config), [])
            protocol = claim.resolve_protocol(PROTOCOL, self.config, self.spec)
        slots = {arm: sum(len(r) for r in questions.values()) for arm, questions in protocol.of(DEEPSEEK).design.items()}
        self.assertEqual(slots, {"shipped": 39, "open everything (product)": 24, "the block (rules)": 82,
                                 "the block (model)": 82})
        self.assertEqual(list(protocol.of(DEEPSEEK).tests), ["H1", "H2", "H3", "H4"])
        # Haiku, unnamed, would run the primary's design, as any unnamed model does.
        self.assertEqual(protocol.design_of(HAIKU), protocol.design_of(DEEPSEEK))

    def test_a_design_that_does_not_hold_together_is_refused(self):
        for label, change, words in (
                ("a model with no design", lambda c: c["design"].pop(DEEPSEEK),
                 "the design does not name the protocol's models"),
                ("the one design of versions 1 to 5", lambda c: c.update(design={"rounds": [1, 2, 3], "asks": {}}),
                 "the design does not name the protocol's models"),
                ("a design without its family", lambda c: c["design"][DEEPSEEK].pop("tests"),
                 f"the design of {DEEPSEEK} is not its asks and its tests"),
                ("an arm the protocol has not", lambda c: c["design"][DEEPSEEK]["asks"].update({"the agent": {"templates": [1]}}),
                 "an arm the protocol has not: 'the agent'"),
                ("a set the protocol does not name",
                 lambda c: c["design"][DEEPSEEK]["asks"]["shipped"].update({"everything": [1]}),
                 "a set the protocol does not name: 'everything'"),
                ("an arm that asks no set", lambda c: c["design"][DEEPSEEK]["asks"].update(shipped={}), "ask no set"),
                ("a round twice", lambda c: c["design"][DEEPSEEK]["asks"]["shipped"].update(templates=[1, 1]),
                 "not distinct round numbers from 1"),
                ("round 0", lambda c: c["design"][DEEPSEEK]["asks"]["shipped"].update(templates=[0, 1]),
                 "not distinct round numbers from 1"),
                ("no round", lambda c: c["design"][DEEPSEEK]["asks"]["shipped"].update(templates=[]),
                 "not distinct round numbers from 1"),
                ("a test the protocol has not", lambda c: c["design"][DEEPSEEK]["tests"].append("H5"),
                 "a test the protocol has not: 'H5'"),
                ("no family", lambda c: c["design"][DEEPSEEK].update(tests=[]), "names no family of tests"),
                ("the primary's family short of a test", lambda c: c["design"][DEEPSEEK]["tests"].remove("H4"),
                 "the primary model's family, deepseek/deepseek-v4-flash's, does not hold every test")):
            with self.subTest(fault=label):
                found = claim.check_protocol(self.changed(change))
                self.assertTrue(any(words in problem for problem in found), found)
        # Against the task file: a test's arms in different rounds, and a question two sets of
        # one arm ask.
        for label, change, words in (
                ("H4's arms in different rounds",
                 lambda c: c["design"][DEEPSEEK]["asks"]["the block (rules)"].update(held_out=[1, 2, 3]),
                 f"H4 of {DEEPSEEK} is on held_out"),
                ("a question in two of an arm's sets",
                 lambda c: c["design"][DEEPSEEK]["asks"]["shipped"].update(reading_independent=[1]),
                 f"the design has {DEEPSEEK}'s shipped ask tee-target-price in two of its sets")):
            with self.subTest(fault=label):
                config = self.changed(change)
                self.assertEqual(claim.check_protocol(config), [])
                with pointed_at(pathlib.Path(self.owner.name)), self.assertRaises(SystemExit) as raised:
                    claim.resolve_protocol(PROTOCOL, config, self.spec)
                self.assertIn(words, str(raised.exception))

    def test_the_sets_fit_the_task_file_and_a_stray_one_is_refused(self):
        # A set naming a question the file lacks, as the water questions are now.
        config = self.changed(lambda c: c["sets"]["gated"].append("water-target-price"))
        with pointed_at(pathlib.Path(self.owner.name)), self.assertRaises(SystemExit) as raised:
            claim.resolve_protocol(PROTOCOL, config, self.spec)
        self.assertIn("water-target-price", str(raised.exception))


class TwoReadings(unittest.TestCase):
    """Which questions have two readings, for claim.py (task F, item 1): the A+ sidecar keys
    every question, so being keyed no longer says a question has two, and its `two_readings`
    names them. The first claim's sidecar has no such field, and keeps the rule it had."""

    def test_the_sidecar_names_them_or_says_nothing(self):
        self.assertEqual(score.two_readings_for(paths.TASKS / "tasks_aplus_dev.json"),
                         ["tee-all-stocked", "tee-count-stocked", "water-all-stocked"])
        self.assertIsNone(score.two_readings_for(paths.TASKS / "tasks_claim_apparel.json"))
        self.assertIsNone(score.two_readings_for(paths.TASKS / "tasks_reviews.json"))    # no sidecar
        # Where it says nothing, every question it keys has two: the first claim's two.
        keyed = score.readings_for(paths.TASKS / "tasks_claim_apparel.json")
        self.assertEqual(sorted({task for keys in keyed.values() for task in keys}),
                         ["apparel-all-stocked", "apparel-count-stocked"])


class ProtocolFile(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(PROTOCOL.read_text())

    def test_the_file_is_whole(self):
        self.assertEqual(claim.check_protocol(self.config), [])

    def test_the_sets_are_design_bs(self):
        sets = self.config["sets"]
        self.assertEqual(sets["control"], ["tee-headline"])
        self.assertEqual(sets["decline"], ["decline-delivery", "decline-fit", "decline-scarcity"])
        self.assertEqual(sets["gated"], ["tee-target-price", "tee-cheapest-target", "tee-all-stocked", "tee-count-stocked",
                                         "tee-count-buyable", "tee-exists-under", "tee-top-3", "tee-xs-price"])
        self.assertEqual(sets["lookup"], ["tee-promo-check"])
        self.assertEqual(sets["two_readings"], ["tee-all-stocked", "tee-count-stocked"])
        self.assertEqual(sets["reading_independent"], ["tee-target-price", "tee-cheapest-target", "tee-count-buyable",
                                                       "tee-exists-under", "tee-top-3", "tee-xs-price", "tee-promo-check"])
        self.assertEqual((sets["count_two_readings"], sets["held_out"]), ("tee-count-stocked", "template"))
        self.assertEqual((sets["held_out_v2"], sets["held_out_v3"]),
                         ({"rewordings": {"source": V2_SOURCE}}, {"rewordings": {"source": V3_SOURCE}}))
        self.assertEqual(sets["kept_templates"], list(KEYED_TEMPLATES[:8]))
        self.assertEqual((sets["new_templates"], sets["promo_trap"]),
                         (["tee-xs-price", "tee-promo-check"], ["tee-xs-price", "tee-promo-check"]))
        # No water question, no water set, and no first-claim split.
        self.assertFalse(any("water" in json.dumps(value) for value in sets.values()))
        self.assertEqual(list(self.config["splits"]["H4"]), ["v2 against v3, within the kept eight templates",
                                                             "the two new templates against the kept eight, within v3"])
        self.assertEqual(self.config["promo_traps"], {"on": "promo_trap"})
        self.assertEqual(self.config["hand_reading"]["second_reader"], {"rows": 40, "seed": 20261024})
        self.assertEqual(self.config["reading_test"]["models"], [DEEPSEEK, HAIKU])
        self.assertIsNone(self.config["reading_test"]["provider_routing"][HAIKU])

    def test_the_notes_say_what_version_7_changed(self):
        notes = self.config["_about"]
        self.assertTrue(any(note.startswith("Version 7, 24 October 2026, design B") for note in notes))
        self.assertTrue(any(note.startswith("Version 8, 24 October 2026, from the verifier's logic audit at cd49128")
                            and "box 20 and form 15" in note and "clash_settled" in note for note in notes))
        self.assertEqual(self.config["version"], 8)
        for words in ("--rate-plan every is dropped", "primitives.every_rate", "'lookup' tee-promo-check",
                      "a label's figure taken", "asks caused by the word-list clash", "promo traps fallen for, by arm",
                      "random.Random(20261024)", "score v10", "01:58 on 24 October 2026", "ask_kind"):
            with self.subTest(words=words):
                self.assertTrue(any(words in note for note in notes), words)
        # The decided questions of 23 October say so where they stood.
        self.assertTrue(any("Pending decision 9" in note and "Decided (decision 7 of 24 October 2026)" in note
                            for note in notes))
        self.assertTrue(any("Pending decision 2" in note and "Decided (decisions 6 and 13 of 24 October 2026)" in note
                            for note in notes))

    def test_the_note_on_when_an_answer_is_unscorable(self):
        # The auditor's check of the freeze candidate: only an answer that cannot be read at all.
        notes = [note for note in self.config["_about"] if "'unscorable'" in note]
        self.assertEqual(len(notes), 1)
        self.assertIn("only when it cannot be read at all, being empty, garbled, or about another question", notes[0])

    def test_a_note_the_code_has_moved_past_says_it_is_superseded(self):
        # The first version's note on H3's tokens said the parse's are not recorded; since
        # cce9ab0 they are, and the note says so where it stands (v4).
        notes = [note for note in self.config["_about"] if "tokens are not recorded" in note]
        self.assertEqual(len(notes), 1)
        self.assertIn("Superseded in part: since cce9ab0", notes[0])

    def test_a_file_that_does_not_hold_together_is_refused_before_any_batch(self):
        config = self.config
        for label, change, words in (
                ("an unknown arm in a test", lambda c: c["tests"]["H1"].update(b="the agent"), "compares an arm"),
                ("an unknown measure", lambda c: c["tests"]["H2"].update(measure="speed"), "measures what"),
                ("template strata off the rewordings", lambda c: c["tests"]["H1"].update(strata="template"),
                 "only the held-out rewordings have"),
                ("a set missing", lambda c: c["sets"].pop("two_readings"), "names no two_readings set"),
                ("a sensitivity unknown", lambda c: c["sensitivity"].append("with luck"), "no sensitivity"),
                ("a condition no run records", lambda c: c["require"].update(colour="red"), "no run records"),
                ("two arms alike", lambda c: c["arms"]["shipped"].update(arm="box", reading="own"),
                 "same instruction and reading"),
                # Protocol analysis v3, from the re-audit.
                ("an arm's condition no run records",
                 lambda c: c["arms"]["the block (model)"]["require"].update(colour="red"),
                 "arm 'the block (model)' requires 'colour', which no run records"),
                ("a secondary measure unknown", lambda c: c["secondary_measures"].append("speed"),
                 "no secondary measure"),
                # Protocol analysis v4.
                ("a required value that is another condition no run records",
                 lambda c: c["arms"]["the block (model)"]["require"].update(parser_model={"same_as": "colour"}),
                 "which is no value and no other condition a run records"),
                # Protocol analysis v5.
                ("a routing for a model the protocol has not",
                 lambda c: c["provider_routing"].update({"x-ai/grok-5-mini": None}),
                 "provider_routing does not name the protocol's models"),
                ("no routing for the one model", lambda c: c["provider_routing"].pop(DEEPSEEK),
                 "provider_routing does not name the protocol's models"),
                ("a routing that is no provider object", lambda c: c["provider_routing"].update({DEEPSEEK: "off"}),
                 "neither a provider object nor null"),
                ("a routing required of an arm by hand",
                 lambda c: c["arms"]["shipped"].update(require={"provider_routing_agent": None}),
                 "which the protocol names by model under provider_routing"),
                # The verifier's check of 281c7e8: a typo OpenRouter would ignore.
                ("a routing key OpenRouter does not document",
                 lambda c: c["provider_routing"][DEEPSEEK].update(allow_fallback=False),
                 "the provider keys ['allow_fallback'], which OpenRouter does not document"),
                # Protocol analysis v2, 23 October 2026.
                ("two primaries", lambda c: c["roles"].update({HAIKU: "primary"}), "not the protocol's models"),
                ("a role this analysis has not", lambda c: c["roles"].update({DEEPSEEK: "lead"}), "role is not one of"),
                ("no primary", lambda c: c["roles"].update({DEEPSEEK: "replication"}), "other than one primary"),
                ("a split of a test the file has not", lambda c: c["splits"].update({"H9": {}}),
                 "a test the protocol has not"),
                ("a split of one set", lambda c: c["splits"]["H4"].update({"one": ["kept_templates"]}),
                 "is not two sets"),
                ("the failure codes out of order", lambda c: c["failure_breakdown"]["codes"].reverse(),
                 "codes are not this analysis's"),
                ("no page size", lambda c: c["failure_breakdown"].pop("page_size"), "names no page size"),
                # Protocol analysis v8, design B.
                ("a selection that is no rewordings object", lambda c: c["sets"].update(held_out_v3={"source": V3_SOURCE}),
                 "is an object that is not"),
                ("an empty selection", lambda c: c["sets"].update(held_out_v3={"rewordings": {}}), "is an object that is not"),
                ("a set of numbers", lambda c: c["sets"].update(odd=[1, 2]), "neither a list of question ids"),
                ("a split within a set the file has not",
                 lambda c: c["splits"]["H4"].update({"odd": {"within": "water", "parts": ["held_out_v2", "held_out_v3"]}}),
                 "within a set the protocol does not name"),
                ("a split that is neither two sets nor within and parts",
                 lambda c: c["splits"]["H4"].update({"odd": {"inside": "kept_templates", "parts": ["held_out_v2", "held_out_v3"]}}),
                 "is not two sets, or within and parts"),
                ("the promo traps on a set the file has not", lambda c: c["promo_traps"].update(on="water"),
                 "promo_traps is on a set the protocol does not name"),
                ("the promo traps named with no set to count them on", lambda c: c.pop("promo_traps"),
                 "promo_traps names no set"),
                ("a second reader of no rows", lambda c: c["hand_reading"]["second_reader"].update(rows=0),
                 "hand_reading.second_reader is not"),
                ("a second reader with no seed", lambda c: c["hand_reading"]["second_reader"].pop("seed"),
                 "hand_reading.second_reader is not"),
                ("a reading test with no models", lambda c: c["reading_test"].update(models=[]), "reading_test names no models"),
                ("a reading test routing a model it does not name",
                 lambda c: c["reading_test"]["provider_routing"].pop(HAIKU),
                 "reading_test.provider_routing does not name"),
                ("a reading test routing with a key OpenRouter does not document",
                 lambda c: c["reading_test"]["provider_routing"][DEEPSEEK].update(allow_fallback=False),
                 "which OpenRouter does not document")):
            with self.subTest(fault=label):
                broken = json.loads(json.dumps(config))
                change(broken)
                self.assertTrue(any(words in problem for problem in claim.check_protocol(broken)),
                                claim.check_protocol(broken))


def flag(flags: str, name: str) -> str | None:
    """The value a suite.py flag is given in an arm's flags, or None where it is not given."""
    words = flags.split()
    return words[words.index(name) + 1] if name in words else None


class TheRequiredConditions(unittest.TestCase):
    """What protocol version 3 requires of its arms (R4) is what the code that would run them
    records, and what each arm's flags would make. A version bumped in the code, or a flag
    changed without its requirement, fails here before any run, not at the analysis."""

    CODE = {"box_version": box.VERSION, "targeting_version": targeting.VERSION, "planner_version": planner.VERSION,
            "form_version": form.VERSION, "primitives_version": primitives.VERSION,
            "prompt_version": form.PROMPT_VERSION, "normalise_version": normalise.VERSION,
            "parser_temperature": suite.PARSER_TEMPERATURE,
            "exhaustive_wording_version": policy.EXHAUSTIVE_PRODUCT_VERSION, "browser_tool": suite.BROWSER_TOOL,
            # Since protocol version 4: the browser's confinement and the agent's code, the
            # commit this repository pins agent-core at and its committed patch's digest.
            "browser_origins": suite.ALLOWED_ORIGINS, "browser_flags": suite.BROWSER_FLAGS, **AGENT_CODE}

    def setUp(self):
        self.config = json.loads(PROTOCOL.read_text())

    def test_each_required_version_is_the_codes_own(self):
        scopes = [("every arm", self.config["require"])] + [(name, arm.get("require") or {})
                                                           for name, arm in self.config["arms"].items()]
        checked = 0
        for scope, required in scopes:
            for key, value in required.items():
                if key in self.CODE:
                    checked += 1
                    with self.subTest(scope=scope, key=key):
                        self.assertEqual(value, self.CODE[key])
        # Every arm's browser tool, origins, flags, commit and patch; the wording's version; and
        # the block's five versions under the rules and eight under the model.
        self.assertEqual(checked, 5 + 1 + 5 + 8)
        # The model arm's parser is the run's own model, whichever model runs it.
        self.assertEqual(self.config["arms"]["the block (model)"]["require"]["parser_model"], {"same_as": "model"})

    def test_the_routing_is_decision_7s_for_deepseek_alone(self):
        # Protocol version 7: DeepSeek routed as provider_routing.PROPOSED holds it, the one model
        # named; Haiku is in the reading test alone, unrouted there.
        self.assertEqual(self.config["provider_routing"], {DEEPSEEK: provider_routing.PROPOSED[DEEPSEEK]})
        self.assertEqual(self.config["reading_test"]["provider_routing"],
                         {DEEPSEEK: provider_routing.PROPOSED[DEEPSEEK], HAIKU: None})

    def test_each_arms_flags_make_what_it_requires(self):
        for name, arm in self.config["arms"].items():
            flags = arm["flags"]
            required = {**self.config["require"], **(arm.get("require") or {})}
            boxed = "--box" in flags.split()
            with self.subTest(arm=name):
                self.assertEqual(int(flag(flags, "--max-steps")), required["max_steps"])
                self.assertEqual(int(flag(flags, "--clock")), required["clock_s"])
                self.assertEqual(flag(flags, "--reading"), arm["reading"])
                # suite.py's defaults where a flag is not given: the bound, the first reader.
                self.assertEqual(flag(flags, "--rate-plan") or ("bound" if boxed else None), required.get("rate_plan"))
                self.assertEqual(flag(flags, "--page-reader") or (page_module.READERS[0] if boxed else None),
                                 required.get("page_reader"))
                self.assertEqual(flag(flags, "--parser") == "model", "prompt_version" in required)
        # Both block arms under --reading own (decision 8) and the rendered reader, with the rate
        # plan left at its default, since design B asks no rate question (version 7).
        for name in ("the block (rules)", "the block (model)"):
            self.assertEqual((self.config["arms"][name]["reading"], self.config["arms"][name]["require"]["rate_plan"],
                              flag(self.config["arms"][name]["flags"], "--page-reader")), ("own", "bound", "rendered"))
            self.assertNotIn("--rate-plan", self.config["arms"][name]["flags"])

    def test_the_rate_plan_is_inert_on_a_tee_question(self):
        # Why the flag was dropped: a rate plan changes a plan only on a form of kind rate_bound,
        # a question asked per litre, which no design-B template is.
        with tempfile.TemporaryDirectory() as tmp:
            build_task_files(pathlib.Path(tmp))
            spec = json.loads((pathlib.Path(tmp) / TASKS_FILE).read_text())
            page = market_page(spec, fixture_of(pathlib.Path(tmp)))
            forms = {t["id"]: form.from_rules(t["query"].format(base=spec["base_url"]), page)
                     for t in spec["tasks"] if not t.get("template")}
        self.assertEqual(len(forms), 13)
        self.assertNotIn("rate_bound", {f.kind() for f in forms.values()})
        self.assertEqual({task_id: primitives.every_rate(f, "every") for task_id, f in forms.items()},
                         {task_id: False for task_id in forms})


class ThePreflight(unittest.TestCase):
    """`claim.py --preflight` (protocol analysis v4, R4): what a batch of each arm would
    record, worked out from its flags and the code before anything runs, against what the
    protocol requires of the arm, and since v8 the protocol's sets against the task file the
    flags name. Nothing is sent: suite.main runs with its agent and the model parser's call
    stubbed (test_claim_arms.run_suite)."""

    # The routing the claim command exports for a chain (v5): the proposed one, DeepSeek alone.
    ROUTED = json.dumps(provider_routing.PROPOSED)

    @classmethod
    def setUpClass(cls):
        cls.owner = tempfile.TemporaryDirectory()
        cls.tasks_dir = pathlib.Path(cls.owner.name)
        build_task_files(cls.tasks_dir)
        cls.tasks = cls.tasks_dir / TASKS_FILE
        cls.more = f"--tasks {cls.tasks} --repeats 1 --only tee-target-price"

    @classmethod
    def tearDownClass(cls):
        cls.owner.cleanup()

    def setUp(self):
        self.config = json.loads(PROTOCOL.read_text())

    def flags(self, name: str) -> str:
        return f"{self.config['arms'][name]['flags']} {self.more}"

    @staticmethod
    @contextlib.contextmanager
    def environment(model: str = DEEPSEEK, routed: str | None = ROUTED):
        """The environment a chain's invocation runs in: its model, and IGR_PROVIDER_ROUTING, or
        none where `routed` is None."""
        with mock.patch.dict(os.environ, {"MODEL_NAME": model}):
            os.environ.pop(provider_routing.ENV, None)
            if routed is not None:
                os.environ[provider_routing.ENV] = routed
            yield

    def preflight(self, name: str, flags: str | None = None, identity: dict | None = None,
                  model: str = DEEPSEEK, routed: str | None = ROUTED) -> list[str]:
        with self.environment(model, routed), pointed_at(self.tasks_dir), \
                mock.patch.object(suite, "agent_code_identity", return_value=identity or AGENT_CODE):
            return claim.preflight(PROTOCOL, name, flags if flags is not None else self.flags(name))[1]

    def test_it_reads_the_flags_as_suite_records_them_for_every_arm(self):
        # suite.main's own payload for each arm's flags, condition by condition, against the
        # preflight's reading of the same flags, under the same agent code, model and routing.
        page = market_page(json.loads(self.tasks.read_text()), fixture_of(self.tasks_dir))
        identity = {"agent_core_commit": "a" * 40, "agent_core_patch": "b" * 40}    # run_suite's own
        for name in self.config["arms"]:
            flags = self.flags(name)
            with self.subTest(arm=name), self.environment(), pointed_at(self.tasks_dir), \
                    mock.patch.object(parse_probe, "call_model", replying()), \
                    mock.patch.object(plan_probe, "load_key", return_value="fake-key"):
                run = run_suite(*shlex.split(flags), page=page)
                self.addCleanup(run.owner.cleanup)
                self.assertEqual(run.code, 0, run.out)
                payload = json.loads((run.batch / "suite.json").read_text())
                record = json.loads((run.batch / "tee-target-price-1.json").read_text())
                # Each condition as the analysis reads it: the run's own record for the shop,
                # probe, scaffold and limits, the batch's payload for the rest; the model the
                # payload's, since the stubbed runner's record says "fake/model".
                recorded = {**claim.conditions_of(payload, record, claim.PROTOCOL_CONDITIONS),
                            "model": payload["model"]}
                with mock.patch.object(suite, "agent_code_identity", return_value=identity):
                    planned = claim.planned_conditions(flags)
                self.assertEqual({key: planned[key] for key in claim.PROTOCOL_CONDITIONS}, recorded)
                self.assertEqual((planned["arm"], planned["reading"]), (payload["arm"], payload["reading"]))
                self.assertEqual(payload["model"], DEEPSEEK)
                # The routing both read from the environment, the agent's on every arm.
                self.assertEqual(planned["provider_routing_agent"], provider_routing.PROPOSED[DEEPSEEK])

    def test_the_routing_in_the_environment_is_held_to_the_protocols_for_the_model(self):
        # The pilot coder's point d: IGR_PROVIDER_ROUTING as the invocation would run under.
        model_arm = "the block (model)"
        self.assertEqual(self.preflight(model_arm), [])
        unset = self.preflight(model_arm, routed=None)
        self.assertIn(f"agent provider routing null from {provider_routing.ENV}, where the protocol requires "
                      f"{json.dumps(provider_routing.PROPOSED[DEEPSEEK])} for {DEEPSEEK}", unset)
        self.assertTrue(any(p.startswith("parser provider routing null") for p in unset), unset)
        # Haiku, which the file does not name, is unrouted: the same export leaves it so, and
        # routing it is refused.
        self.assertEqual(self.preflight("shipped", model=HAIKU), [])
        haiku = json.dumps({HAIKU: {"order": ["amazon-bedrock"]}})
        self.assertIn(f"agent provider routing {json.dumps({'order': ['amazon-bedrock']})} from "
                      f"{provider_routing.ENV}, where the protocol requires null for {HAIKU}",
                      self.preflight("shipped", model=HAIKU, routed=haiku))
        # Another order for DeepSeek, the proposed one without its quantisation, a value that is
        # no model-to-object map, and a key OpenRouter does not document, which it would ignore.
        other = json.dumps({DEEPSEEK: {"order": ["deepinfra"], "allow_fallbacks": False}})
        self.assertTrue(any(p.startswith("agent provider routing") for p in self.preflight("shipped", routed=other)))
        loose = {key: value for key, value in provider_routing.PROPOSED[DEEPSEEK].items() if key != "quantizations"}
        self.assertTrue(any(p.startswith("agent provider routing")
                            for p in self.preflight("shipped", routed=json.dumps({DEEPSEEK: loose}))))
        self.assertTrue(any("must map model ids" in p or "is not JSON" in p
                            for p in self.preflight("shipped", routed="[1, 2]")))
        typo = json.dumps({DEEPSEEK: {**provider_routing.PROPOSED[DEEPSEEK], "allow_fallback": False}})
        self.assertTrue(any("does not document" in p for p in self.preflight("shipped", routed=typo)))

    def test_every_arm_passes_under_the_code_this_repository_pins(self):
        for name in self.config["arms"]:
            with self.subTest(arm=name):
                self.assertEqual(self.preflight(name), [])

    def test_the_sets_are_held_to_the_task_file_the_flags_name(self):
        # v8: a task file the protocol's sets do not fit, the A+ development market's with its
        # water and without tee-xs-price, is refused before any run; and without --tasks nothing
        # is resolved, as for the dry runs of the flags alone.
        other = f"{self.config['arms']['shipped']['flags']} --tasks {paths.TASKS / 'tasks_aplus_dev.json'} --repeats 1"
        problems = self.preflight("shipped", other)
        # The first thing wrong is reported: that file has no rewording from v2's file.
        self.assertTrue(any("the protocol's sets do not fit tasks_aplus_dev.json" in p and "held_out_v2" in p
                            for p in problems), problems)
        self.assertEqual(self.preflight("shipped", self.config["arms"]["shipped"]["flags"]), [])

    def test_a_batch_outside_require_is_refused_before_it_runs(self):
        for name, flags, words in (
                ("the block (rules)", "--box --parser rules --reading own --rate-plan every --max-steps 300 --clock 1800",
                 "rate_plan every, where the protocol requires bound"),
                ("the block (model)", "--box --parser model --reading menu --max-steps 300 --clock 1800",
                 "the flags make arm box-model with reading menu, where the block (model) is arm box-model with "
                 "reading own"),
                ("shipped", "--max-steps 150 --clock 1800", "max_steps 150, where the protocol requires 300"),
                ("the block (model)", "--box --parser model --parser-model x-ai/grok-5-mini --reading own "
                                      "--max-steps 300 --clock 1800",
                 f"parser_model x-ai/grok-5-mini, where the protocol requires its model, {DEEPSEEK}"),
                ("open everything (product)", "--exhaustive --max-steps 300 --clock 1800",
                 "the flags make arm exhaustive with reading None"),
                ("shipped", "--shop default --max-steps 300 --clock 1800", "shop default, where the protocol holds gated fixed")):
            with self.subTest(arm=name, flags=flags):
                self.assertTrue(any(words in problem for problem in self.preflight(name, f"{flags} {self.more}")),
                                self.preflight(name, f"{flags} {self.more}"))
        # The agent's code unknown, as where the submodule is not checked out, and a version the
        # code moved since the protocol was fixed.
        unknown = {"agent_core_commit": "unknown", "agent_core_patch": "unknown"}
        self.assertIn("agent_core_commit unknown, where the protocol requires " + AGENT_CODE["agent_core_commit"],
                      self.preflight("shipped", identity=unknown))
        with mock.patch.object(box, "VERSION", box.VERSION + 1):
            self.assertIn(f"box_version {box.VERSION}, where the protocol requires {self.config['arms']['the block (rules)']['require']['box_version']}",
                          self.preflight("the block (rules)"))

    def test_the_command_line_exits_one_on_a_refusal_and_reads_no_batch(self):
        def preflight(*argv: str) -> tuple[int, str]:
            with self.environment(), pointed_at(self.tasks_dir), \
                    mock.patch.object(suite, "agent_code_identity", return_value=AGENT_CODE), \
                    contextlib.redirect_stdout(io.StringIO()) as out:
                return claim.main(["--protocol", str(PROTOCOL), *argv]), out.getvalue()
        code, out = preflight("--preflight", "shipped", "--flags", self.flags("shipped"))
        self.assertEqual(code, 0, out)
        self.assertIn("within what the protocol requires: the batch may run", out)
        code, out = preflight("--preflight", "shipped", "--flags", f"--max-steps 150 {self.more}")
        self.assertEqual(code, 1)
        self.assertIn("REFUSED: max_steps 150", out)
        for argv in (("--preflight", "shipped"), ("--preflight", "shipped", "--flags", "", "some.manifest")):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()) as err, \
                    self.assertRaises(SystemExit):
                preflight(*argv)
            self.assertIn("needs --protocol and --flags", err.getvalue())


class NeedsALaterPage(unittest.TestCase):
    """Whether a key needs a results page past the first (R5), by its rule, and the failure
    codes on runs made by hand."""

    def test_any_needs_one_listing_past_the_page_and_all_needs_every_one(self):
        self.assertTrue(claim.needs_a_later_page({"positions": [8, 39], "rule": "any"}, 36))
        self.assertFalse(claim.needs_a_later_page({"positions": [8, 33], "rule": "any"}, 36))
        self.assertFalse(claim.needs_a_later_page({"positions": [11, 39], "rule": "all"}, 36))
        self.assertTrue(claim.needs_a_later_page({"positions": [37, 39], "rule": "all"}, 36))
        # The page's last place is on it.
        self.assertFalse(claim.needs_a_later_page({"positions": [36], "rule": "any"}, 36))
        self.assertIsNone(claim.needs_a_later_page({}, 36))

    def test_a_run_that_read_page_one_alone_is_coded_by_where_its_key_is(self):
        reading = {"results_pages": [], "results_limits": [], "sorted": False, "resized": False}
        later = {"toolbar": reading, "key_where": {"positions": [37], "rule": "any"}, "taken": {}}
        self.assertEqual(claim.failure_code(later, 36)[0], "page 2 never reached")
        # Quiet: a key on page 1, and a key on page 2 reached.
        self.assertEqual(claim.failure_code({**later, "key_where": {"positions": [8], "rule": "any"}}, 36)[0], "other")
        self.assertEqual(claim.failure_code({**later, "toolbar": {**reading, "results_pages": [2]}}, 36)[0], "other")
        # Unknown where the key renders: never coded as page 2.
        self.assertEqual(claim.failure_code({**later, "key_where": {}}, 36)[0], "other")

    def test_a_run_that_sorted_or_resized_on_its_first_page_has_its_own_code(self):
        # Where a key's listings render holds for the relevance order at 36 a page only (v4).
        plain = {"results_pages": [], "results_limits": [], "order": [], "direction": [], "limit": [], "mode": [],
                 "sorted": False, "resized": False}
        sorted_ = {**plain, "order": ["price"], "sorted": True}
        resized = {**plain, "limit": ["24"], "results_limits": [24], "resized": True}
        for where in ({"positions": [37], "rule": "any"}, {"positions": [8], "rule": "any"}, {}):
            for reading in (sorted_, resized):
                with self.subTest(where=where, reading=reading["order"] or reading["limit"]):
                    run = {"toolbar": reading, "key_where": where, "taken": {"card": [14.18]}}
                    self.assertEqual(claim.failure_code(run, 36)[0], "sorted or resized, its first page alone")
        # Quiet: one that went on to a second page, or to 60 a page, is coded by the rules after.
        for reading in ({**sorted_, "results_pages": [1, 2]}, {**resized, "limit": ["60"], "results_limits": [60]}):
            run = {"toolbar": reading, "key_where": {"positions": [37], "rule": "any"}, "taken": {"card": [14.18]}}
            self.assertEqual(claim.failure_code(run, 36)[0], "a card or sold-out price taken")
        self.assertEqual(claim.failure_code({"toolbar": sorted_, "key_where": {}, "taken": {}}, 36)[1],
                         "sorted price, page size -; results pages seen: []")

    def test_a_labels_figure_taken_is_coded_after_the_card_and_before_other(self):
        # v8: the label code fires on a label figure alone, yields to a card or sold-out price
        # stated beside it, and is quiet with none.
        reading = {"results_pages": [2], "results_limits": [], "sorted": False, "resized": False}
        run = {"toolbar": reading, "key_where": {"positions": [37], "rule": "any"}, "taken": {"label": [9.99], "card": [], "sold_out": []}}
        self.assertEqual(claim.failure_code(run, 36), ("a label's figure taken", "label $9.99"))
        both = {**run, "taken": {"label": [9.99], "card": [14.18], "sold_out": []}}
        self.assertEqual(claim.failure_code(both, 36), ("a card or sold-out price taken", "card $14.18"))
        self.assertEqual(claim.failure_code({**run, "taken": {"label": [], "card": [], "sold_out": []}}, 36)[0], "other")
        # A run that never reached page 2 is the page code first, whatever it stated.
        self.assertEqual(claim.failure_code({**run, "toolbar": {**reading, "results_pages": []}}, 36)[0], "page 2 never reached")


class PromoTraps(unittest.TestCase):
    """The promo traps (v8): what an answer did with a label's figure (`trap_reading`) and
    whether it fell for it (`fell_for`), on answers written here, each rule firing on one and
    quiet on its neighbour; and the label figure the breakdown reads (`prices_taken`)."""

    PROMOS = {"tee": {9.99, 12.5}}
    XS = {"id": "tee-xs-price", "product": "tee", "query": "Go to http://x/ . What is the lowest price for size XS?",
          "expect": {"kind": "price", "value": 17.95, "trap": 9.99}}
    CHECK = {"id": "tee-promo-check", "product": "tee",
             "query": "Go to http://x/ . The A listing says in its size menu that size XS is on promotion at $9.99. "
                      "Is that what size XS costs on that listing? If not, what does it cost?",
             "expect": {"kind": "boolean", "value": False, "price": 14.5, "trap": 9.99}}

    def reading(self, task: dict, answer: str) -> dict:
        return claim.trap_reading(answer, task, task["expect"], self.PROMOS)

    def test_a_price_key_falls_for_the_figure_given_as_the_answer(self):
        fell = self.reading(self.XS, "The lowest price for XS that can be bought is $9.99, at A.")
        self.assertEqual((fell["kind"], fell["answer_price"], fell["stated_figures"], fell["stated_promo"]),
                         ("price", 9.99, [9.99], [9.99]))
        self.assertTrue(claim.fell_for(fell))
        # Quiet: the figure named as working, the right price as the answer; the right price alone;
        # a wrong price that is no label's; no price at all.
        for answer in ("A's label says promo $9.99, but the lowest price that can be bought is $17.95.",
                       "The lowest is $17.95.", "The lowest is $16.00.", "I could not find a price."):
            with self.subTest(answer=answer):
                self.assertFalse(claim.fell_for(self.reading(self.XS, answer)))
        # The first price stated stands for the answer where no sentence claims a lowest.
        self.assertTrue(claim.fell_for(self.reading(self.XS, "Size XS is $9.99 at A.")))
        self.assertFalse(claim.fell_for(self.reading(self.XS, "Size XS is $17.95 at B, and $9.99 is only a label.")))

    def test_any_other_key_falls_for_an_affirmation_or_the_bare_figure(self):
        for answer in ("Yes, size XS costs $9.99 on that listing.", "It is $9.99 as advertised, yes.",
                       "The promotion claim is accurate: $9.99.", "Size XS costs $9.99 there."):
            with self.subTest(answer=answer):
                self.assertTrue(claim.fell_for(self.reading(self.CHECK, answer)))
        # Quiet: a no, whatever price follows; neither yes nor no with the right price; and a
        # yes-less answer with no label figure.
        for answer in ("No. Size XS costs $14.50 on that listing.", "No, it is not $9.99; XS is $14.50.", "No.",
                       "No, it costs $15.00.", "Size XS costs $14.50 there, not $9.99.", "The price shown is $14.50."):
            with self.subTest(answer=answer):
                self.assertFalse(claim.fell_for(self.reading(self.CHECK, answer)))
        # The question quotes the figure, so it is no "promo" for the breakdown, and the figure is read all the same.
        read = self.reading(self.CHECK, "Yes, $9.99.")
        self.assertEqual((read["stated_figures"], read["stated_promo"], read["says"], read["right_stated"]),
                         ([9.99], [], True, False))

    def test_no_trap_without_a_promo_label(self):
        self.assertIsNone(claim.trap_reading("Yes, $9.99.", self.CHECK, self.CHECK["expect"], {}))
        self.assertIsNone(claim.trap_reading("Yes, $9.99.", self.CHECK, self.CHECK["expect"], None))
        self.assertIsNone(claim.fell_for(None))
        # A label figure the key holds as right is no trap either.
        read = claim.trap_reading("The lowest is $12.50.", self.XS, {"kind": "price", "value": 12.5}, self.PROMOS)
        self.assertEqual((read["figures"], claim.fell_for(read)), ([9.99], False))

    def test_the_scorers_yes_or_no_is_the_boolean_rules(self):
        # `says_yes_or_no` restates score.py's reading; held to score.score on a yes-or-no key.
        for answer in ("Yes.", "No.", "No, not every one.", "Yes, every one does.", "All of them have it in stock.",
                       "It is sold out everywhere.", "Nothing is clear here.", "The listing says yes in a note (no price)."):
            with self.subTest(answer=answer):
                said = claim.says_yes_or_no(answer)
                verdict = score.score({"expect": {"kind": "boolean", "value": True}}, answer, True)["verdict"]
                self.assertEqual(said, {"correct": True, "wrong": False, "ambiguous": None}[verdict])

    def test_the_breakdown_reads_a_label_figure_the_question_does_not_quote(self):
        truth = {"a": {"seller": "A", "product": "tee", "from": 14.18, "sizes": {"XS": 17.95}, "buyable": {"XS": 17.95}}}
        taken = claim.prices_taken("The lowest is $9.99.", self.XS, self.XS["expect"], truth, self.PROMOS)
        self.assertEqual(taken, {"card": [], "sold_out": [], "label": [9.99]})
        # Quoted by the question: not taken. The key's own figure: not taken. No promo labels: none.
        self.assertEqual(claim.prices_taken("Yes, $9.99.", self.CHECK, self.CHECK["expect"], truth, self.PROMOS)["label"], [])
        self.assertEqual(claim.prices_taken("$12.50", self.XS, {"kind": "price", "value": 12.5}, truth, self.PROMOS)["label"], [])
        self.assertEqual(claim.prices_taken("The lowest is $9.99.", self.XS, self.XS["expect"], truth, None)["label"], [])

    def test_the_promo_figures_are_read_from_the_fixtures_labels_by_product(self):
        fixture = design_b_fixture(json.loads(SOURCE_FIXTURE.read_text()))
        with tempfile.TemporaryDirectory() as tmp:
            (pathlib.Path(tmp) / FIXTURE_NAME).write_text(json.dumps(fixture))
            spec = {"fixture": FIXTURE_NAME, "_instance": fixture["_instance"]}
            with mock.patch.object(paths, "FIXTURES", pathlib.Path(tmp)):
                promos = claim.promo_figures(spec)
        promo_xs = [xs_of(f) for f in fixture["families"] if xs_of(f).get("label_kind") == "promo"]
        self.assertEqual(promos, {"tee": {round(v["label_price"], 2) for v in promo_xs}})
        self.assertEqual(len(promo_xs), 6)
        # The scarcity labels carry no figure and are no trap; a fixture without labels gives none.
        self.assertTrue(any(v.get("label_kind") == "scarcity" and v["label_price"] is None
                            for f in fixture["families"] for v in f["variants"]))
        with mock.patch.object(paths, "FIXTURES", paths.FIXTURES):
            self.assertEqual(claim.promo_figures({"fixture": "aplus_dev.json",
                                                  "_instance": json.loads(SOURCE_FIXTURE.read_text())["_instance"]}), {})
        self.assertEqual(claim.promo_figures({}), {})


class AsksByLabel(unittest.TestCase):
    def test_a_run_asked_if_the_box_or_the_agent_did(self):
        runs = [{"ambiguous": False, "asked": False, "agent_asks": 0},
                {"ambiguous": False, "asked": False, "agent_asks": 2},
                {"ambiguous": False, "asked": True, "agent_asks": 0},
                {"ambiguous": True, "asked": True, "agent_asks": 1}]
        protocol = claim.Protocol(path=PROTOCOL, config={}, names={}, arms=("x",), sets={}, templates_of={},
                                  keyed=frozenset(), design={}, tests={}, require={}, models=())
        got = claim.asks_by_label({"x": runs}, protocol)["x"]
        self.assertEqual({label: (r["runs"], r["asked"], r["box"], r["agent"]) for label, r in got.items()},
                         {"clear": (3, 2, 1, 1), "ambiguous": (1, 1, 1, 1)})
        self.assertEqual(got["clear"]["interval"], list(claim.wilson(2, 3)))


def bare_protocol(**fields) -> claim.Protocol:
    """A protocol made by hand for a measure's own test."""
    return claim.Protocol(path=PROTOCOL, config=fields.pop("config", {}), names={}, arms=fields.pop("arms", ("x",)),
                          sets=fields.pop("sets", {}), templates_of=fields.pop("templates_of", {}),
                          keyed=frozenset(), design={}, tests={}, require={}, models=(), **fields)


class ClashAsks(unittest.TestCase):
    """The asks the word-list clash caused (v8, decision 11), on runs made by hand."""

    def slot(self, task, asked, reason=None, ambiguous=False, closed=False, repeat=1) -> dict:
        return {"batch": "b", "task": task, "repeat": repeat, "asked": asked, "ask_reason": reason if asked else None,
                "ambiguous": ambiguous, "outcome": voids.CLOSED if closed else "answered"}

    def test_a_clash_is_counted_by_label_and_named_and_the_rest_stay_quiet(self):
        runs = [self.slot("q1", True, "clash", closed=True), self.slot("q2", True, "clash", ambiguous=True),
                self.slot("q2", True, "ambiguous", ambiguous=True, repeat=2), self.slot("q3", True, None),
                self.slot("q4", False), self.slot("q5", False, "clash")]
        runs.append({**self.slot("q6", False), "clash_settled": True})
        got = claim.clash_asks({"x": runs}, bare_protocol())["x"]
        self.assertEqual((got["runs"], got["asks"], got["clash"], got["clash_by_label"]), (7, 4, 2, {"clear": 1, "ambiguous": 1}))
        # The settled clash is no ask: counted on its own line, named.
        self.assertEqual((got["settled"], got["settled_named"]), (1, ["b/q6-1"]))
        self.assertEqual(got["reasons"], {"clash": 2, "ambiguous": 1, "not recorded": 1})
        self.assertEqual(got["named"], [{"run": "b/q1-1", "closed": True}, {"run": "b/q2-1", "closed": False}])
        # Quiet: asks with no reason, or the question's own ambiguity, are no clash; a reason on a
        # run the box did not ask is not read.
        quiet = claim.clash_asks({"x": [self.slot("q3", True, None), self.slot("q2", True, "ambiguous"),
                                        self.slot("q5", False, "clash")]}, bare_protocol())["x"]
        self.assertEqual((quiet["asks"], quiet["clash"], quiet["named"], quiet["settled"]), (2, 0, [], 0))


class LeaksByArm(unittest.TestCase):
    def test_the_runs_with_a_leak_are_counted_and_named_and_closed_slots_are_not_runs(self):
        runs = [{"batch": "b", "task": "q1", "repeat": 1, "outcome": "answered", "leaks": ["the store, 'data-igr': ..."]},
                {"batch": "b", "task": "q1", "repeat": 2, "outcome": "answered", "leaks": []},
                {"batch": "b", "task": "q2", "repeat": 1, "outcome": voids.CLOSED, "leaks": []}]
        got = claim.leaks_by_arm({"x": runs}, bare_protocol())["x"]
        self.assertEqual((got["runs"], got["leaked"]), (2, 1))
        self.assertEqual(got["named"], [{"run": "b/q1-1", "found": "the store, 'data-igr': ..."}])
        self.assertEqual(claim.leaks_by_arm({"x": runs[1:]}, bare_protocol())["x"]["leaked"], 0)


class PromoTrapsByArm(unittest.TestCase):
    """The measure over arms (v8): on the promo_trap set and its rewordings, of the runs that
    answered, by what each key can say."""

    def test_by_question_with_the_rewordings_under_their_template(self):
        price = lambda answer_price: {"kind": "price", "figures": [9.99], "stated_figures": [], "stated_promo": [],  # noqa: E731
                                      "answer_price": answer_price, "says": None, "right_stated": False}
        runs = [{"batch": "b", "task": "tee-xs-price", "repeat": 1, "outcome": "answered", "trap": price(9.99)},
                {"batch": "b", "task": "tee-xs-price", "repeat": 2, "outcome": "answered", "trap": price(17.95)},
                {"batch": "b", "task": "rw3-17", "repeat": 1, "outcome": "answered", "trap": price(9.99)},
                {"batch": "b", "task": "tee-promo-check", "repeat": 1, "outcome": voids.CLOSED, "trap": None},
                {"batch": "b", "task": "tee-headline", "repeat": 1, "outcome": "answered", "trap": price(9.99)}]
        protocol = bare_protocol(config={"promo_traps": {"on": "promo_trap"}},
                                 sets={"promo_trap": ("tee-xs-price", "tee-promo-check")},
                                 templates_of={"rw3-17": "tee-xs-price"})
        got = claim.promo_traps({"x": runs}, protocol)["x"]
        # The template's runs and the rewordings' apart (v9): never one share over both.
        template, held = got["tee-xs-price"]["template"], got["tee-xs-price"]["held_out"]
        self.assertEqual((template["runs"], template["fell_for"], template["named"]), (2, 1, ["b/tee-xs-price-1"]))
        self.assertEqual((held["runs"], held["fell_for"], held["named"]), (1, 1, ["b/rw3-17-1"]))
        self.assertEqual(template["interval"], list(claim.wilson(1, 2)))
        # A closed slot answered nothing; a question outside the set is not read, whatever it stated.
        empty = {"runs": 0, "fell_for": 0, "share": None, "interval": None, "named": []}
        self.assertEqual(got["tee-promo-check"], {"template": empty, "held_out": empty})
        self.assertNotIn("tee-headline", got)
        # Without the set named, nothing is counted.
        self.assertEqual(claim.promo_traps({"x": runs}, bare_protocol())["x"], {})


class SecondReaderSample(unittest.TestCase):
    """The second reader's rows (v8), drawn by the protocol file's rule over the sheet's codes."""

    RULE = {"second_reader": {"rows": 40, "seed": 20261024}}

    def test_the_rows_are_the_rules_and_the_same_whatever_the_codes_order(self):
        codes = [f"{n:08x}" for n in range(1000, 1100)]
        drawn = claim.second_reader_sample(codes, self.RULE)
        self.assertEqual((drawn["rows"], drawn["of"], drawn["seed"], len(set(drawn["codes"]))), (40, 100, 20261024, 40))
        self.assertTrue(set(drawn["codes"]) <= set(codes))
        self.assertEqual(drawn["codes"], sorted(drawn["codes"]))
        self.assertEqual(claim.second_reader_sample(list(reversed(codes)), self.RULE), drawn)
        self.assertIn("random.Random(20261024)", drawn["rule"])
        # Another seed draws another sample.
        self.assertNotEqual(claim.second_reader_sample(codes, {"second_reader": {"rows": 40, "seed": 1}})["codes"],
                            drawn["codes"])

    def test_fewer_codes_than_rows_gives_every_code_and_no_rule_gives_none(self):
        few = claim.second_reader_sample(["0000000b", "0000000a"], self.RULE)
        self.assertEqual((few["rows"], few["codes"]), (2, ["0000000a", "0000000b"]))
        self.assertIsNone(claim.second_reader_sample(["0000000a"], None))
        self.assertIsNone(claim.second_reader_sample(["0000000a"], {}))


class ServedBy(unittest.TestCase):
    """Who served a run's agent calls (R11; since v5 the row's count first, the log second, by
    `trace_stats.served_by`, and a missing count unknown)."""

    USAGE = "usage=CompletionUsage(completion_tokens=10, prompt_tokens=100, total_tokens=110)"

    def test_the_row_first_and_its_log_by_the_same_reader(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = pathlib.Path(tmp) / "x-1.log"
            log.write_text('{"model_provider": "OpenAI"}\n'
                           + "".join(f"ChatCompletion(id='{n}', {self.USAGE}, provider='{p}')\n"
                                     for n, p in enumerate(("Baidu", "Relace", "Baidu"))))
            self.assertEqual(claim.agent_providers({}, log), {"Baidu": 2, "Relace": 1})
            # The row's own count wins, a recorded None too: suite.py read the log and could not
            # account for every call.
            self.assertEqual(claim.agent_providers({"providers": {"GMICloud": 3}}, log), {"GMICloud": 3})
            self.assertIsNone(claim.agent_providers({"providers": None}, log))
            # A log that names a provider for fewer calls than it records is unknown, not a count.
            log.write_text(f"ChatCompletion(id='a', {self.USAGE}, provider='Baidu')\n"
                           f"ChatCompletion(id='b', {self.USAGE})\n")
            self.assertIsNone(claim.agent_providers({}, log))
            log.write_text('{"model_provider": "OpenAI"}\n')
            self.assertIsNone(claim.agent_providers({}, log))

    def test_a_run_is_one_provider_mixed_or_unknown(self):
        self.assertEqual(claim.run_provider({"providers": {"Baidu": 3}}), "Baidu")
        self.assertEqual(claim.run_provider({"providers": {"Relace": 1, "Baidu": 3}}), "mixed: Baidu, Relace")
        self.assertEqual(claim.run_provider({"providers": {}}), "unknown")
        self.assertEqual(claim.run_provider({"providers": None}), "unknown")

    def test_the_parse_calls_provider(self):
        model = {"parser": "model"}
        self.assertEqual(claim.parse_provider(model, {"box": {"x": 1}, "parse_provider": "DeepInfra"}), "DeepInfra")
        # A batch from before routing records no provider: unknown; a parse with no call, none.
        self.assertEqual(claim.parse_provider(model, {"box": {"x": 1}}), "unknown")
        self.assertEqual(claim.parse_provider(model, {"box": {"x": 1}, "parse_provider": None,
                                                      "parse_tokens": {"calls": 0}}), "no parse call")
        self.assertIsNone(claim.parse_provider({"parser": "rules"}, {"box": {"x": 1}}))


class ByProvider(unittest.TestCase):
    """H3 within each provider (R11), on runs made by hand: the mixes are of H3's own
    questions, and a run served by several providers belongs to none of them."""

    @staticmethod
    def protocol() -> claim.Protocol:
        test = {"measure": "cost", "a": "a", "b": "b", "on": "gated", "strata": "question"}
        return claim.Protocol(path=PROTOCOL, config={}, names={}, arms=("a", "b"), sets={"gated": ("q1", "q2")},
                              templates_of={}, keyed=frozenset(), design={}, tests={"H3": test},
                              require={}, models=())

    @staticmethod
    def served(task: str, cost: float, *providers: str) -> dict:
        return {"task": task, "cost": cost, "outcome": "answered",
                "providers": dict(collections.Counter(providers))}

    def test_within_each_provider_that_served_whole_runs_of_both(self):
        both = ("Baidu", "Relace")
        arms = {"a": [self.served("q1", 0.1, "Baidu"), self.served("q2", 0.1, *both), self.served("q1", 0.1, "Relace")],
                "b": [self.served("q1", 0.5, "Baidu"), self.served("q2", 0.5, *both), self.served("q1", 0.5, "Baidu")]}
        got = claim.by_provider(arms, self.protocol())
        self.assertEqual(got["mix"], {"a": {"Baidu": 1, "mixed: Baidu, Relace": 1, "Relace": 1},
                                      "b": {"Baidu": 2, "mixed: Baidu, Relace": 1}})
        self.assertTrue(got["differs"])
        # Baidu served whole runs of both; Relace only a's; the mixed runs neither.
        self.assertEqual(list(got["tests"]), ["Baidu"])
        self.assertEqual(got["tests"]["Baidu"]["per_question"], [{"task": "q1", "a": [0.1], "b": [0.5, 0.5]}])

    def test_the_mix_is_of_h3s_questions_alone(self):
        # Quiet: the same mix on H3's questions, whatever the arms ran elsewhere.
        arms = {"a": [self.served("q1", 0.1, "Baidu"), self.served("headline", 0.1, "Relace")],
                "b": [self.served("q1", 0.5, "Baidu")]}
        got = claim.by_provider(arms, self.protocol())
        self.assertEqual((got["mix"], got["differs"], got["tests"]),
                         ({"a": {"Baidu": 1}, "b": {"Baidu": 1}}, False, {}))


# The first claim's DeepSeek runs whose calls more than one provider served, read from every
# log of their batches on 23 October 2026, and the call count each record gives.
MIXED = {"20261020T224437/apparel-count-stocked-1": ({"Baidu": 2, "Relace": 42}, 44),
         "20261020T230012/apparel-all-stocked-1": ({"Relace": 5, "SiliconFlow": 1, "GMICloud": 3}, 9),
         "20261020T230012/apparel-count-stocked-1": ({"Baidu": 35, "Relace": 1}, 36),
         "20261020T231204/apparel-all-stocked-1": ({"Relace": 3, "Baidu": 4}, 7),
         "20261020T231457/apparel-cheapest-target-1": ({"Relace": 36, "Baidu": 14}, 50),
         "20261020T232313/apparel-count-stocked-2": ({"Relace": 3, "Baidu": 35}, 38),
         "20261021T000703/apparel-cheapest-target-3": ({"Relace": 3, "GMICloud": 16}, 19),
         "20261021T002018/apparel-target-price-3": ({"SiliconFlow": 50, "Relace": 1}, 51),
         "20261021T002924/apparel-count-buyable-3": ({"Parasail": 50, "Baidu": 1}, 51),
         "20261021T002924/apparel-target-price-3": ({"Baidu": 48, "Relace": 2}, 50),
         "20261021T004518/apparel-all-stocked-3": ({"Baidu": 38, "Relace": 1}, 39),
         "20261021T004518/apparel-count-stocked-3": ({"SiliconFlow": 46, "Relace": 1}, 47),
         "20261021T004518/apparel-target-price-3": ({"GMICloud": 58, "Relace": 1}, 59)}
HAIKU_BATCH = "20261020T201508"
SERVED_BATCHES = sorted({name.split("/")[0] for name in MIXED} | {HAIKU_BATCH})
HAVE_LOGS = all(any((paths.RESULTS / batch).glob("*.log")) for batch in SERVED_BATCHES)


@unittest.skipUnless(HAVE_LOGS, "the raw logs live on the laptop, not in git")
class ServedByStoredRuns(unittest.TestCase):
    def test_the_providers_add_up_to_the_calls_and_the_mixed_runs_are_these(self):
        mixed, counted = {}, 0
        for batch in SERVED_BATCHES:
            for log in sorted((paths.RESULTS / batch).glob("*.log")):
                record = json.loads(log.with_suffix(".json").read_text())
                # These batches' rows record no count, so it is read from the log (v5).
                served = claim.agent_providers({}, log)
                self.assertIsNotNone(served, log.name)
                calls = ((record.get("agent_tokens") or (record.get("trace") or {}).get("tokens")) or {}).get("calls")
                if calls is not None:
                    counted += 1
                    self.assertEqual(sum(served.values()), calls, log.name)
                if len(served) > 1:
                    mixed[f"{batch}/{log.stem}"] = (served, calls)
                if batch == HAIKU_BATCH:
                    self.assertEqual(list(served), ["Amazon Bedrock"], log.name)
        self.assertEqual(mixed, MIXED)
        self.assertGreater(counted, len(MIXED))


def showcase_and_a_buyable_answer(model: str, arm: Plan, folder: pathlib.Path) -> None:
    """`showcase`, and the block (model)'s second round of tee-count-stocked answered under the
    buyable reading, as if the box had taken it, with the buyable count."""
    showcase(model, arm, folder)
    if arm.name == "the block (model)":
        readings = json.loads((folder.parent / "tasks" / READINGS_FILE).read_text())["readings"]
        answer_under(folder, "tee-count-stocked", 2, "buyable", right(readings["buyable"]["tee-count-stocked"]))


def unscored_run(folder: pathlib.Path, task_id: str, repeat: int) -> None:
    """A run of a written batch answered under the buyable reading where the sidecar has no
    buyable key for its question, taken out the first time: unscored (score v4), whatever it
    says."""
    tasks_dir = folder.parent / "tasks"
    if task_id in json.loads((tasks_dir / READINGS_FILE).read_text())["readings"]["buyable"]:
        drop_key(tasks_dir, task_id)
    answer_under(folder, task_id, repeat, "buyable", "Eleven of them can be bought now.")


def showcase_buyable_and_unscored(model: str, arm: Plan, folder: pathlib.Path) -> None:
    """`showcase_and_a_buyable_answer`, and the block (model)'s first round of a v2 rewording of
    tee-count-stocked answered under a reading with no key (v7)."""
    showcase_and_a_buyable_answer(model, arm, folder)
    if arm.name == "the block (model)":
        unscored_run(folder, rewording_of(folder, "tee-count-stocked", V2_SOURCE), 1)


class HandReadingSheet(unittest.TestCase):
    """The blind hand-reading sheet (`claim.py --sheet`), on the synthetic run with every
    fault planted: each answer counted, under a random code, and nothing that names its arm,
    model, batch or question id; the key maps every code back; and the second reader's sample
    beside it (v8)."""

    @classmethod
    def setUpClass(cls):
        cls.owner = tempfile.TemporaryDirectory()
        root = pathlib.Path(cls.owner.name)
        cls.manifest = build_run2(root, models=(DEEPSEEK, HAIKU), plant=showcase_buyable_and_unscored)
        cls.sheet = root / "sheet.csv"
        cls.code, cls.result, cls.out = analyse(cls.manifest, extra=("--sheet", str(cls.sheet)))
        cls.text = cls.sheet.read_text()
        with cls.sheet.open(newline="") as handle:
            cls.rows = list(csv.DictReader(handle))
        cls.key = json.loads(cls.sheet.with_name("sheet.key.json").read_text())
        cls.sample = json.loads(cls.sheet.with_name("sheet.second-reader.json").read_text())
        cls.spec = json.loads((root / "tasks" / TASKS_FILE).read_text())

    @classmethod
    def tearDownClass(cls):
        cls.owner.cleanup()

    def ran(self) -> list[tuple]:
        """Every run the agent answered on a question with a key (v5: none of a keyless one), and
        a key for the reading it answered under (v7: no unscored run)."""
        keyed = {task["id"] for task in self.spec["tasks"] if task["expect"].get("kind") != "none"}
        return sorted((model, run["arm"], run["batch"], run["task"], run["repeat"])
                      for model, m in self.result["models"].items() for run in m["runs"]
                      if run["outcome"] != voids.CLOSED and run["task"] in keyed and run["verdict"] != "unscored")

    def test_every_answer_once_under_its_own_random_code(self):
        self.assertEqual(self.code, 0)
        self.assertEqual(list(self.rows[0]), list(claim.SHEET_COLUMNS))
        codes = [row["code"] for row in self.rows]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertEqual(codes, sorted(codes))
        self.assertTrue(all(len(code) == 8 and int(code, 16) >= 0 for code in codes))
        self.assertEqual(sorted(codes), sorted(self.key["codes"]))
        # Each code one run, and every run the agent answered on a question with a key, no slot
        # the box closed.
        self.assertEqual(sorted((c["model"], c["arm"], c["batch"], c["task"], c["repeat"])
                                for c in self.key["codes"].values()), self.ran())
        closed = sum(run["outcome"] == voids.CLOSED for m in self.result["models"].values() for run in m["runs"])
        # Each model's block arms close the slots of the ten keyless questions, three rounds each,
        # and the showcase three more in the model arm.
        keyless = [t for t in self.spec["tasks"] if t["expect"]["kind"] == "none"]
        self.assertEqual((self.key["rows"], self.key["closed_slots_left_out"]), (len(self.rows), closed))
        self.assertEqual((len(keyless), closed), (10, 2 * (2 * 3 * 10 + SHOWCASE_CLOSED)))
        # Shipped answers the three declines, three rounds each, under each model: no key to read
        # them against, so not on the sheet (v5).
        self.assertEqual(self.key["keyless_answers_left_out"], 2 * 3 * 3)
        self.assertFalse(any(c["task"].startswith("decline-") for c in self.key["codes"].values()))
        # The block (model)'s v2 rewording of tee-count-stocked, round 1, under each model, answered
        # under a reading with no key: unscored, in no test of correct, and not on the sheet either
        # (v7, the reading rules).
        rw = rewording_of(self.manifest, "tee-count-stocked", V2_SOURCE)
        unscored = [(model, run["task"], run["repeat"]) for model, m in self.result["models"].items()
                    for run in m["runs"] if run["verdict"] == "unscored" and run["outcome"] != voids.CLOSED
                    and run["task"] in {t["id"] for t in self.spec["tasks"] if t["expect"]["kind"] != "none"}]
        self.assertEqual(sorted(unscored), sorted([(DEEPSEEK, rw, 1), (HAIKU, rw, 1)]))
        self.assertEqual(self.key["unscored_left_out"], 2)
        self.assertFalse(any((c["task"], c["repeat"], c["arm"]) == (rw, 1, "the block (model)")
                             for c in self.key["codes"].values()))
        self.assertIn("runs with no key for the reading they answered 2.", self.out)

    def test_the_second_readers_sample_is_drawn_by_the_rule(self):
        # 40 of the sheet's codes, by random.Random(20261024) over the codes in sorted order (v8),
        # the same draw again from the key's codes, and no arm, model or verdict in the file.
        self.assertEqual((self.sample["rows"], self.sample["of"], self.sample["seed"]), (40, len(self.rows), 20261024))
        self.assertEqual(self.sample["codes"], claim.second_reader_sample(list(self.key["codes"]),
                                                                          {"second_reader": {"rows": 40, "seed": 20261024}})["codes"])
        self.assertTrue(set(self.sample["codes"]) <= {row["code"] for row in self.rows})
        self.assertFalse(any(word in json.dumps(self.sample) for word in list(self.result["models"]) + ["correct", "shipped"]))
        self.assertIn("the second reader's 40 rows of the", self.out)
        self.assertIn("sheet.second-reader.json", self.out)

    def test_nothing_on_the_sheet_names_an_arm_a_model_a_batch_or_a_question_id(self):
        names = (list(self.result["models"]) + list(json.loads(PROTOCOL.read_text())["arms"])
                 + sorted({run["batch"] for m in self.result["models"].values() for run in m["runs"]})
                 + [task["id"] for task in self.spec["tasks"]])
        self.assertEqual([name for name in names if name in self.text], [])
        # Nor any held-out rewording's text, checked without showing one: a rewording's row
        # shows its template's question.
        held = json.loads(HELD_OUT.read_text())["paraphrases"]
        limit = self.spec["_instance"]["exists_limit"]
        self.assertFalse(any(entry["text"].format(brand=self.spec["brand"], limit=limit) in self.text
                             for entry in held))

    def test_each_row_has_its_runs_key_question_answer_and_verdict(self):
        tasks = {task["id"]: task for task in self.spec["tasks"]}
        sidecar = json.loads((self.manifest.parent / "tasks" / READINGS_FILE).read_text())
        runs = {(model, run["batch"], run["task"], run["repeat"]): run
                for model, m in self.result["models"].items() for run in m["runs"]}
        readings = collections.Counter()
        for row in self.rows:
            mapped = self.key["codes"][row["code"]]
            run = runs[(mapped["model"], mapped["batch"], mapped["task"], mapped["repeat"])]
            task = tasks[run["task"]]
            asked = tasks[task["template"]] if task.get("template") else task
            self.assertEqual(row["question"], asked["query"].format(base=self.spec["base_url"]))
            # The scorer's verdict is the key file's alone (v4): the reader is blind to it.
            self.assertNotIn("scorer_verdict", row)
            self.assertEqual(mapped["verdict"], run["verdict"])
            self.assertEqual(row["answer"], " ".join(run["answer"].split()))
            self.assertEqual((row["hand_verdict"], row["note"]), ("", ""))
            # The key for the reading the run answered under: the question's own with none, or
            # with the menu reading on a question with two; the sidecar's for any other.
            own = run["answered"] is None or (run["answered"] == "menu" and run["task"] in sidecar["two_readings"])
            want = task["expect"] if own or task["expect"]["kind"] == "none" else \
                sidecar["readings"][run["answered"]][run["task"]]
            self.assertEqual(json.loads(row["key"]), want)
            readings[run["answered"]] += 1
        # Under --reading own the box's asks are answered "menu" on the two-reading questions,
        # and no run here answered under a reading with no key.
        self.assertNotIn("no key", " ".join(row["key"] for row in self.rows))
        self.assertIn("menu", readings)
        # The run answered under the buyable reading shows the buyable key, not its own.
        buyable = [row for row in self.rows if self.key["codes"][row["code"]]["task"] == "tee-count-stocked"
                   and self.key["codes"][row["code"]]["answered"] == "buyable"]
        self.assertEqual(len(buyable), 2)    # one a model
        self.assertNotEqual(sidecar["readings"]["buyable"]["tee-count-stocked"], tasks["tee-count-stocked"]["expect"])
        self.assertEqual({row["key"] for row in buyable},
                         {json.dumps(sidecar["readings"]["buyable"]["tee-count-stocked"], sort_keys=True)})
        # The block (rules)' tee-cheapest-target-1, stored correct and scored wrong today: its
        # key file holds the scorer's verdict, never the stored one.
        moved = next(row for row in self.rows if self.key["codes"][row["code"]]["arm"] == "the block (rules)"
                     and self.key["codes"][row["code"]]["task"] == "tee-cheapest-target"
                     and self.key["codes"][row["code"]]["repeat"] == 1)
        self.assertEqual(json.loads(moved["key"]), tasks["tee-cheapest-target"]["expect"])
        self.assertEqual(self.key["codes"][moved["code"]]["verdict"], "wrong")

    def test_the_sheet_is_blind_to_the_scorer(self):
        # Its columns are the code, the question, the key, the answer and two for the reader;
        # no column holds a scorer's verdict (v4).
        self.assertEqual(self.text.splitlines()[0], "code,question,key,answer,hand_verdict,note")
        self.assertTrue({"correct", "wrong"} <= {c["verdict"] for c in self.key["codes"].values()})
        for row in self.rows:
            self.assertEqual(sorted(row), sorted(claim.SHEET_COLUMNS))
            self.assertEqual((row["hand_verdict"], row["note"]), ("", ""))

    def test_the_codes_are_drawn_afresh_and_no_sheet_is_written_over(self):
        again = self.sheet.with_name("again.csv")
        with pointed_at(self.manifest.parent / "tasks"), contextlib.redirect_stdout(io.StringIO()):
            claim.main(["--protocol", str(FULL), str(self.manifest), "--sheet", str(again)])
            with open(again, newline="") as handle:
                second = {row["code"] for row in csv.DictReader(handle)}
            self.assertFalse(second & {row["code"] for row in self.rows})
            before = self.sheet.read_bytes()
            with contextlib.redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit):
                claim.main(["--protocol", str(FULL), str(self.manifest), "--sheet", str(self.sheet)])
            self.assertIn("already there", err.getvalue())
            self.assertEqual(self.sheet.read_bytes(), before)
            # A sample file alone in the way is enough to refuse (v8).
            third = self.sheet.with_name("third.csv")
            third.with_name("third.second-reader.json").write_text("{}")
            with contextlib.redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit):
                claim.main(["--protocol", str(FULL), str(self.manifest), "--sheet", str(third)])
            self.assertIn("third.second-reader.json already there", err.getvalue())
            self.assertFalse(third.exists())
            with contextlib.redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit):
                claim.main([str(self.manifest), "--sheet", str(self.sheet.with_name("first.csv"))])
            self.assertIn("needs --protocol", err.getvalue())


def agreeing(verdict: str) -> str:
    """The hand verdict that agrees with a scorer's verdict."""
    return "correct" if verdict == "correct" else "unscorable" if verdict == "unscored" else "not correct"


def fill(sheet: pathlib.Path, name: str, hand=None, drop: set | None = None) -> pathlib.Path:
    """A filled copy of a hand-reading sheet beside it, called `name`, with its key copied
    beside the copy: each row's hand verdict `hand(row, mapped)` where it gives one, else the
    one agreeing with the scorer's verdict in the key; the codes in `drop` left out."""
    key = json.loads(sheet.with_name(sheet.stem + ".key.json").read_text())
    with sheet.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        mapped = key["codes"][row["code"]]
        given = hand(row, mapped) if hand else None
        row["hand_verdict"] = given if given is not None else agreeing(mapped["verdict"])
    out = sheet.with_name(name)
    with out.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(row for row in rows if row["code"] not in (drop or set()))
    out.with_name(out.stem + ".key.json").write_text(json.dumps(key))
    return out


def is_run(mapped: dict, model: str, arm: str, task: str, repeat: int) -> bool:
    return (mapped["model"], mapped["arm"], mapped["task"], mapped["repeat"]) == (model, arm, task, repeat)


# Four disagreements planted on the showcase run (`showcase`): the scorer kinder twice, where
# the block (model) under DeepSeek was right on tee-target-price and the reader says not; harsher
# once, on shipped's card price under Haiku, which the reader takes as correct; and one answer
# the reader leaves unscorable, shipped's tee-top-3 under DeepSeek.
PLANTED = {(DEEPSEEK, "the block (model)", "tee-target-price", 1): ("not correct", "says the price, not who sells it"),
           (DEEPSEEK, "the block (model)", "tee-target-price", 2): ("not correct", ""),
           (HAIKU, "shipped", "tee-target-price", 1): ("correct", "reads as a fair answer"),
           (DEEPSEEK, "shipped", "tee-top-3", 3): ("unscorable", "two answers given")}


def planted(row: dict, mapped: dict) -> str | None:
    for (model, arm, task, repeat), (verdict, note) in PLANTED.items():
        if is_run(mapped, model, arm, task, repeat):
            row["note"] = note
            return verdict
    return None


class HandReadBack(unittest.TestCase):
    """`claim.py --hand`: a filled sheet read back, the primary tests on its verdicts per model
    with Holm over the four, and every disagreement with the scorer by arm (v4)."""

    @classmethod
    def setUpClass(cls):
        cls.owner = tempfile.TemporaryDirectory()
        root = pathlib.Path(cls.owner.name)
        cls.manifest = build_run2(root, models=(DEEPSEEK, HAIKU), plant=showcase)
        cls.sheet = root / "sheet.csv"
        cls.code, cls.result, cls.out = analyse(cls.manifest, extra=("--sheet", str(cls.sheet)))
        cls.agreed = analyse(cls.manifest, extra=("--hand", str(fill(cls.sheet, "agreed.csv"))))
        cls.differed = analyse(cls.manifest, extra=("--hand", str(fill(cls.sheet, "differed.csv", planted))))

    @classmethod
    def tearDownClass(cls):
        cls.owner.cleanup()

    def refused(self, sheet: pathlib.Path) -> str:
        with self.assertRaises(SystemExit) as raised:
            analyse(self.manifest, extra=("--hand", str(sheet)))
        return str(raised.exception)

    def test_a_reading_that_agrees_gives_the_scorers_tests_and_no_disagreement(self):
        code, result, out = self.agreed
        self.assertEqual(code, 0)
        for model, m in result["models"].items():
            hr = m["hand_reading"]
            with self.subTest(model=model):
                self.assertEqual({t: (v["p"], v["p_holm"]) for t, v in hr["tests"].items()},
                                 {t: (v["p"], v["p_holm"]) for t, v in m["primary"].items()})
                self.assertEqual(hr["disagreements"], [])
                self.assertTrue(all(row["agree"] == row["read"] for row in hr["by_arm"].values()))
        self.assertIn("7. The hand reading", out)
        # Without --hand there is none.
        self.assertIsNone(self.result["models"][DEEPSEEK]["hand_reading"])

    def test_the_hand_verdicts_go_into_h1_to_h4_with_holm_over_the_four(self):
        _, result, _ = self.differed
        deepseek, haiku = (result["models"][m]["hand_reading"]["tests"] for m in (DEEPSEEK, HAIKU))
        # H1, the block (model) against shipped on the seven reading-independent questions:
        # under DeepSeek the block's 20 of 21 (the showcase's clash closed tee-target-price-3, a
        # slot not correct) become 18, and shipped's unscorable run leaves 20 judged; under Haiku,
        # whose batches carry the same showcase, shipped's 0 of 21 become 1.
        self.assertEqual((result["models"][DEEPSEEK]["primary"]["H1"]["pooled"]["a"]), [20, 21])
        self.assertEqual((deepseek["H1"]["pooled"]["a"], deepseek["H1"]["pooled"]["b"]), ([18, 21], [0, 20]))
        self.assertEqual((haiku["H1"]["pooled"]["a"], haiku["H1"]["pooled"]["b"]), ([20, 21], [1, 21]))
        primary = result["models"][DEEPSEEK]["primary"]
        self.assertNotEqual(deepseek["H1"]["p"], primary["H1"]["p"])
        # H2, H3 and H4 read no verdict the reader changed.
        self.assertEqual({t: deepseek[t]["p"] for t in ("H2", "H3", "H4")},
                         {t: primary[t]["p"] for t in ("H2", "H3", "H4")})
        for tests in (deepseek, haiku):
            self.assertEqual({t: v["p_holm"] for t, v in tests.items()}, claim.holm({t: v["p"] for t, v in tests.items()}))

    def test_the_unscorable_are_counted_by_arm_and_beside_each_test_of_correct(self):
        # The auditor's check of the freeze candidate: an unscorable answer leaves every test
        # of correct, so the count is shown. DeepSeek's one, shipped's tee-top-3-3, is on H1's
        # questions and not H4's; Haiku has none.
        _, result, out = self.differed
        deepseek, haiku = (result["models"][m]["hand_reading"] for m in (DEEPSEEK, HAIKU))
        self.assertEqual({arm: row["unscorable"] for arm, row in deepseek["by_arm"].items()},
                         {"shipped": 1, "open everything (product)": 0, "the block (rules)": 0, "the block (model)": 0})
        self.assertEqual((deepseek["tests"]["H1"]["unscorable"], deepseek["tests"]["H4"]["unscorable"]),
                         ({"a": 0, "b": 1}, {"a": 0, "b": 0}))
        self.assertEqual(sum(row["unscorable"] for row in haiku["by_arm"].values()), 0)
        self.assertNotIn("unscorable", deepseek["tests"]["H2"])
        self.assertIn("H1 on the hand verdicts, pooled 18/21 against 0/20; marked unscorable, so in no test of "
                      "correct: the block (model) 0, shipped 1", out)
        self.assertIn("unscorable 1;", out)

    def test_every_disagreement_by_arm_and_which_way_the_scorer_leans(self):
        code, result, out = self.differed
        self.assertEqual(code, 0)
        leans = {model: {arm: {lean: row[lean] for lean in claim.LEANS if row[lean]}
                         for arm, row in m["hand_reading"]["by_arm"].items() if any(row[lean] for lean in claim.LEANS)}
                 for model, m in result["models"].items()}
        self.assertEqual(leans, {DEEPSEEK: {"the block (model)": {"the scorer kinder": 2},
                                            "shipped": {"unscorable on one side": 1}},
                                 HAIKU: {"shipped": {"the scorer harsher": 1}}})
        listed = {(model, d["arm"], d["run"].split("/")[1]): (d["scorer"], d["hand"], d["note"])
                  for model, m in result["models"].items() for d in m["hand_reading"]["disagreements"]}
        self.assertEqual(listed, {
            (DEEPSEEK, "the block (model)", "tee-target-price-1"): ("correct", "not correct", "says the price, not who sells it"),
            (DEEPSEEK, "the block (model)", "tee-target-price-2"): ("correct", "not correct", ""),
            (DEEPSEEK, "shipped", "tee-top-3-3"): ("wrong", "unscorable", "two answers given"),
            (HAIKU, "shipped", "tee-target-price-1"): ("wrong", "correct", "reads as a fair answer")})
        # Every answered run was read: the block (model)'s 168 less its 30 declines and 3 closed slots.
        self.assertEqual(result["models"][DEEPSEEK]["hand_reading"]["by_arm"]["the block (model)"]["read"], 135)
        self.assertIn("the scorer kinder 2", out)

    def test_a_sheet_with_a_gap_is_refused(self):
        key = json.loads(self.sheet.with_name("sheet.key.json").read_text())
        one = sorted(key["codes"])[0]
        for label, sheet, words in (
                ("a row left unfilled", fill(self.sheet, "unfilled.csv", lambda row, mapped: "" if row["code"] == one else None),
                 "no hand verdict"),
                ("a verdict of its own", fill(self.sheet, "maybe.csv", lambda row, mapped: "maybe" if row["code"] == one else None),
                 "is not one of correct, not correct, unscorable"),
                ("a row taken out", fill(self.sheet, "short.csv", drop={one}), "1 codes of the key have no row"),
                ("a code the key has not", self.recoded(one), "is not in the key")):
            with self.subTest(fault=label):
                self.assertIn(words, self.refused(sheet))

    def recoded(self, code: str) -> pathlib.Path:
        sheet = fill(self.sheet, "recoded.csv")
        sheet.write_text(sheet.read_text().replace(code, "ffffffff", 1))
        return sheet

    def test_a_sheet_of_another_analysis_is_refused(self):
        # An answer that is not the run's, and a key of another task file.
        sheet = fill(self.sheet, "other.csv")
        with sheet.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        rows[0]["answer"] = "An answer no run gave."
        with sheet.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        self.assertIn("answer on the sheet is not the one", self.refused(sheet))
        sheet = fill(self.sheet, "elsewhere.csv")
        key_path = sheet.with_name("elsewhere.key.json")
        key_path.write_text(json.dumps({**json.loads(key_path.read_text()), "tasks_file": "tasks_aplus_dev.json"}))
        self.assertIn("its key is of tasks_aplus_dev.json", self.refused(sheet))
        # A sheet whole against its own key, which leaves out a run this analysis counts.
        key = json.loads(self.sheet.with_name("sheet.key.json").read_text())
        one = sorted(key["codes"])[0]
        sheet = fill(self.sheet, "fewer.csv", drop={one})
        key_path = sheet.with_name("fewer.key.json")
        key_path.write_text(json.dumps({**key, "codes": {c: v for c, v in key["codes"].items() if c != one}}))
        self.assertIn("1 runs the agent answered have no row", self.refused(sheet))

    def test_hand_needs_the_protocol_and_is_never_asked_with_a_new_sheet(self):
        with contextlib.redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit):
            claim.main([str(self.manifest), "--hand", str(self.sheet)])
        self.assertIn("needs --protocol", err.getvalue())
        with contextlib.redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit):
            claim.main(["--protocol", str(FULL), str(self.manifest), "--hand", str(self.sheet),
                        "--sheet", str(self.sheet.with_name("new.csv"))])
        self.assertIn("one at a time", err.getvalue())


def unscored_and_one_refused(model: str, arm: Plan, folder: pathlib.Path) -> None:
    """DeepSeek's block (model) answers a v2 rewording of tee-count-stocked under a reading with
    no key, and Haiku's shipped batch runs outside require and is not run again, so Haiku's
    analysis is refused."""
    if model == DEEPSEEK and arm.name == "the block (model)":
        unscored_run(folder, rewording_of(folder, "tee-count-stocked", V2_SOURCE), 1)
    if model == HAIKU and arm.name == "shipped":
        set_conditions(folder, max_steps=150)


class TheSheetsOwnRuns(unittest.TestCase):
    """`--hand` asks a row of exactly the runs `--sheet` writes one for (protocol analysis v7):
    none of a run with no key for the reading it answered, which the key file counts instead,
    as the reading rules say, and none of a refused model's, whose analysis is not made."""

    @classmethod
    def setUpClass(cls):
        cls.owner = tempfile.TemporaryDirectory()
        cls.manifest = build_run2(pathlib.Path(cls.owner.name), models=(DEEPSEEK, HAIKU), plant=unscored_and_one_refused)
        cls.sheet = cls.manifest.with_name("sheet.csv")
        cls.code, cls.result, cls.out = analyse(cls.manifest, extra=("--sheet", str(cls.sheet)))
        cls.key = json.loads(cls.sheet.with_name("sheet.key.json").read_text())
        cls.rw = rewording_of(cls.manifest, "tee-count-stocked", V2_SOURCE)

    @classmethod
    def tearDownClass(cls):
        cls.owner.cleanup()

    def unscored(self) -> dict:
        return next(run for run in self.result["models"][DEEPSEEK]["runs"] if run["verdict"] == "unscored"
                    and run["task"] == self.rw)

    def forged(self, name: str, mapped: dict, answer: str) -> pathlib.Path:
        """A sheet filled as the scorer has it with one row more, standing for `mapped`, in the
        sheet and in its key, with `answer`."""
        sheet = fill(self.sheet, name)
        key_path = sheet.with_name(sheet.stem + ".key.json")
        key_path.write_text(json.dumps({**self.key, "codes": {**self.key["codes"], "ffff0001": mapped}}))
        with sheet.open("a", newline="") as handle:
            csv.DictWriter(handle, fieldnames=list(claim.SHEET_COLUMNS)).writerow(
                {"code": "ffff0001", "question": "", "key": "", "answer": answer, "hand_verdict": "correct", "note": ""})
        return sheet

    def refused(self, sheet: pathlib.Path) -> str:
        with self.assertRaises(SystemExit) as raised:
            analyse(self.manifest, extra=("--hand", str(sheet)))
        return str(raised.exception)

    def test_the_sheet_leaves_off_the_unscored_run_and_the_refused_model(self):
        self.assertEqual(self.code, 1)
        self.assertIn("refused", self.result["models"][HAIKU])
        run = self.unscored()
        self.assertEqual((run["arm"], run["repeat"], run["answered"]), ("the block (model)", 1, "buyable"))
        self.assertEqual(self.key["unscored_left_out"], 1)
        self.assertFalse(any((c["task"], c["repeat"]) == (self.rw, 1) and c["arm"] == "the block (model)"
                             for c in self.key["codes"].values()))
        self.assertEqual({c["model"] for c in self.key["codes"].values()}, {DEEPSEEK})

    def test_hand_reads_it_back_with_one_model_refused(self):
        # Until v7 every run counted was asked a row, Haiku's too, so this sheet was refused.
        code, result, out = analyse(self.manifest, extra=("--hand", str(fill(self.sheet, "agreed.csv"))))
        self.assertEqual(code, 1)
        self.assertIn("refused", result["models"][HAIKU])
        m = result["models"][DEEPSEEK]
        self.assertEqual({t: v["p"] for t, v in m["hand_reading"]["tests"].items()},
                         {t: v["p"] for t, v in m["primary"].items()})
        self.assertEqual(result["hand_sheet"]["left_off"]["unscored_left_out"], 1)
        self.assertIn("runs with no key for the reading they answered 1", out)

    def test_a_row_for_a_run_off_the_sheet_is_refused(self):
        run = self.unscored()
        mapped = {"model": DEEPSEEK, "arm": run["arm"], "batch": run["batch"], "task": run["task"],
                  "repeat": run["repeat"], "answered": run["answered"], "verdict": run["verdict"]}
        self.assertIn(f"{self.rw}-1, which this analysis leaves off the sheet (unscored_left_out)",
                      self.refused(self.forged("unscored.csv", mapped, run["answer"])))
        # A row of the refused model's, whose batch is within require and counted, but read by no
        # model's analysis.
        folder = pathlib.Path(self.manifest.read_text().splitlines()[8].split("|")[1])
        row = next(r for r in json.loads((folder / "suite.json").read_text())["rows"]
                   if (r["task"], r["repeat"]) == ("tee-target-price", 1))
        mapped = {"model": HAIKU, "arm": "the block (model)", "batch": folder.name, "task": "tee-target-price",
                  "repeat": 1, "answered": None, "verdict": "correct"}
        self.assertIn("1 rows stand for runs no model's analysis reads",
                      self.refused(self.forged("refused.csv", mapped, row["answer"])))


class ManifestLines(unittest.TestCase):
    """The lines the second claim's chains write besides the batch and re-run lines (24 October
    2026, tools/claim2_stage_command.py): each a known line kept by its kind, never a problem,
    and an unknown line still one."""

    CHAIN = ("start 2026-10-24T10:00:00 usage 102.0154 cap 6.00",
             "conditions commit 03f69fddab2198a22f076344ffa6823af1da96b3 browser Google Chrome 141.0.7390.108",
             "probe|experiments/results/probe-20261024T100100.json|model=deepseek/deepseek-v4-flash routing check",
             "routing-check|ok",
             "batch|experiments/results/20261024T100500|model=deepseek/deepseek-v4-flash arm=the block (model) round=1 --box",
             "WATCHDOG 2026-10-24T10:31:02 spent 5.7012: stopped pid 4242",
             "rerun|experiments/results/20261024T103300|experiments/results/20261024T100500 --only tee-xs-price --repeat-start 1",
             "reading-test|experiments/results/probe-20261024T104000.json|model=deepseek/deepseek-v4-flash page-from x",
             "pilot-check|PASS|experiments/results/claim2-pilot.summary",
             "search-terms|before|Wexcombe|wexcombe tee,45,3,2026-10-24 10:05:00;|the block (model) round 1 --only tee-xs-price",
             "search-terms|after|Wexcombe|wexcombe tee,45,4,2026-10-24 10:09:00;|the block (model) round 1 --only tee-xs-price",
             "end 2026-10-24T10:41:00 usage 107.9000")

    def test_each_chain_line_is_known_and_kept_by_kind(self):
        found = claim.parse_manifest("\n".join(self.CHAIN))
        self.assertEqual(found.problems, [])
        self.assertEqual([line.kind for line in found.lines], ["batch", "rerun"])
        self.assertEqual({kind: len(lines) for kind, lines in found.extras.items()},
                         {"conditions": 1, "probe": 1, "routing-check": 1, "watchdog": 1, "reading-test": 1, "pilot-check": 1,
                          "search-terms": 2})
        self.assertEqual(found.extras["pilot-check"], ["pilot-check|PASS|experiments/results/claim2-pilot.summary"])
        self.assertEqual(found.extras["watchdog"][0][:9], "WATCHDOG ")
        self.assertEqual((len(found.starts), len(found.ends), found.stops), (1, 1, []))
        for kind in claim.CHAIN_LINES:
            with self.subTest(kind=kind):
                self.assertIn(kind, found.extras)
        # The report keeps them under the source's chain.
        src = claim.source(found.lines, found, [])
        self.assertEqual(src["chain"], found.extras)
        self.assertAlmostEqual(src["account_moved"], 107.9 - 102.0154)

    def test_an_unknown_line_is_still_a_problem_and_a_stop_a_stop(self):
        found = claim.parse_manifest("start 2026-10-24T10:00:00 usage 1.0 cap 6\nprobing|x\nSTOP the live check failed\n"
                                     "watchdog 2026-10-24T10:31:02\nend 2026-10-24T10:41:00 usage 2.0\n")
        self.assertEqual(len(found.problems), 2)
        self.assertIn("manifest line 2 is not one the claim command writes: probing|x", found.problems[0])
        self.assertIn("manifest line 4 is not one the claim command writes: watchdog", found.problems[1])
        self.assertEqual(found.stops, ["STOP the live check failed"])
        self.assertEqual(found.extras, {})


if __name__ == "__main__":
    unittest.main()
