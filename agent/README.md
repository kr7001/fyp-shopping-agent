# The agent: openJiuwen

`agent-core/` is openJiuwen's `agent-core` repository, Apache 2.0, from
https://github.com/openJiuwen-ai/agent-core, pinned as a git submodule at commit
`18d45d6` on the `develop` branch. The browser agent the project studies lives in
`agent-core/openjiuwen/harness/tools/browser_move/`.

Nothing inside `agent-core/` is committed to this repository. The one change made to it is
kept here as a patch instead, so a fresh clone can rebuild the openJiuwen code the runs used.
The browser, Playwright MCP, is still fetched as `@latest`, see the site's Problems page.

## Set up from a fresh clone

```bash
git submodule update --init agent/agent-core
git -C agent/agent-core apply ../openjiuwen-local.patch
cd agent/agent-core && uv sync
```

The runners call it with `uv run python` from inside `agent-core/`, so `uv sync` is the
only install step. The browser itself is Playwright MCP, fetched by `npx` at run time.

## What the patch changes, and why

`openjiuwen-local.patch` touches two files.

- `browser_move/utils/parsing.py` gains `parse_json_object`, which returns `None` for text
  that is not JSON and `{}` for a payload that really was empty. The upstream
  `extract_json_object` returns `{}` for both.
- `browser_move/playwright_runtime/runtime.py` uses it in `browser_probe_cards` and
  `browser_probe_interactives`. Upstream, a page with no cards was reported to the agent as
  "Could not parse ... result JSON", so the agent retried the probe instead of moving on.

Found on 8 September 2026, see `notes/first-agent-runs.md`. Not offered upstream yet. No
upstream contribution is claimed unless a pull request is merged.

The decision log for 8 September also names a second local fix, for the worker's
`ok: false` not reaching the run result. That change is not in the submodule's working tree
today. The submodule's reflog holds a commit made inside it by mistake on 9 September and since
reset, whose change is the same as today's patch, so it was not there then either. "Never
applied" is the likelier reading. It is listed as an open problem on the project site.
