#!/usr/bin/env python3
"""Data for the report's Figure 6 (fig:frontier), and with --tikz the figure body itself.

Redrawn 3 November 2026. The old figure drew mean charges where Table 19 (tab:rq3) gives
medians, and left out the Quenby replication and, in places, the shipped agent. This one
draws one row for each row of Table 19, each study and model on its own, never pooled.

(a) H1 as Table 19 gives it: correct runs of the block against the shipped agent on the
    reading-independent questions. Claim 1's verdict is the automatic scorer's, claim 2's and
    the replication's the student's blind reading.
(b) Median provider charge a run for the block, the shipped agent and open everything, on one
    question set per study: the H3 (gated) questions that every drawn arm ran. The arms ran
    different questions in places, and medians over different questions do not compare.
    Where that set is the whole H3 set, the block and open everything must equal Table 19's
    H3 medians, and the script stops otherwise.

Free: reads stored analysis files only, never a model, the shop or the network. Wexcombe's
shipped charges on its two two-reading questions exist only in the private analysis file
(gitignored), so both claim 2 markets read their private analysis, held to the hash the
released artifact records for it, and every released run must agree with it.

    python3 tools/fig_frontier_data.py          # every drawn value with its question set and n
    python3 tools/fig_frontier_data.py --tikz   # the tikzpicture and the legend line
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from statistics import median
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "tools"))
import paths  # noqa: E402
import reproduce_report  # noqa: E402

CLOSED = reproduce_report.CLOSED
ARMS = ("block", "shipped", "exhaustive")  # legend order, and the order of each row's offsets
NAMES = {"block": "block", "shipped": "shipped agent", "exhaustive": "open everything"}

# The four rows of Table 19, top to bottom: (Table 19's name, the figure's row label, source).
CLAIM1 = (
    ("Ashcombe, Claude Haiku 4.5", "Ashcombe, Haiku", "claim-20261020.analysis.json",
     "anthropic/claude-haiku-4.5"),
    ("Ashcombe, DeepSeek V4 Flash", "Ashcombe, DeepSeek", "night-20261020.deepseek.analysis.json",
     "deepseek/deepseek-v4-flash"),
)
# The private analysis each released claim 2 dataset was exported from (experiments/artifacts/README.md).
CLAIM2 = {"Wexcombe": "claim2b-stage1.analysis.json",
          "Quenby": "claim2-replication-28-oct-both-rounds.hand.analysis.json"}
# The released artifact's model, as Table 19 names it and as the figure's row label does.
CLAIM2_MODEL = {"deepseek/deepseek-v4-flash": ("DeepSeek V4 Flash", "DeepSeek")}

# An arm is left out of panel (b) for a study when keeping it would leave fewer than half of
# that study's H3 questions, so no drawn median rests on a minority of the questions its H3
# test used (3 November 2026). It fires on no study as run: Quenby keeps 6 of 8.
MIN_SHARE = 0.5


def require(condition, message):
    if not condition:
        raise ValueError(message)


def index(runs):
    """Runs by (arm, question, repeat). A repeat counted twice would weight its question twice."""
    seen = {}
    for run in runs:
        key = run["arm"], run["task"], run["repeat"]
        require(key not in seen, f"run {key} appears twice")
        seen[key] = run
    return seen


def claim1_study(name, short, filename, model, folder=None):
    """One model of claim 1, from its committed analysis file (automatic scorer)."""
    analysis = json.loads(((folder or paths.RESULTS) / filename).read_text())
    record = analysis["models"][model]
    h1, h3 = record["primary"]["H1"], record["primary"]["H3"]
    require(h1["a"] == h3["a"] and h1["b"] == "shipped", f"{name}: H1 and H3 name different arms")
    arms = {h3["a"]: "block", h1["b"]: "shipped", h3["b"]: "exhaustive"}
    require(h3["left_out_without_a_value"] == 0, f"{name}: H3 left a run out")
    runs = [{"arm": arms[r["arm"]], "task": r["task"], "repeat": r["repeat"], "cost": r["cost"],
             "closed": r["outcome"] == CLOSED} for r in record["runs"] if r["arm"] in arms]
    index(runs)
    return {"name": name, "short": short, "source": f"experiments/results/{filename}",
            "verdict": f"automatic scorer v{analysis['scorer_version']}",
            "h1": {"questions": list(h1["questions"]), "block": tuple(h1["pooled"]["a"]),
                   "shipped": tuple(h1["pooled"]["b"]), "unscorable": 0},
            "h3": {"questions": list(h3["questions"]), "block": median(h3["pooled"]["a"]),
                   "exhaustive": median(h3["pooled"]["b"])},
            "runs": runs}


def check_released(runs, released, arms):
    """Every released run must have the private analysis's charge and outcome, arm for arm."""
    ours = index(runs)
    for run in released:
        key = arms[run["arm"]], run["task"], run["repeat"]
        mine = ours.get(key)
        require(mine is not None, f"released run {key} is missing from the private analysis")
        require(mine["cost"] == run["cost_usd"] and mine["closed"] == (run["outcome"] == CLOSED),
                f"released run {key} differs from the private analysis")


