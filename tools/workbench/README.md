# Optional Claude workbench

`igr-workbench/` is the legacy Claude Code plugin used to keep the project objective visible
and gate paid experiment commands. Its source and tests remain for research provenance.
It is not required to read the project, run `make check-offline`, or run the Python checks.

Local `.claude/` settings, agent definitions and worktrees are intentionally untracked.
Existing local files are retained during repository cleanup. A fresh clone does not install
or activate the plugin; `IGR_ESTIMATE_USD` alone does not enforce an approval gate.

`make mod` runs the optional plugin tests using a compatible Claude CLI. `make check-all`
includes those tests; `make check` runs the Python suite and planner regression only.

The hook intercepts Claude's `Bash` tool, not Codex or arbitrary shell execution. Before
paid runs, follow [the user guide](../../docs/user-guide.md#paid-runs-and-verification) and independently verify the exact launch
command, spending checks and execution context. No paid command is part of the default checks.

Personal `OBJECTIVE.md` and `PARKED.md` files are also local-only. A fresh clone has no
project-specific objective/drift context until those optional files are supplied. Plugin tests
use mock files and do not require the original research notebook.
