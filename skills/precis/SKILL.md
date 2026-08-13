---
name: precis
description: Explain a pull request, merge request, or diff with a self-contained comprehension report covering intent, scope, change composition, hard-to-see behavior, dependencies, genuine risk flags, and verification evidence. Use when asked to explain, summarise, walk through, or prepare a change for human review. Precis complements the host code-review UI and never replaces it.
---

# precis

precis explains a change before a human reviews it. It does not reproduce the
review experience GitHub or GitLab already provides.

The output is one self-contained HTML report and a short Markdown digest. The
report answers the questions that are expensive to answer from a diff:

- What works differently, and why does this change exist?
- What did the ticket promise, what arrived, and what did not?
- How much of the diff is the essential change versus support or mechanical ripple?
- What crosses file or subsystem boundaries?
- Which contracts and callers are affected?
- Did the change introduce a concrete behavioral risk worth checking?
- What was actually verified, and what remains uncertain?

The source host remains the place to inspect code, leave comments, approve, and
track review progress. A precis report contains no diff viewer, reading steps,
checkboxes, progress state, or substitute approval workflow.

## Product boundary

precis is not a code review tool. It is a comprehension tool that prepares a
reviewer to make their own judgement.

**Never produce a verdict.** Precis may identify a genuine risk-bearing decision, but it never produces an
overall verdict, approval recommendation, severity score, or list of generic
concerns. Silence beats padding. If no decision qualifies, write **No risk
flags found**.

Risk flags are not findings. They are narrow claims about a boundary a reviewer
may want to verify. Each one states what could break, points to the changed
decision, and names the test or other evidence that proves the boundary. Use
`PROVEN` when a boundary-focused test exists and `UNPROVEN` when it does not.
An absent test is evidence status, not an automatic conclusion about readiness.

## Scale the output

For a trivial diff under roughly 50 changed lines, one concern, and no contract
or cross-file behavior change, generate only the digest:

```bash
python3 skills/precis/scripts/render_report.py /tmp/precis.model.json \
  --digest precis-1184.md --no-html
```

Everything else gets the report and digest.

## Pipeline

```text
diff -> parse_diff.py -> classify.py -> find_rules.py -> analysis -> build_model.py -> render_report.py
```

### 1. Ingest

Read `references/ingestion.md`. Fetch metadata, the description, linked ticket
when accessible, and the diff. Read-only commands only.

```bash
gh pr diff 1184 > /tmp/precis.diff
```

Read the closest `CLAUDE.md`, `AGENTS.md`, or other repository instructions for
the changed files. Use the repository's language and terms.

### 2. Establish deterministic facts

```bash
python3 skills/precis/scripts/parse_diff.py /tmp/precis.diff \
  | python3 skills/precis/scripts/classify.py - -o /tmp/precis.pre.json
python3 skills/precis/scripts/find_rules.py /tmp/precis.pre.json --root . \
  -o /tmp/precis.rules.json
```

The pre-model is authoritative for paths, hunks, line numbers, counts, and the
classification budget. Do not estimate them or reparse the diff by eye.

### 3. Investigate for explanation

Read `references/analysis.md` and `references/schema.md`. Use the checkout to
trace changed symbols, callers, configuration, and behavior beyond the diff.
Read the linked ticket if possible. When it is unavailable, say that Scope uses
the PR description as its contract.

Focus analysis on what the host UI does not already explain:

1. **Outcome** - one plain statement of what works differently.
2. **Scope** - delivered, not delivered, and extra work against the ticket or
   PR description. A missing item with no stated reason stays explicit.
3. **Change composition** - essential, supporting, and mechanical changed-line
   shares, with a plain explanation of what drove the ripple.
4. **Behavior and structure** - before/after diagrams or a call map only when
   they materially reduce reconstruction work. Every edge needs a hunk id or
   `path:line`. Use `null` when there is nothing useful to draw.
5. **Change map** - concerns in execution or dependency order. Explain why each
   concern changed and what a reviewer should expect there. Keep the file
   inventory collapsed and secondary.
6. **Contracts** - changed signatures, schemas, wire formats, config, flags, or
   CLI surfaces as before/after pairs, including searched callers.
7. **Risk flags** - only concrete decisions involving connection lifecycle,
   routing, error boundaries, observability, auth, state/data flow, guards that
   cover one path, assumed prior steps, client-supplied state, or replayed side
   effects. Do not create a flag merely because the subsystem appears in the
   diff.
8. **Verification** - commands actually run and their real result. Never invent
   output. Name skipped checks and why.
9. **Assumptions and open questions** - only what the evidence cannot settle.

Do not replay the diff. File entries name purpose and consequence in one or two
short sentences. They do not paraphrase each edit.

### 4. Build and render

```bash
python3 skills/precis/scripts/build_model.py /tmp/precis.analysis.json \
  --pre /tmp/precis.pre.json -o /tmp/precis.model.json
python3 skills/precis/scripts/render_report.py /tmp/precis.model.json \
  -o precis-1184.html --digest precis-1184.md
```

`build_model.py` reconciles every count with the deterministic pre-model and
validates evidence references. `render_report.py` validates again and embeds
the model in a single offline HTML file. Never hand-edit the generated HTML.

## Evidence rules

1. Every number comes from the pre-model.
2. Every structural or risk claim points to a hunk id or `path:line`.
3. Every risk flag has `PROVEN` or `UNPROVEN` status and evidence directly
   beneath it. A happy-path test does not prove a boundary.
4. No risk flags is a valid and desirable result when none qualify.
5. A diagram without evidenced edges is omitted.
6. Missing tickets, unread files, elided hunks, binaries, and unavailable
   commands are named in coverage limitations.
7. Never claim overall correctness, safety, or readiness.
8. Nothing leaves the machine except read-only `gh`, `glab`, and `git` access.

## References

| Path | Purpose |
|---|---|
| `references/ingestion.md` | Fetch the change and its contract. |
| `references/analysis.md` | Investigate and write comprehension-first analysis. |
| `references/schema.md` | Model fields and evidence invariants. |
| `references/rules.md` | Use project rules as context without inventing policy. |
| `scripts/parse_diff.py` | Unified diff to deterministic facts. |
| `scripts/classify.py` | Essential, supporting, and mechanical classification. |
| `scripts/find_rules.py` | Find governing repository documents. |
| `scripts/build_model.py` | Reconcile analysis with the pre-model. |
| `scripts/validate_model.py` | Enforce the report contract. |
| `scripts/render_report.py` | Produce the HTML report and digest. |

## Handover

Return the report path and the digest. The digest should lead with outcome,
scope, essential-change share, genuine risk flags or their absence, and the
most useful diagram or concern. Do not add a second review outside the report.
