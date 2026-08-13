# Report model

The report model separates deterministic facts from explanatory analysis. The
HTML is a view of this model and must never be hand-authored.

The current compatible schema version is `1.2`. The comprehension fields below
are additive while the old review-pass carrier is retired. The renderer ignores
that carrier and does not expose a diff viewer or review workflow.

## Top level

```json
{
  "schema_version": "1.2",
  "source": {},
  "coverage": {},
  "stats": {},
  "story": {},
  "scope": {},
  "composition": {},
  "change_map": {},
  "contracts": [],
  "behavior": {},
  "risk_flags": [],
  "verification": {},
  "assumptions": [],
  "open_questions": [],
  "seams": {},
  "review_pass": {},
  "hunks": {}
}
```

`scope`, `composition`, `risk_flags`, `verification`, `assumptions`, and
`open_questions` are the new comprehension contract. They are optional only so
stored 1.x reports remain renderable. New reports populate all of them.

## Source, coverage, and stats

`source` records kind, title, identifier, URL, repository, author, base and head
revisions, linked issues, original description, generator, and timestamp.

`coverage` records the deterministic budget, files and hunks read, repository
rules read, and limitations. Missing tickets, elided hunks, binaries, and
unavailable commands belong in limitations.

`stats` owns all counts. `files_changed`, `additions`, `deletions`, and `hunks`
come from the pre-model. `signal_ratio` is essential changed lines divided by
all changed lines.

## Story

`story.headline` is the outcome. `story.beats` is an ordered list of two to four
`{label, text}` entries explaining the causal chain. `shape`, `tests`,
`confidence`, `evidence`, and `caveat` disclose what the explanation rests on.
`intent_delta` remains as a compatibility source for old reports; `scope` is
the rendered contract comparison for new reports.

## Scope

```json
{
  "contract": "Ticket ACME-42, read on 2026-08-13.",
  "delivered": [{"item": "Reject expired sessions"}],
  "not_delivered": [{"item": "Backfill old sessions", "reason": "Deferred in the ticket"}],
  "extra": [{"item": "Rename the session helper", "reason": "Rode along with the change"}]
}
```

Every group is an array. Entries may be strings or `{item, reason}`. `contract`
states which source was used. Never infer a reason for missing scope.

## Composition

```json
{
  "summary": "One validation rule drives adapter updates and regenerated fixtures.",
  "essential": 18,
  "supporting": 71,
  "mechanical": 143
}
```

Counts are changed lines, not files or hunks. They are non-negative integers and
must sum to `stats.additions + stats.deletions`.

## Change map and diagrams

`change_map.groups` is ordered by execution or dependency flow. Each group has
an id, role, label, short narrative, and complete file inventory. Each file has
path, status, classification, additions, deletions, and hunk ids.

`change_map.graph` is `null` unless a relationship changed. Graph nodes are
limited to 12. Every edge carries evidence through a hunk id or `path:line`.

`behavior.changed` decides whether before and after diagrams exist. Sequence
diagrams show ordering; flow diagrams show branching and state. When runtime
behavior did not change, `behavior.note` says so plainly.

## Contracts

Each contract has id, kind, name, before, after, note, and non-empty hunk ids.
Optional caller evidence records the number updated and the untouched
`path:line` references found by an actual search.

## Risk flags

An empty array means no risk flags were found and is a complete result.

```json
{
  "status": "PROVEN",
  "title": "Refresh rejection clears the existing session",
  "explanation": "If refresh fails after a session was loaded, stale state could remain visible.",
  "refs": ["src/session.ts:84"],
  "evidence": {
    "summary": "The rejection test asserts that session state is cleared.",
    "refs": ["tests/session.test.ts:211"]
  }
}
```

Allowed statuses are `PROVEN` and `UNPROVEN`. Every flag has a changed-code
anchor and evidence object. `PROVEN` requires at least one boundary-focused
evidence reference. `UNPROVEN` states that the relevant boundary lacks such
evidence. No severity or readiness field exists.

## Verification

```json
{
  "commands": [
    {"command": "pytest -q", "status": "PASS", "output": "84 passed in 2.1s"}
  ],
  "skipped": ["Integration tests require credentials not present in this checkout"]
}
```

Statuses are `PASS`, `FAIL`, and `NOT_RUN`. Output is copied from the command and
kept concise. `skipped` is always an array.

## Assumptions and open questions

Both are arrays of short strings. Assumptions name missing evidence. Open
questions name decisions the report cannot settle. Empty arrays are preferred
to filler.

## Evidence and prose invariants

1. Every count comes from or reconciles with the pre-model.
2. Every hunk id resolves to a parsed hunk.
3. Every `path:line` has the exact `path:line` shape.
4. Every graph edge and risk flag is anchored to code.
5. Every `PROVEN` risk has boundary-focused evidence.
6. Empty risk flags are valid and render as `No risk flags found.`
7. Authored fields respect their character caps.
8. Quoted ticket text, repository rules, and code are clearly distinguished
   from Precis prose.
9. The renderer refuses an invalid model.
10. The report never exposes code-review steps, checkboxes, or approval state.

## Minimal valid report

- A minimal valid report model is available in `assets/fixtures/small.json`.
  Stored fixtures predate the additive comprehension fields and exercise
  backward compatibility.
