# Removing Claude as a co-author from the history

Done on 21 October 2026, at the student's request. This page records what was run, so the
rewrite can be checked or undone. The overnight draft of these steps is in this file's history.

## Outcome

| | Before | After |
| --- | --- | --- |
| Commits on `dev` | 225, tip `bddd6e1` | 225, tip `21e808d` |
| Commits on `main` | 139, tip `ee0a7eb` | 139, tip `8cad71a` |
| Messages with a `Co-Authored-By: Claude` line | 219 | 0 |
| Trees, authors, committers and dates | | the same in all 225 pairs |
| Ids that changed | | 223 of 225 |

Removing a line from a message changes that commit's id and the id of every commit after it.
The first two commits carried no line and kept their ids. The other 223 ids changed, while no
file did. Commits made after the rewrite carry no Claude line, by the rule in force since
00:12 on 21 October.

## What was run

1. **Backup.** The old history, exactly as GitHub had it, is in a mirror outside the
   repository, never pushed:
   `git clone --mirror git@github.com:kr7001/fyp-shopping-agent.git ~/fyp-backup-before-coauthor-rewrite.git`
2. **Worktrees.** The three finished agent worktrees under `.claude/worktrees/` and their
   `worktree-agent-*` branches were removed from the working folder.
3. **The rewrite**, in a fresh clone at `~/fyp-rewrite`, never in the working folder, which
   holds the run logs, the `.env` and the agent submodule:
   ```
   git filter-repo --force --message-callback '
   import re
   return re.sub(rb"\n*Co-Authored-By: Claude[^\n]*", b"", message).rstrip(b"\n") + b"\n"
   '
   ```
   By default git filter-repo also rewrites commit ids quoted inside messages to the new ids.
   Fifteen messages quote one, so their references still lead to the right commit.
4. **The check.** Each old commit was compared with its new one through the map: the same
   tree, the same parents, the same author, committer and dates, and the same message once
   the Claude line is removed and quoted ids are mapped. All 225 pairs passed. The script is
   below.
5. **The push**, replacing GitHub's history. The leases name the exact old tips, so the push
   would have been refused had GitHub changed since the backup:
   ```
   git push --force-with-lease=dev:bddd6e198b1b8c544d364df9b09f8b0fe6bbcd38 \
            --force-with-lease=main:ee0a7eb1df8ed947cf409fcd2d84253501a7193d origin dev main
   ```
6. **The working folder**, moved onto the new history without changing a file:
   ```
   git fetch origin
   git reset origin/dev            # mixed: the trees are identical, so no file changes
   git branch -f main origin/main
   ```
   The overnight draft said `git reset --hard`. That would have discarded the uncommitted
   edits to `docs/report-4.html`, `docs/report-4.js` and `docs/site-data.js`. A mixed reset
   kept them.
7. **Tags.** GitHub had none. The two local tags were moved through the map.
   `rq3-gate-heldout` now points at `6c218b3`. `rq2-baseline`, an annotated tag, was
   re-created with `git mktag` from its own tag object, so its tagger, date and message are
   unchanged, and it points at `abe8d7f`.
8. **The map and the quoted ids.** The map is `docs/archive/commit-map-2026-10-21.txt`. Ids
   quoted in the decision log, the notes, these guides, `PARKED.md`, `docs/content/` and the
   code comments were replaced through it by the second script below. The site data,
   `docs/site-data.js`, was not rebuilt, and the next `make site` brings the new ids with it.

## What was left as written

- Run records in `experiments/results/`, the archived pages in `docs/archive/` and the
  verifier's stamps in `.verification/` keep the ids they were written with. The map
  resolves them. An id from before 10 October goes through `docs/archive/commit-map.txt`
  first, then the new map.
- The claim protocol, `docs/content/claim-protocol.md`, is the pre-registration. It is left
  exactly as it stood before the rewrite, so it still quotes `ea17804` and `c09bd87`. They are
  now `9cf54a5` and `51f3b0f`.
- `backup/before-rewrite`, the local branch kept from the rewrite of 10 October, is untouched
  and has never been pushed. Its commits from before 10 October still carry the lines.

