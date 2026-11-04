#!/usr/bin/env python3
"""Did the agents in the primary studies fetch product pages by page script? A free audit.

Written 4 November 2026, when the student approved a free audit of the stored traces. The
report counts a listing as opened when the agent navigates to its product page: the frozen
counter, `sufficiency.listings_opened`, reads the addresses a `page.goto` went to and the
addresses a tool reply reports as the current page. A product page that the agent's own page
script downloads never becomes the current page, so the counter never sees it. That happened
in the supplementary studies (two Quenby matched-briefing trials fetched all 45 product
documents while recording 7 and 5 navigations) and, as the 27 October draft of the report
said, in two shipped DeepSeek runs of claim 1. This reads the stored run logs of the primary
studies and counts every such fetch, by study and arm. It never calls a model, the shop or the
network, and it never runs the recorded code: it reads it.

Which trials. The four primary comparisons of the report's Table 19 (`STUDIES`), and in each
exactly the runs its frozen analysis uses: the `runs` of its stored analysis file, which
already leaves out the technical voids (each replaced by its re-run, as the analysis lists
under `exclusions`). Claim 1's batch of newer question shapes is not among them. A slot the
block closed by asking back or declining ran no agent and has no log: it is counted as a slot
and not scanned. Every scanned run's
navigation count is recomputed with the frozen counter and must equal the analysis's
`opened`, or the audit stops, so the only difference in a combined count is what scripts
fetched.

The counting rule. A product document counts as fetched by script when all of these hold.

1. A script call. The call is the Playwright tool that runs the agent's own JavaScript in the
   page, `browser_evaluate` (argument `function`), or `browser_run_code` (argument `code`),
   under any prefix the model spelt it with. No other tool in these logs runs page script:
   `browser_batch_interact`'s operations select, click, wait, sleep, take screenshots and read
   text.
2. It ran. Its reply carries the tool's `### Result` header. A reply of `### Error` means the
   script threw, and how far it got cannot be told from the log, so its requests are listed
   but not counted. A reply of "Ability not found" means the runtime did not know the name the
   model used (`mcp_playwright-official-browser_evaluate`), so nothing ran.
3. It requested a document. The code calls `fetch(`, opens an `XMLHttpRequest`, calls jQuery's
   `$.get`, `$.getJSON`, `$.ajax` or `$.post`, sets an iframe's `src`, calls `window.open(`, or
   assigns `location`. A request whose method is not GET (POST, HEAD, PUT, PATCH, DELETE) reads
   no document: an add-to-cart form post is not a page read.
4. Its target is a listing of the market. The market is the task file's own fixture's listing
   URLs, the set the frozen counter counts against (`verify_cells.market_urls`, LESSONS 2 and
   33). A target is read as written in the code, and is one of:
     a listing          it names a listing's URL key, `igr-rp28-21.html` or a URL ending in it
     the current page   `location.href`, `window.location.href`, `document.URL` and the like:
                        the document the browser already shows, which the counter already
                        counts when it is a listing, so never another document
     not a listing      a results page (`catalogsearch`), an API (`/graphql`, `/rest/`,
                        `getQty`, `customer/section`, `search/ajax`), `/checkout`, `/static/`,
                        `sitemap`, `robots.txt`, `/admin`, or a product page outside the
                        market (a page of the WebArena catalogue)
     built at run time  anything else: a variable or a concatenation, `fetch(u)`,
                        `'http://localhost:7770/' + slug + '.html'`
   A listing target names its listing. A target built at run time names the listings whose
   URL key the call's code spells out, the list the URL was built from, as when a script maps
   45 keys to URLs and fetches each, and, when a string of the code ends in the market's
   shared key prefix (`'http://localhost:7770/igr-fm02-' + id + '.html'`, or a template
   literal's text before `${`), the listings whose number the code lists as a string in an
   array (`['02', '37']`). A number a loop counts to is never read: such a script is left
   unresolved (rule 5). These are the counted measure, "fetched by script". A key is matched
   whole and in lower case, as URL keys are written, so `IGR-TCL-38`, a SKU sent to the REST
   API, and `igr-tcl-38-m`, a size's SKU, are never a listing, nor is `igr-rp28-2` inside
   `igr-rp28-22`.
5. Reply evidence, reported apart. A script whose run-time target names no key in its code
   (it read the URLs off a results page it fetched) leaves its reply as the only record of
   which listings it fetched. The listings that reply names are reported as "named in the
   reply" and form a second, broader combined count. They are never added to the counted
   measure, because a reply can name listings the script did not fetch. A script that
   requested an address built at run time and names no listing in its code or its reply
   (it counted from 1 to 45 to build the keys, or fetched a variable that held a results
   page) is counted as unresolved, by call: it may have fetched listings this cannot name.

Embedded-data reads. A call that ran and whose code names the theme's hidden variant store
(`igr-variant-store`, `data-igr`) or Magento's configurable-product data (`spConfig`,
`jsonConfig`) read embedded variant data. On the page the browser shows, that is not a fetch
of another document and adds no listing: the counter already counts that page when it is a
listing, and `experiments/analysis/leaks.py` counts the read as a leak. In a call that also
requested a listing or a URL built at run time, it is part of those fetches. Both are reported
as counts of calls and change no count of listings.

Counts per trial. Navigated: the frozen counter's listings. Fetched by script: the distinct
listings the rule above names. Fetched only by script: those the counter did not count.
Combined: navigated plus fetched only by script, the size of their union. With the reply: the
same with the listings named in the reply added.

The sensitivity check. H2 compares the listings opened by the block against open everything
on the gated questions, by the frozen `claim.compare_ranks` (van Elteren's stratified exact
rank test, mid-ranks) with Holm's adjustment over the study's family (`claim.holm`), the other
tests' p values taken from the analysis of record: claim 1's automatic analysis, claim 2's and
the replication's hand reading. It is recomputed with each run's combined count, once for the
counted measure and once with the reply's, beside the frozen values, which are recomputed
first and must equal the stored ones. Every arm's median on the same questions is given the
same three ways, since the report quotes some arms outside H2. No frozen analysis is changed.

    python3 tools/audit_script_fetches.py
    python3 tools/audit_script_fetches.py --json experiments/artifacts/script-fetch-audit-4-nov.json
    python3 tools/audit_script_fetches.py --log experiments/results/<batch>/<task>-<repeat>.log

`--log` shows what the rule read in one log, call by call, for checking it on a known case.
"""
from __future__ import annotations

