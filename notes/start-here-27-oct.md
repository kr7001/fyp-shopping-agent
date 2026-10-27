# Your next steps before the 28 October meeting

Prepared 27 October 2026. Stage-1 results remain blinded. No new paid run or public issue was started by this preparation.

## What you are checking

You are judging **the answer a shopping agent already gave**. You do not need to visit the shop, rerun an agent, calculate all the prices yourself, understand the code, or decide which method you prefer.

For each row, you have three things: the shopper's question, the expected answer (`key`), and the agent's reply. Decide whether the reply's **final committed answer** satisfies the frozen rules. The arm, model, round and automatic score are hidden. Style can still give clues; this is a stated limitation of blinding.

The `key` column is safe and necessary to read. The separate `.key.json` file is different: it reveals arm identities. Keep that file, `.analysis.json`, and `second-reader.verdicts.csv` closed until every verdict is locked. I have not opened those files or filled any of your scores.

## Step 1 — use the one-answer reader

Open [the offline review reader](../report/hand-review-27-oct.html) in Chrome or Safari. If the link opens source text, find `report/hand-review-27-oct.html` in Finder and use **Open With → Google Chrome** or **Safari**. No server, account or API key is needed.

1. Expand **Read this before starting**, then **Full frozen reading rules**. Read those once. The original rules are also in [claim2-reading-rules.md](../docs/content/claim2-reading-rules.md); its historical DRAFT heading does not make it a new opportunity to change the rules.
2. Read the **Question**, **Expected answer key**, then **Agent's answer**.
3. Click **Correct**, **Not correct** or **Unscorable**. Add a note if a case is doubtful.
4. Click **Next**. You can return to earlier answers. **Jump to first unfinished** finds the first blank verdict.
5. At every break, click **Download reviewed CSV**. Keep the downloaded file. Browser storage helps you resume in the same browser, but the downloaded CSV is the portable copy.

The original CSV is not overwritten by a browser download. Downloads may acquire names such as `claim2b-stage1.sheet (1).csv`; that is normal. Keep the latest one and tell me its path when you are ready to import it. Do not regenerate the review HTML while working, switch browsers, clear browser storage, or use two review tabs at once.

If you prefer Numbers/Excel, use `experiments/results/claim2b-stage1.sheet.csv`, change only `hand_verdict` and `note`, and export CSV UTF-8. Keep all six column names, row codes, questions, keys and answers intact. Do not sort just one column.

## Step 2 — make the decision

| Verdict | Use it when |
|---|---|
| `correct` | The final committed answer supplies what this question's rule requires, matching the key. |
| `not correct` | It is wrong or incomplete, refuses an answerable question, gives only advice, or leaves incompatible alternatives unresolved. |
| `unscorable` | The reply is empty, unreadable/garbled, or about another question. **Not** merely difficult to judge. |

Read the final claim rather than every number mentioned during working. If it corrects an earlier answer, use the correction. “Probably” does not make a committed answer unscorable. A wrong seller listed only among rejected candidates does not make the final answer wrong.

Made-up practice examples, **not rows from your experiment**:

- If the key asks for a price of `$23.40`, “The banner said $12, but after selecting M the price is $23.40” gives the correct price. The rejected $12 is working.
- For that price question, “Either $23.40 or $24.10; I cannot tell” is **not correct**: no single answer is chosen.
- For a seller-and-price question requiring Nora at `$23.40`, “Nora is cheapest” is **not correct** if the rule also requires the price.
- For a count question with `value: 5`, “I checked 15 listings; five can sell M” gives the right count. The number checked is not the answer.

Pay attention to the per-question rules: a price-only question does not judge an optional seller, but cheapest-seller questions require both seller and price; an existence question answered yes needs an acceptable witness seller; top-three needs exactly three accepted sellers with their prices; the promotion-check question needs **no plus the actual price**. Do not apply a stricter rule because it seems more natural.

The key's shorthand: `any` = acceptable seller names; `not_any` = sellers that would be wrong if offered as the answer; `price`/`value` = required number or yes/no; `items` = the required three seller/price pairs; `trap` = a false label figure. The frozen per-question table decides what must be present.