def claim2_study(dataset, summary, model, folder=None):
    """Wexcombe or Quenby: H1 from the released artifact, charges from the private analysis."""
    market = dataset["market"]
    protocol = json.loads((ROOT / dataset["protocol_path"]).read_text())
    raw = ((folder or paths.RESULTS) / CLAIM2[market]).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == dataset["source_hashes"]["analysis_json"],
            f"{market}: the private analysis is not the one the released artifact was exported from")
    record = json.loads(raw)["models"][model]
    tests, sets = protocol["tests"], protocol["sets"]
    require(tests["H1"]["a"] == tests["H3"]["a"], f"{market}: H1 and H3 name different blocks")
    arms = {tests["H1"]["a"]: "block", tests["H1"]["b"]: "shipped", tests["H3"]["b"]: "exhaustive"}
    wanted = set(sets["gated"]) | set(sets["reading_independent"])
    runs = [{"arm": arms[r["arm"]], "task": r["task"], "repeat": r["repeat"], "cost": r["cost"],
             "closed": r["outcome"] == CLOSED} for r in record["runs"]
            if r["arm"] in arms and r["task"] in wanted and r["repeat"] in dataset["rounds"]]
    check_released(runs, dataset["runs"], {reproduce_report.ARMS[a]: ours for a, ours in arms.items()})
    block, shipped = summary["accuracy"]["block_model"], summary["accuracy"]["shipped"]
    resources = summary["resources"]
    name, short = CLAIM2_MODEL[model]
    return {"name": f"{market}, {name}", "short": f"{market}, {short}",
            "source": f"experiments/results/{CLAIM2[market]} (private), {reproduce_report.DEFAULT.relative_to(ROOT)}",
            "verdict": "blind hand reading",
            "h1": {"questions": list(sets["reading_independent"]),
                   "block": (block["correct"], block["scored"]),
                   "shipped": (shipped["correct"], shipped["scored"]),
                   "unscorable": block["unscorable"] + shipped["unscorable"]},
            "h3": {"questions": list(sets["gated"]),
                   "block": resources["block_model"]["median_cost_usd"],
                   "exhaustive": resources["exhaustive"]["median_cost_usd"]},
            "runs": runs}


def plotted_set(h3, ran, share=MIN_SHARE):
    """The H3 questions every drawn arm ran, and the arms left out to keep that set large enough.

    `ran` maps each arm to the questions it ran. The block is never left out: it is the subject.
    """
    drawn, left_out = [a for a in ARMS if a in ran], []
    while True:
        common = [q for q in h3 if all(q in ran[a] for a in drawn)]
        others = [a for a in drawn if a != "block"]
        if len(common) >= share * len(h3) or not others:
            return common, left_out
        fewest = min(others, key=lambda a: (len(set(h3) & set(ran[a])), ARMS.index(a)))
        drawn.remove(fewest)
        left_out.append(fewest)


def check_grid(runs, arms, questions):
    """Each drawn arm must have the same repeats of every drawn question, or a median weights them unequally."""
    grids = {(a, q): sorted(r["repeat"] for r in runs if r["arm"] == a and r["task"] == q)
             for a in arms for q in questions}
    first = next(iter(grids.values()), [])
    for key, repeats in grids.items():
        require(repeats and repeats == first, f"{key} has repeats {repeats}, others {first}")


def check_table19(values, record):
    """On the whole H3 set the block and open everything are Table 19's H3 medians, exactly."""
    for arm in ("block", "exhaustive"):
        if arm in values:
            require(values[arm]["median"] == record[arm],
                    f"{arm}: median {values[arm]['median']} is not Table 19's H3 value {record[arm]}")


def charge_group(study):
    h3 = study["h3"]["questions"]
    ran = {a: {r["task"] for r in study["runs"] if r["arm"] == a} for a in ARMS}
    questions, left_out = plotted_set(h3, ran)
    drawn = [a for a in ARMS if a not in left_out]
    check_grid(study["runs"], drawn, questions)
    values = {}
    for arm in drawn:
        selected = [r for r in study["runs"] if r["arm"] == arm and r["task"] in questions]
        costs = [r["cost"] for r in selected if not r["closed"]]
        require(costs and all(type(c) in (int, float) and math.isfinite(c) and c >= 0 for c in costs),
                f"{study['name']}, {arm}: a charge is missing or invalid")
        values[arm] = {"median": median(costs), "n": len(costs), "closed": len(selected) - len(costs)}
    whole = questions == h3
    if whole:
        check_table19(values, study["h3"])
    return {"questions": questions, "whole": whole, "left_out": left_out, "values": values}