import argparse
import collections
import dataclasses
import hashlib
import json
import pathlib
import re
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "tools"))
import paths  # noqa: E402  (puts box/, runners/, analysis/, water/ on the path)
import claim  # noqa: E402  (compare_ranks and holm: the frozen H2 test and its correction)
import reproduce_report  # noqa: E402  (the released artifact, which holds claim 2's analysis hashes)
import sufficiency  # noqa: E402  (listings_opened: the frozen counter)
import trace_stats  # noqa: E402
import verify_cells  # noqa: E402  (market_urls: the listing set the counter counts against)
import voids  # noqa: E402

# Bumped when a count this prints would change for the same logs, and written into the JSON.
#   1  4 November 2026, the first audit
AUDIT_VERSION = 1


@dataclasses.dataclass(frozen=True)
class Study:
    name: str
    analysis: str          # the frozen analysis file, in experiments/results
    model: str
    record: str            # where the tests of record are: "primary" or "hand_reading"
    released: str | None   # the market whose released artifact holds this file's hash


# The four primary comparisons of the report's Table 19, each on its own, never pooled.
STUDIES = (
    Study("Claim 1, Ashcombe, Claude Haiku 4.5", "claim-20261020.analysis.json",
          "anthropic/claude-haiku-4.5", "primary", None),
    Study("Claim 1, Ashcombe, DeepSeek V4 Flash", "night-20261020.deepseek.analysis.json",
          "deepseek/deepseek-v4-flash", "primary", None),
    Study("Claim 2, Wexcombe, DeepSeek V4 Flash", "claim2b-stage1.analysis.json",
          "deepseek/deepseek-v4-flash", "hand_reading", "Wexcombe"),
    Study("Quenby replication, DeepSeek V4 Flash",
          "claim2-replication-28-oct-both-rounds.hand.analysis.json",
          "deepseek/deepseek-v4-flash", "hand_reading", "Quenby"),
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


# ---------------------------------------------------------------------------
# The trace

@dataclasses.dataclass
class Call:
    id: str
    tool: str              # as the model named it, the runtime's prefix removed
    arguments: str         # as sent
    reply: str | None      # the longest copy of the reply, None when none came back


def trace_calls(text: str) -> list[Call]:
    """Every tool call in an openJiuwen log, once each, in call order, with the longest copy of
    its reply. The runtime trims older replies to a thousand characters before re-sending
    them, so the longest copy is the original (`trace_stats.tool_replies`). A call that never
    got a reply is kept too, which `tool_replies` leaves out."""
    calls: dict[str, Call] = {}
    for line in text.splitlines():
        start = line.find('{"event_id"')
        if start < 0:
            continue
        try:
            event = json.loads(line[start:])
        except json.JSONDecodeError:
            continue
        for message in event.get("messages") or []:
            for call in message.get("tool_calls") or []:
                function = call.get("function") or {}
                raw = function.get("arguments")
                raw = raw if isinstance(raw, str) else json.dumps(raw)
                known = calls.setdefault(call.get("id"), Call(
                    call.get("id"), trace_stats.normalise(function.get("name") or ""), raw, None))
                if len(raw) > len(known.arguments):
                    known.arguments = raw
            if message.get("role") == "tool":
                content = message.get("content")
                content = content if isinstance(content, str) else json.dumps(content)
                known = calls.get(message.get("tool_call_id"))
                if known is not None and len(content) > len(known.reply or ""):
                    known.reply = content
    return list(calls.values())


# The tools that run the agent's own JavaScript. A suffix, so a misspelt prefix is still read
# as a script call; whether it ran is its reply's to say (`outcome`).
SCRIPT_TOOLS = ("browser_evaluate", "browser_run_code")

RAN, THREW, NOT_RUN, NO_REPLY = "ran", "threw", "did not run", "no reply"


def is_script(call: Call) -> bool:
    return call.tool.endswith(SCRIPT_TOOLS)


def code_of(call: Call) -> str:
    """The script a call sent: its `function` or `code` argument, else the arguments whole."""
    try:
        arguments = json.loads(call.arguments)
    except json.JSONDecodeError:
        return call.arguments
    if isinstance(arguments, dict):
        for key in ("function", "code"):
            if isinstance(arguments.get(key), str):
                return arguments[key]
    return call.arguments


def outcome(reply: str | None) -> str:
    """Whether a script call ran, from the header its reply opens with. Read in these logs on
    4 November 2026: every primary-study call to a script tool replied `### Result`, `### Error`
    or "Ability not found in resource_mgr: <name>", the last for a name the runtime did not
    know, and none was left without a reply."""
    if reply is None:
        return NO_REPLY
    result, error = reply.find("### Result"), reply.find("### Error")
    if result >= 0 and (error < 0 or result < error):
        return RAN
    if error >= 0:
        return THREW
    return NOT_RUN


# ---------------------------------------------------------------------------
# The requests a script makes

@dataclasses.dataclass(frozen=True)
class Request:
    how: str       # fetch, XMLHttpRequest, jQuery, iframe, window.open, location
    target: str    # the expression the address came from, as written
    method: str    # GET unless the code says otherwise; "?" when it names it by a variable


FETCH = re.compile(r"\bfetch\s*\(")
XHR_OPEN = re.compile(r"(?<!window)\.open\s*\(")
JQUERY = re.compile(r"(?:\$|\bjQuery)\.(get|getJSON|post|ajax)\s*\(")
IFRAME = re.compile(r"createElement\(\s*['\"`]iframe", re.IGNORECASE)
SRC = re.compile(r"\.src\s*=(?!=)\s*([^;\n]+)")
WINDOW_OPEN = re.compile(r"\bwindow\.open\s*\(")
LOCATION_SET = re.compile(r"\blocation(?:\.href)?\s*=(?!=)\s*([^;\n]+)")
LOCATION_CALL = re.compile(r"\blocation\.(?:assign|replace)\s*\(")
METHOD = re.compile(r"\b(?:method|type)\s*:\s*['\"`](\w+)")
URL_FIELD = re.compile(r"\burl\s*:\s*([^,}\n]+)")


def arguments_at(code: str, start: int, limit: int = 600) -> list[str]:
    """The top-level arguments of the call whose opening parenthesis ends at `start`, as
    written. Strings and nested brackets are skipped whole. The scan stops after `limit`
    characters, so a call whose end it cannot find never swallows the rest of the script."""
    found, depth, quote, begin, i = [], 0, None, start, start
    end = min(len(code), start + limit)
    while i < end:
        ch = code[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "'\"`":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                found.append(code[begin:i].strip())
                return found
            depth -= 1
        elif ch == "," and depth == 0:
            found.append(code[begin:i].strip())
            begin = i + 1
        i += 1
    found.append(code[begin:end].strip())
    return found


def literal_method(text: str) -> str:
    """A method written as a string, upper case, or "?" when a variable holds it."""
    bare = text.strip()
    if len(bare) >= 2 and bare[0] in "'\"`" and bare[-1] == bare[0]:
        return bare[1:-1].upper()
    return "?"


def requests_in(code: str) -> list[Request]:
    """Every request for an address that a script makes, in the forms rule 3 names."""
    found = []
    for match in FETCH.finditer(code):
        args = arguments_at(code, match.end())
        method = METHOD.search(args[1]) if len(args) > 1 else None
        found.append(Request("fetch", args[0], method.group(1).upper() if method else "GET"))
    if "XMLHttpRequest" in code:
        for match in XHR_OPEN.finditer(code):
            args = arguments_at(code, match.end())
            if len(args) >= 2:
                found.append(Request("XMLHttpRequest", args[1], literal_method(args[0])))
    for match in JQUERY.finditer(code):
        args = arguments_at(code, match.end())
        kind, first = match.group(1), args[0]
        if kind == "ajax":
            method = METHOD.search(first)
            url = URL_FIELD.search(first) if first.startswith("{") else None
            found.append(Request("jQuery", url.group(1).strip() if url else first,
                                 method.group(1).upper() if method else "GET"))
        else:
            found.append(Request("jQuery", first, "POST" if kind == "post" else "GET"))
    if IFRAME.search(code):
        found += [Request("iframe", match.group(1).strip(), "GET") for match in SRC.finditer(code)]
    for match in WINDOW_OPEN.finditer(code):
        found.append(Request("window.open", arguments_at(code, match.end())[0], "GET"))
    found += [Request("location", match.group(1).strip(), "GET") for match in LOCATION_SET.finditer(code)]
    for match in LOCATION_CALL.finditer(code):
        found.append(Request("location", arguments_at(code, match.end())[0], "GET"))
    return found


# What a target can be (rule 4). A listing and one built at run time can name listings.
LISTING, RUNTIME, CURRENT = "listing", "built at run time", "current page"
NOT_A_READ, OUTSIDE = "not a read", "product page outside the market"
# Addresses that are never a product page, by what they are. Read off every request target
# in the primary studies' scripts on 4 November 2026: Wexcombe's shipped runs asked
# GraphQL, the REST API, the stock endpoint, the cart, sitemap.xml and the theme's own
# scripts as well as product pages.
NOT_A_LISTING = (
    ("results page", ("catalogsearch",)),
    ("API", ("/graphql", "/rest/", "getQty", "inventory_catalog", "customer/section", "search/ajax")),
    ("other page", ("/checkout", "/static/", "sitemap", "robots.txt", "/admin", ".playwright-mcp", "/media/")),
)
CURRENT_PAGE = re.compile(r"^(?:window\.|document\.)?(?:location(?:\.href|\.pathname)?|URL)$")
PRODUCT_PATH = re.compile(r"/[a-z0-9][a-z0-9-]*\.html")
READS = ("GET", "?")   # a method named by a variable may be a read
COUNTED = (LISTING, RUNTIME)


@dataclasses.dataclass(frozen=True)
class Market:
    """A market's listings as a script writes them: each URL key (`igr-fm02-02`), the pattern
    that matches one whole, and the prefixes the keys share before their number (`igr-fm02-`)."""
    keys: frozenset[str]
    pattern: re.Pattern
    prefixes: frozenset[str]


def market_from(urls: list[str]) -> Market:
    keys = frozenset(key.split(":", 1)[1] for key in map(sufficiency.listing_key, urls)
                     if key and key.startswith("slug:"))
    alternatives = "|".join(re.escape(key) for key in sorted(keys, key=lambda k: (-len(k), k)))
    pattern = re.compile(rf"(?<![A-Za-z0-9_-])(?:{alternatives})(?![A-Za-z0-9_-])")
    prefixes = frozenset(m.group(1) for m in map(re.compile(r"^(.*-)\d+$").match, keys) if m)
    return Market(keys, pattern, prefixes)


def keys_in(text: str | None, market: Market) -> set[str]:
    """The market's URL keys a text writes whole, in lower case (rule 4)."""
    return set(market.pattern.findall(text or ""))


STRING = re.compile(r"'([^'\\\n]*)'|\"([^\"\\\n]*)\"|`([^`\\\n$]*)`")
# The text of a template literal before its first placeholder: `http://localhost:7770/igr-tcl-${n}.html`.
TEMPLATE_HEAD = re.compile(r"`([^`\\\n$]*)\$\{")
# An array written out as strings and nothing else, `['02', '37']`.
STRINGS_ARRAY = re.compile(r"\[\s*(?:'[^'\\\n]*'|\"[^\"\\\n]*\")"
                           r"(?:\s*,\s*(?:'[^'\\\n]*'|\"[^\"\\\n]*\"))*\s*,?\s*\]")


def strings_of(text: str) -> list[str]:
    return [next(g for g in m.groups() if g is not None) for m in STRING.finditer(text)]


def keys_from_parts(code: str, market: Market) -> set[str]:
    """Keys a script builds from the market's prefix and a number it lists as a string:
    `'http://localhost:7770/igr-fm02-' + id + '.html'` over `['02', '37']` (rule 4). The prefix
    must end a string of the code, or a template literal's text before its first placeholder,
    and the number must be a whole string in an array of strings, so neither a number a loop
    counts to nor a `"17"` inside a regular expression (20261024T232020/decline-delivery-1,
    a size's option id) ever names a listing. Written for 20261102T061732/tee-count-buyable-2,
    a Rookmere trial that fetched 44 listings this way (read 4 November 2026)."""
    listed = [s for array in STRINGS_ARRAY.finditer(code) for s in strings_of(array.group(0))]
    ends = strings_of(code) + TEMPLATE_HEAD.findall(code)
    found = set()
    for prefix in market.prefixes:
        if any(s.endswith(prefix) for s in ends):
            found |= {prefix + s for s in listed if prefix + s in market.keys}
    return found


def classify(request: Request, market: Market) -> tuple[str, set[str]]:
    """What a request's target is, and the listings it names when it names them itself. An
    address that is never a product page is named for what it is first, so a GraphQL query
    sent by POST reads as the API it is."""
    for kind, marks in NOT_A_LISTING:
        if any(mark in request.target for mark in marks):
            return kind, set()
    if request.method not in READS:
        return NOT_A_READ, set()
    if CURRENT_PAGE.match(re.sub(r"\s+", "", request.target)):
        return CURRENT, set()
    named = keys_in(request.target, market)
    if named:
        return LISTING, named
    if PRODUCT_PATH.search(request.target):
        return OUTSIDE, set()
    return RUNTIME, set()


# The theme's hidden variant store and Magento's configurable-product data, as a script names
# them (the theme's template, env/gated_theme/, and leaks.STORE).
EMBEDDED = ("igr-variant-store", "data-igr", "spConfig", "jsonConfig")


@dataclasses.dataclass
class Finding:
    """What one script call did, by the rule in the module's docstring."""
    call: Call
    outcome: str
    requests: list[tuple[Request, str]]
    named: set[str]         # listings the call names and requested: the counted measure
    in_reply: set[str]      # listings its reply names, for a run-time target with no key in its code
    embedded: bool          # its code names embedded variant data

    @property
    def requested_listing(self) -> bool:
        """Whether it requested a listing or an address built at run time, the requests that
        can fetch another product document."""
        return any(kind in COUNTED for _, kind in self.requests)

    @property
    def unresolved(self) -> bool:
        """It requested an address built at run time and names no listing anywhere (rule 5)."""
        return (any(kind == RUNTIME for _, kind in self.requests)
                and not self.named and not self.in_reply)


def read_call(call: Call, market: Market) -> Finding:
    code = code_of(call)
    requests, named = [], set()
    for request in requests_in(code):
        kind, listings = classify(request, market)
        requests.append((request, kind))
        named |= listings
    in_code = keys_in(code, market)
    runtime = any(kind == RUNTIME for _, kind in requests)
    if runtime:
        named |= in_code | keys_from_parts(code, market)
    in_reply = keys_in(call.reply, market) - named if runtime and not in_code else set()
    return Finding(call, outcome(call.reply), requests, named, in_reply,
                   any(mark in code for mark in EMBEDDED))


# ---------------------------------------------------------------------------
# One trial

def audit_text(text: str, urls: list[str]) -> dict:
    """One trial's counts from its log text and its market's listing URLs."""
    navigated = {key.split(":", 1)[1] for key in sufficiency.listings_opened(text, urls)}
    market = market_from(urls)
    findings = [read_call(call, market) for call in trace_calls(text) if is_script(call)]
    ran = [f for f in findings if f.outcome == RAN]
    fetched = set().union(*(f.named for f in ran))
    in_reply = set().union(*(f.in_reply for f in ran)) - fetched
    requests = collections.Counter(kind for f in ran for _, kind in f.requests)
    return {
        "navigated": len(navigated),
        "fetched_by_script": len(fetched),
        "fetched_only_by_script": len(fetched - navigated),
        "combined": len(navigated | fetched),
        "named_in_reply_only": len(in_reply - navigated),
        "combined_with_reply": len(navigated | fetched | in_reply),
        "fetched": sorted(fetched),
        "fetched_only": sorted(fetched - navigated),
        "script_calls": dict(sorted(collections.Counter(f.outcome for f in findings).items())),
        "requests_in_scripts_that_ran": dict(sorted(requests.items())),
        # Scripts that may have fetched listings this cannot name: listed, never counted.
        "unresolved_calls": sum(f.unresolved for f in ran),
        "threw_after_requesting_listings": sum(f.outcome == THREW and f.requested_listing for f in findings),
        "embedded_reads": {
            "current_page": sum(f.embedded and not f.requested_listing for f in ran),
            "fetched_documents": sum(f.embedded and f.requested_listing for f in ran)},
        "_findings": findings,
    }


def market_of(batch: pathlib.Path, cache: dict) -> list[str]:
    """The listing URLs the frozen counter counts a batch's runs against: its task file's own
    fixture's (`verify_cells.market_urls`), the same for every arm."""
    name = json.loads((batch / "suite.json").read_text())["tasks_file"]
    if name not in cache:
        market = verify_cells.market_urls(json.loads((paths.TASKS / name).read_text()))
        require(market, f"{name} names no fixture, so its listing set is not the counter's here")
        cache[name] = market
    return cache[name]


# ---------------------------------------------------------------------------
# One study

def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tests_of_record(record: dict, study: Study) -> dict:
    tests = record["primary"] if study.record == "primary" else record["hand_reading"]["tests"]
    return {name: test for name, test in tests.items() if isinstance(test, dict) and "p" in test}


def h2_variant(record: dict, tests: dict, values: dict) -> dict:
    """H2 with each run's listings replaced by `values[(batch, task, repeat)]` where given,
    through the frozen test and Holm's adjustment over the study's family."""
    h2 = tests["H2"]
    arms = {h2["a"]: [], h2["b"]: []}
    for run in record["runs"]:
        if run["arm"] in arms:
            key = (run["batch"], run["task"], run["repeat"])
            arms[run["arm"]].append({**run, "opened": values.get(key, run["opened"])})
    test = claim.compare_ranks(arms[h2["a"]], arms[h2["b"]], h2["questions"], "opened")
    family = {name: t["p"] for name, t in tests.items()}
    family["H2"] = test["p"]
    a, b = test["pooled"]["a"], test["pooled"]["b"]
    return {"median_block": statistics.median(a), "median_open": statistics.median(b),
            "n": [len(a), len(b)], "observed": test["observed"], "expected": test["expected"],
            "p": test["p"], "p_holm": claim.holm(family)["H2"],
            "per_question": test["per_question"]}


def sensitivity(record: dict, study: Study, trials: list[dict]) -> dict:
    """H2 as frozen, then with the combined counts, the counted measure and with the reply."""
    tests = tests_of_record(record, study)
    h2 = tests["H2"]
    by_key = {(t["batch"], t["task"], t["repeat"]): t for t in trials}
    out = {"a": h2["a"], "b": h2["b"], "questions": list(h2["questions"]),
           "family": sorted(tests), "record": study.record}
    for name, measure in (("frozen", "navigated"), ("fetched_by_script", "combined"),
                          ("with_reply", "combined_with_reply")):
        out[name] = h2_variant(record, tests, {key: t[measure] for key, t in by_key.items()})
    frozen = out["frozen"]
    require(frozen["p"] == h2["p"] and frozen["p_holm"] == h2["p_holm"],
            f"{study.name}: the frozen H2 recomputes to p {frozen['p']}, Holm {frozen['p_holm']}, "
            f"against the stored {h2['p']}, {h2['p_holm']}")
    for name in ("fetched_by_script", "with_reply"):
        variant = out[name]
        variant["medians_changed"] = (variant["median_block"], variant["median_open"]) != (
            frozen["median_block"], frozen["median_open"])
        variant["p_changed"] = variant["p"] != frozen["p"]
        variant["block_fewer"] = variant["median_block"] < variant["median_open"]
        variant["rejected_at_05"] = variant["p_holm"] <= claim.ALPHA
    out["frozen"]["block_fewer"] = frozen["median_block"] < frozen["median_open"]
    out["frozen"]["rejected_at_05"] = frozen["p_holm"] <= claim.ALPHA
    # Every arm's median on the same questions, since the report quotes some outside H2 (the
    # shipped agent's on Ashcombe), each measured as H2 measures it (`claim.values`).
    out["arm_medians"] = {}
    for arm in claim.ordered({run["arm"] for run in record["runs"]}):
        runs = [run for run in record["runs"] if run["arm"] == arm]
        medians = {}
        for name, measure in (("frozen", "navigated"), ("fetched_by_script", "combined"),
                              ("with_reply", "combined_with_reply")):
            def value(run, measure=measure):
                found = by_key.get((run["batch"], run["task"], run["repeat"]))
                return run["opened"] if found is None else found[measure]
            pooled = [v for q, vs in claim.values(runs, h2["questions"], value).items() for v in vs]
            medians[name] = statistics.median(pooled) if pooled else None
        medians["n"] = len(pooled)
        out["arm_medians"][arm] = medians
    for arm, median in ((h2["a"], frozen["median_block"]), (h2["b"], frozen["median_open"])):
        require(out["arm_medians"][arm]["frozen"] == median,
                f"{study.name}: {arm}'s median {out['arm_medians'][arm]['frozen']} is not H2's {median}")
    return out


def audit_study(study: Study, folder: pathlib.Path | None = None) -> dict:
    folder = folder or paths.RESULTS
    path = folder / study.analysis
    digest = sha256(path)
    if study.released:
        artifact = json.loads(reproduce_report.DEFAULT.read_text())
        held = {d["market"]: d["source_hashes"]["analysis_json"] for d in artifact["datasets"]}
        require(held.get(study.released) == digest,
                f"{study.analysis} is not the analysis the released artifact was exported from")
    record = json.loads(path.read_text())["models"][study.model]
    cache, trials, missing, closed = {}, [], [], collections.Counter()
    for run in record["runs"]:
        if run["outcome"] == voids.CLOSED:
            closed[run["arm"]] += 1
            continue
        log = folder / run["batch"] / f"{run['task']}-{run['repeat']}.log"
        try:
            text = log.read_text(errors="replace")
        except OSError as exc:
            missing.append({"log": str(log.relative_to(ROOT)) if log.is_relative_to(ROOT) else str(log),
                            "arm": run["arm"], "why": type(exc).__name__})
            continue
        counts = audit_text(text, market_of(log.parent, cache))
        require(counts["navigated"] == run["opened"],
                f"{log}: the frozen counter reads {counts['navigated']} listings, the analysis "
                f"{run['opened']}, so this is not the analysis's count")
        # The listings scripts fetched that the counter missed are kept by key; the rest by count.
        for name in ("_findings", "fetched"):
            counts.pop(name)
        trials.append({"batch": run["batch"], "task": run["task"], "repeat": run["repeat"],
                       "arm": run["arm"], **counts})
    arms = {}
    for arm in claim.ordered({run["arm"] for run in record["runs"]}):
        mine = [t for t in trials if t["arm"] == arm]
        slots = sum(run["arm"] == arm for run in record["runs"])
        affected = [t for t in mine if t["fetched_by_script"]]
        arms[arm] = {
            "slots": slots, "closed_by_the_block": closed[arm], "scanned": len(mine),
            "with_a_script_fetch": len(affected),
            "with_a_script_fetch_or_reply_listing": sum(
                bool(t["fetched_by_script"] or t["named_in_reply_only"]) for t in mine),
            "with_listings_only_scripts_fetched": sum(bool(t["fetched_only_by_script"]) for t in mine),
            "fetched_by_script_per_affected_trial": [t["fetched_by_script"] for t in affected],
            "with_unresolved_calls": sum(bool(t["unresolved_calls"]) for t in mine),
            "script_calls_that_ran": sum(t["script_calls"].get(RAN, 0) for t in mine),
            "embedded_reads_on_the_current_page": sum(t["embedded_reads"]["current_page"] for t in mine),
            "trials_with_api_requests": sum(bool(t["requests_in_scripts_that_ran"].get("API")) for t in mine)}
    out = {"study": study.name, "model": study.model,
           "analysis": f"experiments/results/{study.analysis}", "analysis_sha256": digest,
           "released_artifact_hash_checked": bool(study.released),
           "slots": len(record["runs"]), "closed_by_the_block": sum(closed.values()),
           "agent_trials": len(record["runs"]) - sum(closed.values()),
           "scanned": len(trials), "missing_logs": missing,
           "voids_excluded_by_the_analysis": len(record["exclusions"]["voids"]),
           "arms": arms,
           "affected_trials": [{k: t[k] for k in ("batch", "task", "repeat", "arm", "navigated",
                                                  "fetched_by_script", "fetched_only_by_script",
                                                  "combined", "named_in_reply_only",
                                                  "combined_with_reply", "unresolved_calls",
                                                  "fetched_only")}
                               for t in trials if t["fetched_by_script"] or t["named_in_reply_only"]
                               or t["unresolved_calls"]],
           "trials": trials}
    # A study with a log missing cannot be recomputed whole, so its H2 is not, rather than guessed.
    out["h2"] = None if missing else sensitivity(record, study, trials)
    return out


# ---------------------------------------------------------------------------
# Output

def p_text(p: float) -> str:
    return f"{p:.3g}"


def render(studies: list[dict]) -> str:
    lines = [f"Script-fetch audit of the primary studies, audit v{AUDIT_VERSION} "
             f"(counter rules v{sufficiency.RULES_VERSION}, claim analysis v{claim.VERSION})",
             "Fetched by script: listings a script that ran named and requested (counted). "
             "With the reply: listings named in the reply of a script whose URLs were built at "
             "run time (reported apart, never counted).",
             "Columns, in trials: fetch, a listing fetched by script; +reply, the same or a listing "
             "named in such a reply; uncounted, a listing scripts fetched and the counter did not "
             "count; unresolved, a script that requested an address built at run time and names "
             "no listing.", ""]
    for s in studies:
        lines.append(f"{s['study']}   {s['analysis']}")
        lines.append(f"  {s['slots']} slots in the analysis: {s['agent_trials']} agent trials, "
                     f"{s['closed_by_the_block']} closed by the block (no agent ran). "
                     f"{s['voids_excluded_by_the_analysis']} voids excluded by the analysis, "
                     f"their re-runs counted.")
        lines.append(f"  Scanned {s['scanned']} of {s['agent_trials']} agent trials. Every scanned "
                     "navigation count equals the analysis's.")
        for gone in s["missing_logs"]:
            lines.append(f"  MISSING: {gone['log']} ({gone['arm']}): {gone['why']}")
        lines.append(f"  {'arm':34} {'slots':>5} {'scanned':>7} {'fetch':>5} {'+reply':>6} "
                     f"{'uncounted':>9} {'unresolved':>10}  fetched per affected trial")
        for arm, a in s["arms"].items():
            lines.append(f"  {arm:34} {a['slots']:>5} {a['scanned']:>7} {a['with_a_script_fetch']:>5} "
                         f"{a['with_a_script_fetch_or_reply_listing']:>6} "
                         f"{a['with_listings_only_scripts_fetched']:>9} {a['with_unresolved_calls']:>10}  "
                         f"{a['fetched_by_script_per_affected_trial'] or '-'}")
        if s["affected_trials"]:
            lines.append("  Trials with a script fetch, navigated + fetched only by script = combined "
                         "(with the reply), unresolved calls:")
        for t in s["affected_trials"]:
            lines.append(f"    {t['batch']}/{t['task']}-{t['repeat']} [{t['arm']}]: {t['navigated']} + "
                         f"{t['fetched_only_by_script']} = {t['combined']} ({t['combined_with_reply']}); "
                         f"fetched by script {t['fetched_by_script']}, unresolved {t['unresolved_calls']}")
        h2 = s["h2"]
        if h2 is None:
            lines.append("  H2 not recomputed: a log is missing.")
        else:
            lines.append(f"  H2, {h2['a']} against {h2['b']}, {len(h2['questions'])} gated questions, "
                         f"Holm over {', '.join(h2['family'])} ({h2['record']}):")
            for name in ("frozen", "fetched_by_script", "with_reply"):
                v = h2[name]
                change = "" if name == "frozen" else (
                    f"  medians {'CHANGED' if v['medians_changed'] else 'unchanged'}, "
                    f"p {'changed' if v['p_changed'] else 'unchanged'}, "
                    f"direction {'kept' if v['block_fewer'] else 'LOST'}")
                lines.append(f"    {name:18} medians {v['median_block']:g} vs {v['median_open']:g}, "
                             f"p {p_text(v['p'])}, Holm {p_text(v['p_holm'])}{change}")
            lines.append("  Every arm's median listings on the same questions, frozen / fetched by script "
                         "/ with the reply (n):")
            for arm, m in h2["arm_medians"].items():
                values = " / ".join("-" if m[k] is None else f"{m[k]:g}"
                                    for k in ("frozen", "fetched_by_script", "with_reply"))
                lines.append(f"    {arm:34} {values} ({m['n']})")
        lines.append("")
    return "\n".join(lines)


def describe(log: pathlib.Path) -> str:
    """What the rule read in one log, call by call: every script call that requested an
    address or read embedded data."""
    text = log.read_text(errors="replace")
    counts = audit_text(text, market_of(log.parent, {}))
    lines = [f"{log}: navigated {counts['navigated']}, fetched by script {counts['fetched_by_script']} "
             f"({counts['fetched_only_by_script']} only by script), combined {counts['combined']}, "
             f"with the reply {counts['combined_with_reply']}. Script calls {counts['script_calls']}."]
    for f in counts["_findings"]:
        if not f.requests and not f.embedded:
            continue
        lines.append(f"  {f.call.id} {f.call.tool}: {f.outcome}" + (", embedded data" if f.embedded else ""))
        for request, kind in f.requests:
            target = re.sub(r"\s+", " ", request.target)
            lines.append(f"    {request.how} {request.method} -> {kind}: {target[:90]}")
        if f.named:
            lines.append(f"    named {len(f.named)}: {', '.join(sorted(f.named))}")
        if f.in_reply:
            lines.append(f"    named in the reply {len(f.in_reply)}")
        if f.unresolved and f.outcome == RAN:
            lines.append("    unresolved: an address built at run time, no listing named")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", type=pathlib.Path, help="also write every count here; never overwrites")
    parser.add_argument("--log", type=pathlib.Path, help="show what the rule read in one log instead")
    args = parser.parse_args()
    if args.log:
        print(describe(args.log))
        return 0
    if args.json and args.json.exists():
        parser.exit(2, f"{args.json} exists. Move it away before writing a new one to its path.\n")
    studies = []
    for study in STUDIES:
        try:
            studies.append(audit_study(study))
        except (OSError, KeyError, ValueError) as exc:
            parser.exit(2, f"Cannot audit {study.name}: {exc}\n")
    print(render(studies))
    if args.json:
        payload = {"audit": "product documents fetched by page script in the primary studies",
                   "command": "python3 tools/audit_script_fetches.py --json " + str(args.json),
                   "audit_version": AUDIT_VERSION, "counter_rules_version": sufficiency.RULES_VERSION,
                   "claim_analysis_version": claim.VERSION,
                   "script_sha256": sha256(pathlib.Path(__file__).resolve()),
                   "rule": "see the docstring of tools/audit_script_fetches.py", "studies": studies}
        with open(args.json, "x", encoding="utf-8") as out:
            json.dump(payload, out, indent=1)
            out.write("\n")
        print(f"Wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
