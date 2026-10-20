# Removing Claude as a co-author from the history


Prepared overnight on 21 October 2026. Nothing here has been run. Do it only when no paid
batch is running (check with `pgrep -fl suite.py`, which must print nothing).

### What it touches, measured tonight

- 219 of the 221 commits on `dev` end with a `Co-Authored-By: Claude ...` line, in three
  variants (Claude Opus 5 on 102 commits, Claude Fable 5.1 on 62, Claude Opus 5.5 on 55).
  `main`, the two tags (`rq2-baseline`, `rq3-gate-heldout`) and `backup/before-rewrite` share
  most of that history.
- Removing a line from a commit message changes that commit's id and every id after it. So
  every commit id changes, although no file content changes (the trees stay identical).
- The project cites commit ids as evidence. The protocol says the plan was committed at
  `3843e20` before the market existed, and the decision log, `LESSONS.md` and the site cite
  about 25 more. After the rewrite those ids still exist in your backup but not on GitHub.

### The choice

- **Option A, rewrite**, keeping every cited id traceable. This is the same method the project
  used for the first rewrite on 10 October (README, "Old commit ids are mapped to new ones").
  It publishes a map from old ids to new, updates the ids quoted in the log, the notes, the
  protocol and the code, and leaves run records and archived pages as written.
- **Option B, no rewrite.** Commits from now on carry no Claude line (already in effect since
  00:12 on 21 October). Credit Claude in the README and the report. This has no risk and keeps
  every id valid, but GitHub would still list Claude on the old commits.

Option A is safe if done in this order. Choose B if you would rather not touch history again
before the abstract.

### Option A, step by step (about 20 minutes)

1. Install the tool: `brew install git-filter-repo`
2. Back up everything: `git clone --mirror git@github.com:kr7001/fyp-shopping-agent.git ~/fyp-backup-before-coauthor-rewrite.git`
3. In the project folder, remove the three finished agent worktrees and their branches:
   `git worktree remove --force .claude/worktrees/agent-a01850863544fa058` (and the same for
   `agent-a35e53ef628c48029` and `agent-ab608abc551d4b6ce`), then
   `git branch -D worktree-agent-a01850863544fa058 worktree-agent-a35e53ef628c48029 worktree-agent-ab608abc551d4b6ce`.
4. Do the rewrite in a fresh clone, never in the working folder (which holds the run logs, the
   `.env` and the agent submodule):
   ```
   git clone git@github.com:kr7001/fyp-shopping-agent.git ~/fyp-rewrite && cd ~/fyp-rewrite
   git checkout -B main origin/main && git checkout -B dev origin/dev && git fetch --tags
   git log --all --format=%B | grep -c "Co-Authored-By: Claude"     # expect about 219 plus main's
   git rev-parse dev^{tree} > /tmp/tree-before.txt
   ```
5. Remove only the Claude lines, nothing else:
   ```
   git filter-repo --force --message-callback '
   import re
   return re.sub(rb"\n*Co-Authored-By: Claude[^\n]*", b"", message).rstrip(b"\n") + b"\n"
   '
   ```
6. Check it did exactly that:
   ```
   git log --all --format=%B | grep -c "Co-Authored-By: Claude"     # must be 0
   git rev-parse dev^{tree} | diff - /tmp/tree-before.txt && echo "files identical"
   git log --format=%s dev | wc -l                                  # still 221 or more
   ```
7. Keep the map from old ids to new: `cp .git/filter-repo/commit-map docs/archive/commit-map-2026-10-21.txt`
8. Update the ids quoted in the prose (README.md, LESSONS.md, docs/content/*.md including the
   protocol, and comments in experiments/ and env/), and leave `experiments/results/`,
   `docs/archive/` and `.verification/` as written. Ask me to do this step: it is a scripted
   replacement from the map, and I will show you the diff before you commit it.
9. Add one line to the README decision log: "21 October 2026: Claude co-author lines removed
   from the history at the student's request. Ids before this date map through
   docs/archive/commit-map-2026-10-21.txt. Claude's role is credited under 'How this project
   was built'."
10. Push, replacing GitHub's history (this is the irreversible step):
    ```
    git remote add origin git@github.com:kr7001/fyp-shopping-agent.git
    git push --force-with-lease origin dev main
    git push --force origin --tags
    ```
11. Bring the working folder onto the new history, which keeps its ignored files (logs, `.env`):
    ```
    cd ~/projects/shopping-agent-against-information-gated-retrieval
    git fetch origin --tags --force
    git checkout dev && git reset --hard origin/dev
    git status            # only your own uncommitted files (docs/report-4.*) should show
    ```
12. Any paid run after this needs a fresh verifier stamp, because the stamp names a commit id.

### What to put in the README and the report instead

A short section, "How this project was built": the student designed the research, made every
decision and reviewed every result. Claude Code (Anthropic), used with Claude Opus and Fable
models, wrote most of the code under the student's direction, ran the independent
verification passes, and drafted documentation. The decision log records what was decided,
when and why. Check your faculty's rules on declaring AI assistance, and use their wording if
they give one.