def block_against_shipped(study, questions):
    """Medians and n of the block and the shipped agent on the given questions. Not drawn."""
    out = {}
    for arm in ("block", "shipped"):
        costs = [r["cost"] for r in study["runs"] if r["arm"] == arm and r["task"] in questions and not r["closed"]]
        out[arm] = (median(costs), len(costs)) if costs else (None, 0)
    return out


def studies():
    """The four rows of Table 19, with panel (b)'s group computed for each."""
    rows = [claim1_study(*spec) for spec in CLAIM1]
    artifact = json.loads(reproduce_report.DEFAULT.read_text())
    for dataset, summary in zip(artifact["datasets"], reproduce_report.reproduce(artifact)):
        rows.append(claim2_study(dataset, summary, artifact["model"]))
    for row in rows:
        row["charge"] = charge_group(row)
    return rows


def percent(count):
    return 100 * count[0] / count[1]


def table(rows):
    lines = ["Figure 6 data. One row per row of Table 19. Studies and models are never pooled.", ""]
    lines += ["Panel (a): H1, correct runs on the reading-independent questions",
              "| Study | Verdict | Question set | Block | Shipped agent |", "| --- | --- | --- | --- | --- |"]
    for row in rows:
        h1 = row["h1"]
        cells = [f"{c}/{n} = {percent((c, n)):.1f}%" for c, n in (h1["block"], h1["shipped"])]
        lines.append(f"| {row['name']} | {row['verdict']} | {len(h1['questions'])} reading-independent questions | "
                     f"{cells[0]} | {cells[1]} |")
    lines.append("")
    for row in rows:
        if row["h1"]["unscorable"]:
            lines.append(f"{row['name']}: {row['h1']['unscorable']} answer marked unscorable by the human reader "
                         "is outside the denominator, as prespecified.")
    lines += ["", "Panel (b): median provider charge a run (US$), on the H3 questions every drawn arm ran",
              "| Study | Question set | Block | Shipped agent | Open everything | Table 19 H3 |",
              "| --- | --- | --- | --- | --- | --- |"]
    for row in rows:
        group, h3 = row["charge"], row["h3"]["questions"]
        where = (f"all {len(h3)} H3 questions" if group["whole"]
                 else f"{len(group['questions'])} of {len(h3)} H3 questions")
        cells = []
        for arm in ARMS:
            v = group["values"].get(arm)
            cells.append("left out" if v is None else
                         f"{v['median']:.7f} (n={v['n']}" + (f", {v['closed']} closed" if v["closed"] else "") + ")")
        check = ("same set, block and open everything equal it" if group["whole"]
                 else "not the H3 set, so not Table 19's values")
        lines.append(f"| {row['name']} | {where} | " + " | ".join(cells) + f" | {check} |")
    lines.append("")
    for row in rows:
        group = row["charge"]
        lines.append(f"{row['name']}: drawn set {', '.join(group['questions'])}.")
        missing = [q for q in row["h3"]["questions"] if q not in group["questions"]]
        if missing:
            short = [a for a in ARMS if not set(missing) <= {r["task"] for r in row["runs"] if r["arm"] == a}]
            lines.append(f"  Left out of the set: {', '.join(missing)}, which the {', '.join(NAMES[a] for a in short)} did not run.")
        for arm in group["left_out"]:
            lines.append(f"  Left out of the panel: the {NAMES[arm]}, whose H3 questions in common were too few.")
        values = group["values"]
        if "shipped" in values:
            higher = values["block"]["median"] > values["shipped"]["median"]
            lines.append(f"  Block {'HIGHER' if higher else 'lower'} than the shipped agent: "
                         f"{values['block']['median']:.4f} against {values['shipped']['median']:.4f}.")
    lines += ["", "Not drawn, a check on the set: block against shipped agent on the gated questions inside H1",
              "| Study | Questions | Block | Shipped agent | Block higher? |", "| --- | --- | --- | --- | --- |"]
    for row in rows:
        questions = [q for q in row["h3"]["questions"] if q in row["h1"]["questions"]]
        pair = block_against_shipped(row, questions)
        (b, nb), (s, ns) = pair["block"], pair["shipped"]
        if b is None or s is None:
            lines.append(f"| {row['name']} | {len(questions)} | not computable: an arm ran none of them | | |")
            continue
        lines.append(f"| {row['name']} | {len(questions)} | {b:.7f} (n={nb}) | {s:.7f} (n={ns}) | "
                     f"{'yes' if b > s else 'no'} |")
    lines += ["", "Sources:"] + [f"  {row['name']}: {row['source']}" for row in rows]
    lines.append("Charges are the provider's charges per completed run, model parsing included where used. "
                 "Slots the block closed are left out of the charges, as in Table 19's H3.")
    return "\n".join(lines)


