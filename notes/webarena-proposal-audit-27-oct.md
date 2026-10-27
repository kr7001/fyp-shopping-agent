# WebArena proposal: submission notes, 27 October 2026

Status: **issue submitted and verified**: [WebArena-Verified #60](https://github.com/ServiceNow/webarena-verified/issues/60), posted by `kr7001` on 27 October 2026 at 22:36 Singapore time after the student's explicit approval. No PR has been submitted or merged by this review. The exact submitted body remains in `notes/webarena-variant-proposal-27-oct.md`; this audit file was not published.

Title: **Proposal: optional shopping tasks with interaction-gated variant prices and availability**

Destination: [ServiceNow/webarena-verified](https://github.com/ServiceNow/webarena-verified/issues).

## Corrections to the handover and old proposal

The handover says no submission plan was recorded. A substantial plan already exists in `docs/guides/webarena-contribution.md`, first committed on 21 October (`416cf74`, with a later history-link update at `28beb4f`). A plan is not a submitted contribution. No proposal matching the extension was found in the upstream issue/PR title-and-body search before posting issue #60.

The old issue draft claims a ready Apache-2.0 extension, example tasks in upstream's format, and a universal catalogue limitation. Those claims are premature. This draft describes the prototype, limits the measurement to the audited instance, and treats task conversion, evaluator integration, clean-container reproduction and licence packaging as work remaining. It does not make claims about maintainer inactivity or promise a response/merge date.

The user-agent theme selection does not isolate all environment changes: new catalogue products and store settings affect the shared instance. The draft therefore proposes a separate opt-in instance. The theme carries an encoded price table, so the extension tests initially rendered observation access, not resistance to arbitrary script inspection.

## What was verified

- `gh repo view kr7001/fyp-shopping-agent --json nameWithOwner,isPrivate,defaultBranchRef,url` returned public visibility and default branch `main`.
- `gh api repos/kr7001/fyp-shopping-agent/branches/dev --jq '.commit.sha'` returned `98988269fce34e504d72631f0b97fe15d53f8820`, matching local `origin/dev`, dated 21 October.
- The issue links use that immutable public commit and files confirmed in its `env` directory. The local branch was 108 commits ahead when this review began. The newer `generate_aplus.py`/design-B work is not in that public snapshot and the draft does not link to it or claim it is already published.
- All 59 items returned by the upstream `issues?state=all&per_page=100` API endpoint were checked by title and body for `interaction.gated`, `variant.dependent`, `configurable product` or `variant pric`; no match was returned. This includes PRs returned by that endpoint. It is a duplicate search, not proof that no related work exists elsewhere.
- The current [contribution guide](https://github.com/ServiceNow/webarena-verified/blob/main/CONTRIBUTING.md) asks contributors to search existing issues and run formatting/type checks and pytest for a PR. The [shopping documentation](https://servicenow.github.io/webarena-verified/v1.2.3/environments/shopping/) identifies the `am1n3e/webarena-verified-shopping` image. The [configuration documentation](https://servicenow.github.io/webarena-verified/getting_started/configuration/) allows a custom dataset path. These support the proposed destination and integration route; they do not establish that our tasks already integrate.
- The local source was read: `env/README.md`, `seed_variants.py`, `generate_aplus.py`, `install_gated_theme.py`, the configurable template and `check_market.py`. No protected stage-1 result files were opened.

## Submission and meeting wording

The student explicitly approved posting the prepared body on 27 October. The following command was executed once successfully; do not rerun it to create a duplicate:

```bash
gh issue create --repo ServiceNow/webarena-verified \
  --title 'Proposal: optional shopping tasks with interaction-gated variant prices and availability' \
  --body-file notes/webarena-variant-proposal-27-oct.md
```

The returned URL was `https://github.com/ServiceNow/webarena-verified/issues/60`. A subsequent `gh issue view 60 --repo ServiceNow/webarena-verified --json number,title,body,url,author,state,createdAt` verified the exact title, author `kr7001`, state `OPEN` and creation timestamp `2026-10-27T14:36:38Z`. Python verified that the returned body equals the approved file byte for byte as UTF-8 text; its SHA256 is `c51229c7abcffb4a5f5d514e58f2f773d918357171249acdf025093430d35af4`.

Meeting wording: “I proposed the extension to the WebArena-Verified maintainers in issue #60. This is a submitted proposal; no upstream PR has been merged.”

A later submitted PR is “under review.” Use “merged upstream” only after verifying a merge. The student confirmed on 27 October that the **first report/full draft is due 6 November**; the report deadline must not depend on a maintainer reply.

## Before a first PR

1. Agree the initial scope: a dedicated opt-in shopping instance, one fixture, and a few deterministic retrieval tasks.
2. Package only the required environment tools; remove experiment-repository import dependencies and make URL/container/fixture names explicit.
3. Preserve existing theme rules and settings when installing/removing. The current installer deletes all `design/theme/ua_regexp` rows, and its SQL/cache subprocesses do not raise on failure. A portable package must address that before claiming safe installation. See `env/install_gated_theme.py:55`, `:67`, `:77` and `:88`.
4. Retain the existing fixture-scoped product teardown (`seed_variants.py:482`) and test it alongside configuration restoration. The README's broad description of deleting every `IGR-` product is misleading: the implementation deletes only SKUs in the selected fixture and leaves attributes in place.
5. Reproduce on a fresh pinned image, recording its digest and configuration, then verify both observation modes and teardown. This has not been done in this review.
6. Convert tasks to the current upstream schema and test correct answers, wrong target variants, wrong sellers, extra alternatives, availability and price tolerance. Do not claim exact-price scoring until its configured tolerance has been checked.
7. Establish licence/notice files for student-authored code and the Magento-derived template before redistributing a standalone package. The repository currently has no top-level extension licence.
8. Run the checks required by upstream's current contribution guide and open the smallest PR the maintainers request. No clean PR completion time is guaranteed by the existing prototype.
