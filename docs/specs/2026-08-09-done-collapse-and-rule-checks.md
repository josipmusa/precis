# Collapsing done steps, and checks against the repo's own rules

Two independent changes, specified together, implemented in that order.

**Goal:** ticking a review-pass item collapses it the way GitHub collapses a viewed
file; and precis reads the rule-bearing docs already in the repository and turns any
place the diff departs from a stated rule into a check the reviewer answers.

---

# Part 1 - Ticking an item collapses it

**Approach:** the tick already carries the "finished" signal. Today it also fades the
card to 55% opacity and strikes the title through while leaving the code fully
expanded, so a finished 40-line step still costs 40 lines of scroll. Collapse the body
instead and drop the fade, which stops earning its place once the card is closed.

## Design

Ticking collapses the card's body and keeps the head. For a step the body is the
`.hunks` container; for a check it is the `.tail` block carrying the question. The head
keeps the ordinal, title, `why` and path, so a reviewer can still see what they did.

A chevron button in the head toggles the body independently of the tick:

- Re-opening a done item does not un-tick it.
- Un-ticking always re-opens.
- Expansion state is transient and is not persisted. Only the ticks live in
  `localStorage`, as today, so a reload shows done items collapsed.

`.step.done { opacity: .55 }`, its `:hover` un-fade, the print override that undoes it,
and the heading strikethrough are all removed.

Print shows every body regardless of tick state. A printed report that hides half the
diff is worse than one that ignores the ticks.

The chevron carries `aria-expanded` and `aria-controls` against an id on the body.

**Files:** `assets/template.html` only, in the CSS block, `tickButton`, `stepItem` and
`checkItem`. No schema change, no script change.

The three shipped examples must be re-rendered from their existing JSON with
`render_report.py`, so the repository does not ship HTML built from an older template.
No network needed.

## Success criteria

- Ticking a step hides its hunks; ticking a check hides its question block.
- The chevron re-opens a done item without changing the tick, and the progress bar and
  copy-summary are unaffected.
- Un-ticking re-opens the body.
- A reload restores ticks with the done items collapsed.
- `@media print` renders every body.
- `tests/test_render.py` covers the collapse markup and the aria wiring.
- The three `examples/*.html` files are regenerated.

---

# Part 2 - Checks against rules stated in the repo's docs

**Approach:** precis is not judging the code here. It quotes one document and points at
a line in another, which is the move `intent_delta` already makes against the PR
description: evidence, not accusation. The verdict stays with the reviewer because the
question precis asks is one it genuinely cannot answer, namely whether the departure is
an agreed exception.

Departures surface as `review_pass.checks`, reusing the tick, the progress bar and the
copy-summary rather than adding a section beside them.

## Design

### Rules are read as of head

If the same PR rewrites a rule and the code follows the new wording, there is no
departure. Where a rule doc is itself in the diff, resolve its text in this order:

1. `git show <head_sha>:<path>`.
2. Failing that (a fork whose objects are not local), the `+` lines in that file's own
   hunks from the pre-model.
3. Failing both, check nothing from that doc and record a `coverage.limitations` entry
   naming it.

### Discovery: `scripts/find_rules.py`

A new deterministic script, in the shape of `classify.py`. Given the pre-model and a
repo root, it walks up from each changed file's directory to the root collecting
conventional rule-bearing names, plus any doc the diff itself touches.

Names it looks for: `CLAUDE.md`, `AGENTS.md`, `.cursorrules`,
`.github/copilot-instructions.md`, `CONTRIBUTING.md`, `STYLE.md`, `CONVENTIONS.md`,
`docs/adr/*.md`, and conventions or style documents under `docs/`.

Output is JSON: each doc with its path, a `reasons` list explaining why it was picked,
whether it appears in the diff, and its hunk ids when it does; plus a `skipped` list.
Count and total bytes are capped, and whatever the cap excluded is reported rather than
dropped.

Scoping to the diff means a monorepo's per-package rules doc wins over the root one.

Discovery is a script and not an ad-hoc grep because `coverage.rules_read` has to be a
record of what was read, not a claim, and because a grep composed fresh each run gives a
different answer each run.

### The two check kinds

| Kind | Fires when |
|---|---|
| `documented_rule` | The diff does something a rule in force at head forbids, or omits something it requires. |
| `rule_change` | The diff changes the rule text itself. |

Both are added to `ATTENTION_KINDS` in the validator and to `ATTN_LABEL` in the
template, labelled "Documented rule" and "Rule change".

