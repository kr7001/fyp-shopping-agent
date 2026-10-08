#!/usr/bin/env python3
"""The "see everything" arm: openJiuwen with one setting changed and nothing else.

Why this arm exists
-------------------

openJiuwen's card summary reports only what is inside the browser window. On our search page
of fifteen products it reports four, and the reply contains no field saying anything was
left out. Across unmodified runs, 74 opened exactly four listings and not one of those had
read the search page in full, against 30 of 38 that opened some other number.

That is an association across stored runs and not a controlled test, so it cannot separate
two explanations:

    the tool hid the page        the summary dropped eleven listings, so the agent could
                                 not act on what it never saw
    the model looks less         a model inclined to stop early would stop at four anyway,
                                 and the summary merely agrees with it

This arm separates them. It flips `viewport_only` to False, which the probe already supports,
and changes **nothing else**: same prompt, same tools, same model, same budget, same shop,
same questions. If runs still stop at four listings, the cause is the model. If they stop
stopping, the cause is the tool.

Already measured at the tool level, with no model involved: the shipped setting reports 4
sellers in 31,701 characters and this one reports all 15 in 88,822. So the flag works, and
the open question is only whether the agent then uses what it is given.

Why a patch rather than an edit
-------------------------------

`agent/agent-core` is a checkout of someone else's project and this repository never commits
changes to it. Editing the probe in place would leave the arm undocumented and unreproducible
for anyone else. So the change lives here, is applied at import time by the runner when
`IGR_SEE_EVERYTHING=1` is set, and is recorded in the run's own record.

It patches one thing: the default of the `viewport_only` input, which the model may still
override if it explicitly passes a value. The agent is not told about the change, because
telling it would alter the prompt and that is the thing being held constant.
"""

from __future__ import annotations

import os

ENV_FLAG = "IGR_SEE_EVERYTHING"


def wanted() -> bool:
    return os.environ.get(ENV_FLAG, "") in {"1", "true", "yes", "on"}


def apply() -> str:
    """Flip the card probe's default to the whole page. Returns what was done, for the record."""
    if not wanted():
        return "off"

    from openjiuwen.harness.tools.browser_move.playwright_runtime import runtime_tools

    tool = getattr(runtime_tools, "BrowserProbeCardsTool", None)
    if tool is None:  # pragma: no cover - the class name is checked by the self test below
        raise SystemExit(
            "see_everything: BrowserProbeCardsTool not found in runtime_tools. "
            "The upstream class has been renamed and this patch needs updating.")

    original = tool.invoke

    async def invoke(self, inputs, **kwargs):
        # A dict copy rather than a mutation, since the caller's dict is not ours to edit.
        patched = dict(inputs or {})
        patched.setdefault("viewport_only", False)
        return await original(self, patched, **kwargs)

    tool.invoke = invoke
    return "viewport_only defaults to False"


def self_test() -> int:
    """Check the patch still binds to the real class, without running a browser or a model."""
    os.environ[ENV_FLAG] = "1"
    from openjiuwen.harness.tools.browser_move.playwright_runtime import runtime_tools

    tool = getattr(runtime_tools, "BrowserProbeCardsTool", None)
    if tool is None:
        print("FAIL: BrowserProbeCardsTool is gone from runtime_tools")
        return 1
    before = tool.invoke
    note = apply()
    after = tool.invoke
    ok = before is not after and note != "off"
    print(f"patch applied: {note}")
    print(f"invoke replaced: {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(self_test())