# Each arm's colour, and its bar's offset within a row in each panel, the block on top.
STYLE = {"block": "figblue", "shipped": "figorange", "exhaustive": "black!45"}
OFFSET = {"accuracy": {"block": 0.14, "shipped": -0.14},
          "charge": {"block": 0.25, "shipped": 0.0, "exhaustive": -0.25}}


def plot(arm, points):
    colour = STYLE[arm]
    body = " ".join(f"({x},{y}) [{label}]" for x, y, label in points)
    return (f"\\addplot[{colour}, fill={colour}, nodes near coords, point meta=explicit symbolic]\n"
            f"  coordinates {{{body}}};")


def tikz(rows):
    count = len(rows)
    y = {row["name"]: count - i for i, row in enumerate(rows)}  # first row of Table 19 at the top
    labels = ",".join("{" + row["short"] + "}" for row in reversed(rows))
    top = max(v["median"] for row in rows for v in row["charge"]["values"].values())
    xmax = math.ceil(top * 1.12 / 0.1) * 0.1  # room for the label beside the largest charge
    ticks = ",".join(f"{t / 10:g}" for t in range(round(xmax * 10) + 1))

    def place(row, panel, arm):
        return f"{y[row['name']] + OFFSET[panel][arm]:g}"

    accuracy = []
    for arm in ("shipped", "block"):
        points = [(f"{percent(row['h1'][arm]):.1f}", place(row, "accuracy", arm),
                   f"{row['h1'][arm][0]}/{row['h1'][arm][1]}")
                  for row in rows]
        accuracy.append(plot(arm, points))
    charge = []
    for arm in ("exhaustive", "shipped", "block"):
        points = [(f"{row['charge']['values'][arm]['median']:.4f}", place(row, "charge", arm),
                   f"{row['charge']['values'][arm]['median']:.3g}")
                  for row in rows if arm in row["charge"]["values"]]
        if points:
            charge.append(plot(arm, points))
    return "\n".join([
        "% Drawn by `python3 tools/fig_frontier_data.py --tikz` from the stored analysis files. Do not edit by hand.",
        "% Two endpoints in separate panels on the same rows. Panel (b) uses the H3 questions every drawn arm",
        "% ran, a different set from panel (a), so the panels are not one workload and are not a trade-off.",
        "% Within a row each arm has its own bar from zero, the block on top.",
        "\\begin{tikzpicture}",
        "\\begin{groupplot}[group style={group size=2 by 1, horizontal sep=1.3cm, yticklabels at=edge left},",
        f"  scale only axis, width=0.33\\linewidth, height=5cm, ymin=0.5, ymax={count + 0.5:g}, "
        f"ytick={{{','.join(str(i) for i in range(1, count + 1))}}},",
        f"  yticklabels={{{labels}}},",
        "  tick label style={font=\\scriptsize}, label style={font=\\small, align=center}, title style={font=\\small},",
        "  xmajorgrids, grid style={gray!20}, axis lines*=left,",
        "  every axis plot/.append style={xbar, bar width=0.22, bar shift=0pt, draw=none}, clip=false,",
        "  every node near coord/.append style={font=\\tiny, black!75, inner sep=2pt, anchor=west},",
        "  scaled x ticks=false, xticklabel style={/pgf/number format/fixed, /pgf/number format/precision=2}]",
        "\\nextgroupplot[title={(a) Accuracy (H1)}, xlabel={Correct (\\%)\\\\reading-independent questions},",
        "  xmin=0, xmax=100, xtick={0,25,50,75,100}]",
        *accuracy,
        "\\nextgroupplot[title={(b) Charge}, xlabel={Median charge a run (US\\$)\\\\gated questions all drawn arms ran},",
        f"  xmin=0, xmax={xmax:g}, xtick={{{ticks}}}]",
        *charge,
        "\\end{groupplot}",
        "\\end{tikzpicture}",
        "\\par\\smallskip",
        "{\\small\\tikz\\fill[figblue] (0,0) rectangle (0.6em,0.6em);\\enspace block\\qquad",
        "\\tikz\\fill[figorange] (0,0) rectangle (0.6em,0.6em);\\enspace shipped agent\\qquad",
        "\\tikz\\fill[black!45] (0,0) rectangle (0.6em,0.6em);\\enspace open everything}",
    ])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tikz", action="store_true", help="print the figure body instead of the table")
    args = parser.parse_args()
    try:
        rows = studies()
    except (OSError, KeyError, TypeError, ValueError) as exc:
        parser.exit(2, f"Cannot compute Figure 6: {exc}\n")
    print(tikz(rows) if args.tikz else table(rows))


if __name__ == "__main__":
    main()
