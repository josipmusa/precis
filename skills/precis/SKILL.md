---
name: precis
description: Turn a pull request, merge request, or diff into a self-contained HTML report that a human reviewer completes - what the change does, which parts are the real change, what calls what across files, and a numbered review pass with checkboxes. Use when asked to explain, summarise, walk through, or prepare a PR/MR/diff for review, or when a reviewer needs to get oriented in a large change. Never reviews the code.
---

# precis

precis is not a code review tool. It is a tool that helps humans review code.

The output is one HTML file: no server, no dependencies, openable from a laptop
or attached to a ticket. It exists to get a reviewer oriented in under two
minutes, and then to give them a checklist they can actually finish.

## The one rule

**Never produce a verdict.** No findings, no bugs, no risks-as-accusations, no
"should", no suggestions, no quality opinions, no severity ratings. Not in the
report, not in the chat message around it.

This is not a stylistic preference, it is what the tool is. A reviewer who is
handed conclusions stops reviewing and starts agreeing, which is the exact
failure precis exists to prevent. The line is simple:

- **Allowed:** what the code does, what changed, what it touches, what order to
  read it in, and questions only the reviewer can answer.
- **Not allowed:** whether any of that is good.

You will drift toward reviewing. Every model running this skill does. That is
why `scripts/validate_model.py` fails the run on judgement vocabulary, and why
the rule is repeated in `references/analysis.md` where the prose gets written.

## The pipeline

Four phases, and each one only gets to do its own job.

```
diff -> parse_diff.py -> classify.py ->   you    -> build_model.py -> render_report.py -> report.html
        (facts)          (signal/noise)  (judgement)  (copies the diff)  (template only)
```

1. **Ingest.** Get the diff and its metadata. `references/ingestion.md`.
2. **Parse and classify.** Two deterministic scripts. Never do this by eye.
3. **Analyse.** Write the analysis, which is JSON. `references/analysis.md`.
4. **Build and render.** Two commands. You never copy diff text, and you never
   write HTML.

### 1. Ingest

Read `references/ingestion.md` and follow it. In short:

```bash
gh pr diff 1184 > /tmp/precis.diff        # or glab mr diff, or git diff
```

Read-only commands only. Never comment, push, or modify anything.

### 2. Parse and classify

```bash
python3 skills/precis/scripts/parse_diff.py /tmp/precis.diff \
  | python3 skills/precis/scripts/classify.py - -o /tmp/precis.pre.json
```

Read the result. It is the authority on what changed: every file, every hunk,
every line number, the counts, and a classification with reasons. Do not
re-derive any of it from the raw diff - a second parse by eye is how a report
ends up quoting the wrong line.

### 3. Analyse

Write the analysis against `references/schema.md`, following the procedure in
`references/analysis.md`. It is the report model with hollow hunks: every other
section in full, and a `hunks` entry per hunk carrying only `change_kind` and
`significance`. **Never copy diff lines into it.** `build_model.py` does that,
and a retyped line is a report quoting code the repository does not contain.

The parts that need the most care:

- **The call graph** needs the checkout, not just the diff. Grep for callers of
  the changed symbols and put the unchanged ones on the graph, muted. Every
  edge needs a hunk id or a `path:line`. An edge you cannot point at a line for
  is an edge you do not draw.
- **The review pass** is a checklist someone completes: numbered steps to read,
  then checks to decide, then what can be skipped and why.
- **A check is a question only the reviewer's context can answer.** If precis
  can answer it by reading the file, it is not a check.

### 4. Build and render

```bash
python3 skills/precis/scripts/build_model.py /tmp/precis.analysis.json \
  --pre /tmp/precis.pre.json -o /tmp/precis.model.json
python3 skills/precis/scripts/render_report.py /tmp/precis.model.json -o precis-1184.html
```

`build_model.py` fills in the hunk bodies from the pre-model, checks your counts
against it, validates, and refuses to write a model that fails. `render_report.py`
validates again before writing. If either fails, fix the analysis: the message
names the field. Never patch the template to accommodate one report, never
hand-edit the HTML, never write HTML yourself.

## What lives where

| Path | What it is |
|---|---|
| `references/schema.md` | The contract. Both models, field by field, with the invariants. |
| `references/ingestion.md` | How to get a diff from GitHub, GitLab, git, or a patch file. |
| `references/analysis.md` | How to turn the facts into the report model without reviewing. |
| `scripts/parse_diff.py` | Unified diff to facts. Deterministic. |
| `scripts/classify.py` | Signal, noise, and the content budget. Deterministic. |
| `scripts/build_model.py` | Your analysis plus the pre-model's hunks to one report model. |
| `scripts/validate_model.py` | The contract, executable. Exits 1 on a violation. |
| `scripts/render_report.py` | Model plus template to one HTML file. |
| `assets/template.html` | The only thing that draws. |
| `assets/fixtures/` | Three worked examples: 3 files, 13 files, 40 files. |

Read `references/schema.md` before writing a model. Read the fixture closest in
size to the change in front of you - `small.json`, `medium.json`, or
`monster.json` - to see what a finished model looks like at that scale.

## Rules that hold everywhere

1. **No verdicts.** See above. This is the product.
2. **Every number comes from the pre-model.** Never estimate a count.
3. **Every claim points at code.** Hunk ids or `path:line`, or it does not go in.
   Diff text is copied by `build_model.py`, never typed by you.
4. **Admit what you did not read.** `coverage.limitations` is not optional
   modesty; an elided lockfile, a binary file, a missing PR description, and a
   fork you could not check out all belong there.
5. **When in doubt, promote.** A hunk you are unsure about goes in the reading
   pass. Hiding something real costs the reviewer far more than one extra hunk.
6. **Short fields.** Every prose field has a cap and the caps are enforced. A
   paragraph is a field nobody reads.
7. **Nothing leaves the machine.** No telemetry, no uploads, no network beyond
   `gh`, `glab`, and `git` reading.

## When something goes wrong

| Situation | Do this |
|---|---|
| `gh`/`glab` missing or unauthenticated | Fall back to `git diff` against the merge base, and record the limitation. Omit `intent_delta` when there is no description to compare against. |
| The diff is enormous | `classify.py` elides to fit and sets `budget.tier`. Report the tier honestly in `coverage`; do not describe hunks you were not given. |
| Binary files, or a merge diff | They land in `warnings`. Carry them into `coverage.limitations` in words a reader understands. |
| Validation fails | Read the message; it names the field. Fix the model. Never work around the validator. |
| You cannot answer what the change does | Say so in the story beats and let the review pass carry the reader. An honest "this rewrites X, and the intent behind Y is not stated anywhere" is a useful report. A confident guess is not. |

## Handing it over

Give the reviewer the file path and one or two sentences: the size of the
change, the share of it that is the real change, and where the pass starts.
Nothing else - no summary of your own findings, because you do not have
findings.
