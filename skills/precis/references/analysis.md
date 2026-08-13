# Analysis procedure

This phase turns deterministic diff facts, repository context, and the stated
ticket contract into an explanation. It does not reproduce the diff or conduct
the review for the reader.

## Read first

Read, in order:

1. the pre-model from `classify.py`;
2. PR or MR metadata and description;
3. the linked ticket when accessible;
4. repository instructions selected by `find_rules.py`;
5. changed files and the unchanged callers needed to understand them.

Use project terminology. Record missing sources in `coverage.limitations`.

## Investigation order

### 1. Reconstruct the outcome

Write one sentence describing what works differently now. State behavior, not
implementation. Then add two to four short story beats explaining the causal
chain. Separate sourced intent from inference with `story.confidence`,
`story.evidence`, and `story.caveat`.

### 2. Compare contract and delivery

Use the linked ticket as the contract. If it is unreachable, use the PR
description and say so in `scope.contract`.

- `delivered`: promised items present in the diff.
- `not_delivered`: promised items absent from the diff. Preserve any stated
  reason. If there is none, write `No reason stated` rather than inventing one.
- `extra`: work in the diff the contract did not ask for.

Name items tersely. Scope is an inventory, not another summary.

### 3. Explain change composition

Classify every changed line through its hunk as:

- `essential`: the decision or behavior the change exists to introduce;
- `supporting`: tests, adapters, migrations, or nearby changes needed for it;
- `mechanical`: generated output, formatting, renames, lockfiles, or repeated
  ripple that adds no new decision.

The three counts must equal additions plus deletions. Explain the main source
of ripple in `composition.summary`. This is a prominent part of the report.

### 4. Trace what code hides

Use the checkout, not only the diff. Search for changed symbols and relevant
callers. Add a call graph only when the change adds, removes, or redirects a
relationship that would otherwise be tedious to reconstruct. Every edge needs
a hunk id or `path:line`. Use `graph: null` when no useful relationship changed.

For runtime behavior, create before and after diagrams only when ordering,
branching, async work, or state transitions matter. A diagram of unchanged
structure is decoration and should be omitted.

### 5. Build the concern map

Group files by concern and order groups by execution or dependency flow. Each
group gets a short narrative answering:

1. Why did this concern change?
2. What consequence or relationship should the reader understand?

File notes are one sentence at most. Do not paraphrase edits. The inventory is
secondary and collapsed in the report.

### 6. Identify changed contracts

Record every changed surface used outside its defining code: API signatures,
schemas, wire formats, config, flags, and CLI contracts. Show before and after.
Search for callers and report untouched callers only when that search was
actually performed.

### 7. Evaluate risk flags

Start with an empty list. A flag is allowed only when a changed decision creates
a concrete boundary on one of these axes:

- connection or stream lifecycle;
- routing or error boundaries;
- authentication or authorization;
- observability relied on during failure;
- state ownership or cross-component data flow;
- a guard that covers one path but not another;
- logic that assumes an earlier step ran;
- trust in client-supplied state;
- retry or replay of a side effect.

Subsystem presence alone is not enough. A normal auth edit is not automatically
a risk flag. When nothing qualifies, use `risk_flags: []`; the renderer states
`No risk flags found.`

Each flag includes:

- `status`: `PROVEN` or `UNPROVEN`;
- `title`: the boundary, not a dramatic conclusion;
- `explanation`: what could break and under which condition;
- `hunk_ids` or `refs`: the changed decision;
- `evidence.summary` and `evidence.refs`: the boundary-focused test or the
  explicit absence of one.

A happy-path test does not prove rejection, skipped ordering, idempotency, or
failure cleanup. `UNPROVEN` is a proof state, not a readiness verdict.

### 8. Record verification

Run relevant repository checks when authorized and practical. Capture the exact
command, `PASS`, `FAIL`, or `NOT_RUN`, and concise real output. Never invent or
clean up output. List skipped checks with reasons.

### 9. Close with uncertainty

`assumptions` contains claims the report had to make because a source was
missing. `open_questions` contains decisions only a reviewer or author can
settle. Empty arrays are valid. Do not pad them.

## Writing rules

- Plain language and short fields.
- Summary, not replay.
- Facts point to code.
- No overall quality, safety, approval, or readiness verdict.
- No generic concerns.
- No risk flag without a concrete boundary and evidence status.
- No diagram that does not reduce comprehension work.
- No hidden omission. Coverage names what was not read.

## Compatibility fields

The current built model still carries hunk classification and may carry the
former `review_pass` fields so existing 1.x fixtures can be rebuilt
deterministically. They are migration data only. New analysis omits
`review_pass`; `build_model.py` supplies a mechanical compatibility carrier.
The HTML presentation model strips it and all hunk bodies before rendering.
