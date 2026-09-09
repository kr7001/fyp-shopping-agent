#!/usr/bin/env bash
# Run one browser task and score its trace, in one step.
#
# The runner writes its JSON record while its own stdout is still being redirected
# to the log, so it cannot count its own tool calls. This runs the task, then hands
# the finished log to trace_stats.py to fold the counts back into the record.
#
#   experiments/run.sh "your question"
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(date +%Y%m%dT%H%M%S)"
LOG="$REPO/experiments/runs/$STAMP.log"

cd "$REPO/agent/agent-core"
uv run python "$REPO/experiments/run_browser_task.py" "$@" > "$LOG" 2>&1 || true

grep -E "^elapsed|^ok|^result:" "$LOG" || true
python3 "$REPO/experiments/trace_stats.py" "$LOG" --update-json