### The `rule` object

A check gains one optional object, **required when `kind` is `documented_rule` or
`rule_change`, and forbidden on every other kind**:

```json
{
  "kind": "documented_rule",
  "title": "CLAUDE.md forbids the em dash",
  "rule": {
    "source": "CLAUDE.md:5",
    "quote": "Never use the em dash. Use a plain hyphen instead.",
    "was": null
  },
  "why": "Three added lines in `src/report.py` contain an em dash.",
  "question": "Is this an agreed exception, or does the rule still hold here?",
  "path": "src/report.py",
  "hunk_ids": ["h12"]
}
```

| Field | Req | Notes |
|---|---|---|
| `source` | required | `path:line`, matching the existing `REF_RE` shape used by graph edges. |
| `quote` | required | The doc's voice, verbatim, cap 200. The operative sentence, never a summary of the document. |
| `was` | optional | The prior wording, cap 200. **Required when `kind` is `rule_change`.** |

`quote` and `was` are the doc's voice and are exempt from the verdict scan; rules
routinely say "should" and "problem", and precis must not be blocked from quoting them
accurately. The exemption is added explicitly to `QUOTED` rather than left to the
accident that neither key is in `PROSE_KEYS`. Because `QUOTED` is matched with
`startswith` and check paths carry array indices, `_authored_prose` normalises indices
out of the path (`review_pass.checks[3].rule` matches `review_pass.checks[].rule`)
before the test. Existing entries keep working; `source.linked_issues[0].title` is
covered by the same normalisation.

`title`, `why` and `question` on the same check stay scanned. Those are precis's voice.

### Evidence discipline

`hunk_ids` is **required and non-empty** for both kinds, which is the graph-edge rule
applied here: *a departure you cannot point at a changed line for is a departure you do
not report.*

This is also what keeps the feature from becoming a linter with opinions. A doc saying
"keep functions small" produces no check, because there is no verbatim rule the diff
contradicts and no line to point at.

For `rule_change`, the hunks are the doc's own; `rule.source` names that doc.

### `coverage.rules_read`

A new optional array of paths, each capped at 120, rendered in the provenance strip as
`Rules read: CLAUDE.md, CONTRIBUTING.md`.

- Present and non-empty: these docs were read.
- Present and empty: precis looked and found no rule documents.
- Absent: precis did not look, which obliges a `limitations` entry saying why.

That three-way distinction is why this belongs in `coverage`: a reviewer can tell a
clean PR from one where the check never ran.

### Documentation

A new `references/rules.md` carries the procedure: discovery, head-state resolution,
what counts as a checkable rule, the evidence rule, and how to word a check so it stays
a question. `references/analysis.md` points at it from its `checks` section. `SKILL.md`
gains the pipeline step and a row in "What lives where".

`schema.md` gains the `rule` object, the two kinds, `coverage.rules_read`, and the new
renderer invariants.

### Error handling

No checkout, no `git`, or a discovery run that finds nothing all degrade identically:
no rule checks, `rules_read` absent, one plain `limitations` entry naming what was
missed. The capability never blocks a report.

## Out of scope

- Re-analysing the three shipped examples so they carry rule checks. That needs `gh`
  and a checkout of each upstream repository. Both new fields are optional, so the
  examples stay valid and correctly show no `Rules read` line: they were generated
  before the capability existed.
- Any rule that cannot be quoted verbatim and anchored to a changed line.
- Editing, proposing edits to, or summarising the rule documents. Precis stays
  read-only and quotes only the operative sentence.

## Success criteria

- `find_rules.py` discovers rule docs, prefers the ones nearest the changed files,
  includes docs the diff touches, honours its caps, reports what it skipped, and gives
  byte-identical output for the same input.
- The validator accepts a well-formed `rule` object, and rejects: the two new kinds
  without one, `rule` on any other kind, a malformed `source`, `rule_change` without
  `was`, and either kind with empty `hunk_ids`.
- A rule quote containing "should" validates; the same word in the check's `why` still
  fails.
- The renderer draws the quote with its `path:line` attribution, visually distinct from
  precis's own prose, and the was/now pair for `rule_change`.
- `coverage.rules_read` renders in the provenance strip, and its empty and absent cases
  differ as specified.
- `assets/fixtures/medium.json` carries one `documented_rule` check and a `rules_read`
  list, and all three fixtures still validate.
- `tests/test_docs.py` still passes, including the reference-set completeness check that
  requires `rules.md` to be named in `SKILL.md`.
- The full suite passes.