## Worth knowing

- GitHub still serves an old commit to anyone who has its exact id, until it clears out
  commits that no branch reaches. GitHub Support can clear them sooner on request. Nothing on
  GitHub leads to them: the repository has no forks and no pull requests.
- A paid run from now on needs a fresh verifier stamp, because a stamp names a commit id.
- To undo, push the mirror's two branches back. The command names GitHub's address, because
  the mirror's own remote is set to mirror and refuses a push of named branches:
  `git -C ~/fyp-backup-before-coauthor-rewrite.git push --force git@github.com:kr7001/fyp-shopping-agent.git dev main`

## Credit

The README's "How this project was built" says who did what, and so does the footer of the
update of 21 October. Check the faculty's rules on declaring AI assistance in the final report,
and use their wording if they give one.

## The two scripts

The pair check, run from the repository root. It needs the backup mirror, and it checks that
the map covers every commit on both sides:

```python
import pathlib, re, subprocess
OLD = pathlib.Path.home() / "fyp-backup-before-coauthor-rewrite.git"
MAP = pathlib.Path("docs/archive/commit-map-2026-10-21.txt")
FMT = "%H%x00%T%x00%P%x00%an%x00%ae%x00%ad%x00%cn%x00%ce%x00%cd%x00%B%x1e"

def commits(repo):
    out = subprocess.run(["git", "-C", str(repo), "log", "--all", f"--format={FMT}", "--date=raw"],
                         capture_output=True, text=True, check=True).stdout
    rows = (r.strip("\n").split("\x00") for r in out.split("\x1e") if r.strip("\n"))
    return {f[0]: (f[1], f[2].split(), tuple(f[3:9]), f[9]) for f in rows}

rows = [l.split() for l in MAP.read_text().splitlines() if l.strip() and not l.startswith("#")]
pairs = dict(rows[1:])
HEX = re.compile(r"(?<![0-9a-fA-F])[0-9a-f]{7,40}(?![0-9a-fA-F])")
def mapped(message):
    def swap(m):
        hits = [o for o in pairs if o.startswith(m.group(0))]
        return pairs[hits[0]][:len(m.group(0))] if len(hits) == 1 else m.group(0)
    return HEX.sub(swap, re.sub(r"\n*Co-Authored-By: Claude[^\n]*", "", message).rstrip("\n"))

old, new = commits(OLD), commits(".")
bad = [o for o, n in pairs.items()
       if old[o][0] != new[n][0] or [pairs[p] for p in old[o][1]] != new[n][1]
       or old[o][2] != new[n][2] or mapped(old[o][3]) != new[n][3].rstrip("\n")]
print(len(pairs), "pairs,", len(bad), "differ")
# The map must cover every commit on both sides, or a missing pair would go unnoticed.
tips = subprocess.run(["git", "rev-list", "21e808d", "8cad71a"], capture_output=True, text=True,
                      check=True).stdout.split()
print("every old commit mapped:", set(pairs) == set(old), "| every new one:", set(pairs.values()) == set(tips))
```

The id replacement, run from the repository root with the files to change as arguments. It
replaces a run of 7 to 40 lowercase hex characters when it starts exactly one old id, by the
new id cut to the same length. Run it once per file. A second run on the decision log or on
this guide would rewrite the old ids they quote on purpose:

```python
import pathlib, re, sys
MAP = pathlib.Path("docs/archive/commit-map-2026-10-21.txt")
rows = [l.split() for l in MAP.read_text().splitlines() if l.strip() and not l.startswith("#")]
pairs = {o: n for o, n in rows[1:] if o != n}
HEX = re.compile(r"(?<![0-9a-fA-F])[0-9a-f]{7,40}(?![0-9a-fA-F])")
for name in sys.argv[1:]:
    path, changes = pathlib.Path(name), []
    def swap(m):
        hits = [o for o in pairs if o.startswith(m.group(0))]
        if len(hits) != 1:
            return m.group(0)
        changes.append(m.group(0))
        return pairs[hits[0]][:len(m.group(0))]
    text = path.read_text()
    path.write_text(HEX.sub(swap, text))
    print(name, len(changes))
```