There are **184 answers, about 21,960 words**. Budget roughly 2–3 hours initially, with breaks, and allow more if you need it. This is a planning estimate, not a time limit. Try a first block of 10 to learn the rules, then blocks of 30–40. Do not rush to agree with what you think the research should show. I can clarify a rule with made-up examples; I should not supply your actual verdicts and then call them an independent human review.

## Step 3 — save, validate, then unblind

When the page says **184 reviewed · 0 remaining**, download once more and say: “My hand review is complete; the file is at [path].” I can validate and import it, run the two analyses, explain their results, and update tomorrow's page and the report.

The helper rejects altered evidence, missing/duplicate codes, invalid verdicts, and an older import that would erase completed grades. It backs up the original CSV before importing. It never consults hidden arm mappings during validation/import.

If you want to do it yourself, from the project folder:

```bash
# Replace the example path with your newest download. Quotes matter if it has spaces.
python3 tools/hand_review.py --import-verdicts '/Users/kaironglee/Downloads/claim2b-stage1.sheet.csv'

# Only after every row is finished: this deliberately unblinds the results.
python3 tools/hand_review.py --score
```

The second command refuses an incomplete sheet, calls the handover's two analysis programs, and writes `experiments/results/claim2b-stage1.hand.txt` and `experiments/results/claim2b-stage1.agreement.txt`. It makes no paid model call. Do not run `claim.py --sheet`: the review sheet already exists.

The 184 review rows are not the whole experimental denominator. Keyless decline questions, block closures and other predeclared exclusions have separate accounting. The frozen design schedules 227 question/arm/round slots; the handover reports 198 executed browser runs. We will reconcile those categories from the unblinded outputs, rather than treating missing sheet rows as failures or silently discarding them.

## The rest of today

1. **Rest first if needed.** A rested review is more valuable than another overnight run whose results cannot be read in time.
2. **Finish your review**, download it, then let me calculate the results. If you cannot finish tonight, keep results explicitly pending for the meeting; do not substitute automatic scores for the planned human verdict of record.
3. **Read and rehearse [the meeting brief](meeting-28-oct-brief.md)** for 20–30 minutes. Focus on the literature gap, the block's input → decision → plan pipeline, and what changed since 21 October. Use [the updated meeting page](../docs/update-28-oct.html).
4. **Review [the WebArena issue draft](webarena-variant-proposal-27-oct.md).** It is ready for a posting decision. Until an issue URL exists, say “proposal drafted,” not “proposed to the maintainers,” “submitted,” or “contributed.”
5. **Bring [the replication plan](replication-prep/protocol-draft-27-oct.md)** to the supervisor. It is a draft for a second market, not an overnight run already in progress. Its estimated $16.53 cost is uncertain, and a $20 stop budget may not complete it.

The 6 November deadline is inconsistent in the old notes: the 21 October update says abstract; the handover says report. Prepare both by 5 November unless the actual assessment instructions confirm otherwise. Ask about the exact deliverable, time and submission channel tomorrow. Do not let an upstream PR or a new experiment delay the required submission.

## What is ready, and what is deliberately still pending

- Changes are isolated on `codex/meeting-28-oct-review`; the earlier dirty files and modified agent submodule were preserved. The private report remains outside Git, with its original source/PDF backed up.
- The revised report compiles to 42 pages. All 52 result placeholders remain, and citation-key checks are not a full citation-content audit. Its wording patch is `report/codex-wording-27-oct.patch`.
- Fixed a CSV import bug: the claim analyser now accepts the UTF-8 byte-order mark that Excel may write. No scoring rule or frozen agent behaviour changed.
- The helper passed eight synthetic tests and real Chromium checks of selections, navigation, reload persistence and CSV export. The agreement suite passed 17 tests, protocol analysis passed 109, and the stage-command suite's 25 tests passed when the watchdog had required process visibility. An independent reviewer checked the helper and meeting/scoring instructions.
- Docker Desktop and the existing shop were restarted. Wexcombe passed eight free checks of cards, prices, pagination and order; this is not a new run or a full new-market preflight. The replication still needs its separate seed-selection configuration, frozen design, exact-command verification and explicit spending approval.
