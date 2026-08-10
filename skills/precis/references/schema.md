# The precis data contract

There are three JSON documents in precis, and one direction of flow:

```
diff ──▶ parse_diff.py + classify.py ──▶ PRE-MODEL ──▶ [analysis, LLM] ──▶ ANALYSIS ──▶ build_model.py ──▶ REPORT MODEL ──▶ render_report.py ──▶ HTML
         deterministic                   (facts)        judgement          (meaning)     (rejoins them)     (facts + meaning)   template only
```

The **pre-model** is what a script can know for certain: paths, hunks, line counts,
rename detection, whether a file is generated or vendored. No judgement.

The **analysis** is the report model with hollow hunks - see
[The analysis file](#the-analysis-file). It is the only document written by hand.

The **report model** is what the report is. Everything the HTML shows comes from it and
nothing else. The template never re-parses a diff, never calls out, never guesses. If the
report should say something, the report model has a field for it.

All three are UTF-8 JSON. The pre-model and the report model carry `schema_version`. This
file is the only place any of the shapes is defined; changing a field here means changing
all three fixtures and both ends of the pipeline in the same commit.

---

## Conventions used below

- **required** fields must be present. **optional** fields may be absent or `null`; the
  template treats absent and `null` identically and hides the corresponding UI.
- Every `*_kind`, `role`, `significance`, `confidence`, `shape`, and `state` field
  is a **closed enumeration**. Most of them steer what the page says rather than
  showing up in it. An unknown value falls back to something neutral rather than
  crashing, but emitting one is a bug.
- Arrays are **ordered and meaningful** unless stated otherwise. `review_pass.steps` is
  the reading order. `review_pass.checks` is ordered by how much precis thinks the item
  warrants a reader's time, without ever saying so numerically.
- Prose fields are **plain text**, not markdown, not HTML. The template escapes them. The
  one exception is `code_ref` spans, described under [Prose and code references](#prose-and-code-references).
- Every prose field has a **character cap**, listed beside it and enforced by
  `validate_model.py`. The caps are the product: a reviewer who wanted paragraphs would
  have read the diff. A field that will not fit its cap is a field trying to be two
  fields, or a thought that is not finished yet.
- Prose written in precis's own voice is scanned for **verdict vocabulary** and rejected.
  See [The verdict scan](#the-verdict-scan).

---

# Part 1 - The report model

## Top level

```json
{
  "schema_version": "1.1",
  "source":        { ... },
  "coverage":      { ... },
  "stats":         { ... },
  "story":         { ... },
  "change_map":    { ... },
  "contracts":     [ ... ],
  "behavior":      { ... },
  "review_pass":   { ... },
  "seams":         { ... },
  "hunks":         { ... },
  "since_previous": { ... }
}
```

| Field | Req | Notes |
|---|---|---|
| `schema_version` | required | `"1.1"`. Renderer refuses a major version it does not know. |
| `source` | required | Provenance and identity of the change. |
| `coverage` | required | What precis actually looked at. Honesty lives here. |
| `stats` | required | Deterministic counts, copied from the pre-model. |
| `story` | required | Headline, beats, shape, tests, intent-vs-diff delta. |
| `change_map` | required | The symbol graph plus every file, grouped by role. |
| `contracts` | required | Every changed contract as a before/after pair. May be empty. |
| `behavior` | required | Before/after. May declare `changed: false`. |
| `review_pass` | required | The pass a reviewer completes: steps, checks, and the skippable remainder. |
| `seams` | required | Independent-concern clusters. May declare `detected: false`. |
| `hunks` | required | Object keyed by hunk id. The single store of diff text. |
| `since_previous` | optional | Incremental mode. Absent in v1 output. |

---

## `source`

Identity, provenance, reproducibility.

```json
"source": {
  "kind": "github_pr",
  "title": "Fix duplicate refunds when Stripe retries a webhook",
  "identifier": "#1184",
  "url": "https://github.com/meridian/orders-service/pull/1184",
  "repo": "meridian/orders-service",
  "author": "dana-kwon",
  "base": { "ref": "main",  "sha": "3f9a1c4e8b2d7a5069c31f8e4b6d2a90c7e15f43" },
  "head": { "ref": "fix/webhook-idempotency", "sha": "b81d0f6a2c94e7358d1a6f0b3e9c4275ad8e1602" },
  "commits": [
    { "sha": "9a2f1c7", "subject": "Add processed-event table and dedupe guard" }
  ],
  "linked_issues": [
    { "id": "MER-2231", "title": "Customers double-refunded on 2024-11-03", "url": "https://..." }
  ],
  "description": "Raw PR/MR body, verbatim, for the intent-delta comparison.",
  "generated_by": "precis 0.1.0",
  "generated_at": "2026-08-08T11:42:09Z"
}
```

| Field | Req | Notes |
|---|---|---|
| `kind` | required | `github_pr` \| `gitlab_mr` \| `git_range` \| `patch_file`. Drives which provenance UI shows. |
| `title` | required | PR/MR title, or a title precis composed for a bare diff. |
| `identifier` | optional | `#1184`, `!77`. Absent for bare diffs. |
| `url` | optional | Link back to the PR/MR. |
| `repo` | optional | `owner/name`, or a local path for `git_range`. |
| `author` | optional | Handle. Absent for bare diffs and patch files. |
| `base`, `head` | required | Each `{ ref, sha }`. `ref` optional, `sha` **required** - this is the reproducibility stamp and it is rendered in the report footer. For a `patch_file` with no SHA information, use `{ "ref": null, "sha": null }` and add a `coverage.limitations` entry saying so. |
| `commits` | optional | Ordered oldest-first. `sha` may be short. Used as intent evidence. |
| `linked_issues` | optional | Issues referenced by the PR body or branch name. |
| `description` | optional | The verbatim PR/MR body. The template shows it collapsed next to the story so a reader can check precis's reconstruction against the source. |
| `generated_by` | required | Tool name and version. |
| `generated_at` | optional | ISO 8601 UTC. |

---

## `coverage`

Where precis admits what it did and did not read. It renders in the footer with the
rest of the provenance; a partial reading also earns one sentence in the masthead,
because that is the one coverage fact that cannot wait for the end of the page.

```json
"coverage": {
  "tier": "core",
  "hunks_total": 51,
  "hunks_read": 22,
  "files_total": 43,
  "files_read": 19,
  "note": "Core and supporting hunks were read in full. Mechanical groups were summarised from file-level statistics only.",
  "limitations": [
    "2 binary files (PNG) could not be analysed.",
    "package-lock.json was classified as generated and not read."
  ]
}
```

| Field | Req | Notes |
|---|---|---|
| `tier` | required | `full` (every hunk read) \| `core` (core + supporting read, mechanical summarised) \| `summary` (file-level only; the change exceeded what could be read). |
| `hunks_total`, `hunks_read` | required | Integers. `hunks_read` counts hunks whose content the analysis phase actually saw. |
| `files_total`, `files_read` | required | Integers. |
| `note` | optional | ≤ 160 chars explaining the tier in plain language. |
| `rules_read` | optional | Array of paths, each ≤ 120. The rule documents the analysis phase read. See below. |
| `limitations` | required | Array of strings, may be empty, each ≤ 120. Each is a specific thing precis could not do. Never a hedge, always a fact. |

### `rules_read`

Three states, three different answers, and the template renders each one
differently:

| Value | Means |
|---|---|
| A list of paths | These documents were read, and their rules were checked against the diff. |
| `[]` | precis looked and the code this change touches has no rule document above it. |
| absent | precis did not look. `limitations` says why. |

A report where this phase ran is worth more than one where it did not, and a
reader can only tell the two apart here. Never list a document that was not
opened. Discovery is `scripts/find_rules.py`; the procedure is
`references/rules.md`.

---

## `stats`

Deterministic. Copied from the pre-model without modification, except `signal_ratio`,
which is computed from the final significance assignments.

```json
"stats": {
  "files_changed": 43,
  "additions": 1247,
  "deletions": 388,
  "hunks": 51,
  "signal_ratio": 0.14,
  "changed_lines_by_kind": {
    "new_logic": 118, "modified_logic": 94, "moved": 210, "rename": 340,
    "formatting": 0, "generated": 812, "content": 61, "deleted": 0
  },
  "changed_lines_by_role": {
    "api": 74, "domain": 188, "persistence": 96, "tests": 302,
    "config": 41, "generated": 812, "docs": 22, "build": 100
  }
}
```

`signal_ratio` is `core changed lines ÷ total changed lines`. It is the number behind the
report's central claim: most of a diff is not the change. Rendered as a percentage.
`changed_lines_by_kind` and `changed_lines_by_role` are optional; nothing on the page
draws them, and they are recomputable from `change_map` if absent.

---

## `story`

The change in a headline and two to four beats, its confidence, and the delta between
what the change says it does and what it does.

```json
"story": {
  "headline": "Refund webhooks are now deduplicated by event id before they reach the ledger.",
  "beats": [
    { "label": "Before", "text": "Stripe retries after 20s. The handler had no guard." },
    { "label": "Impact", "text": "One refund could reach the ledger twice." },
    { "label": "Now",    "text": "`claim_event()` takes the row first. Retries get a 200." }
  ],
  "shape": "bugfix",
  "tests": { "state": "yes", "note": "The retry path is exercised end to end in `test_webhooks.py`." },
  "confidence": "high",
  "evidence": ["pr_description", "linked_issue", "commit_messages", "code"],
  "caveat": null,
  "intent_delta": {
    "stated": "Fix duplicate refunds when Stripe retries a webhook.",
    "also_does": [
      {
        "summary": "Raises the webhook handler timeout from 10s to 30s.",
        "where": ["config/webhooks.yaml"],
        "hunk_ids": ["h31"],
        "kind": "drive_by"
      }
    ],
    "not_done": [
      {
        "summary": "The description mentions backfilling affected refunds; no backfill script or migration appears in the diff.",
        "note": "May be handled outside this change."
      }
    ]
  }
}
```

| Field | Req | Notes |
|---|---|---|
| `headline` | required | One sentence, **≤ 100 chars**, present tense, describes the change not the code's quality. This is the first thing a reader sees. |
| `beats` | required | 2–4 entries, each `{ label, text }`. `label` ≤ 14 chars, `text` ≤ 100 chars. |
| `shape` | required | `feature` \| `bugfix` \| `refactor` \| `docs` \| `chore` \| `mixed`. One word for what kind of change this reads as. `mixed` is itself information: it says the diff carries more than one kind of change, and usually travels with `seams`. |
| `tests` | required | `{ state, note }`. Whether tests **in this diff** exercise the changed behaviour. `state` is `yes` \| `partial` \| `none` \| `n/a`. `note` ≤ 100, optional except for `partial`, where it names what is exercised and what is not. `n/a` is for a change with no runtime behaviour to exercise, and is required exactly when `behavior.changed` is false. |
| `confidence` | required | `high` \| `medium` \| `low`. See the rule below. |
| `evidence` | required | Ordered array from `pr_description`, `linked_issue`, `commit_messages`, `branch_name`, `code`. What the story was reconstructed from. Named in the footer, in a sentence, so a reader can discount accordingly. |
| `caveat` | optional | **Required in practice whenever `confidence != "high"`.** ≤ 160 chars, naming what is missing, e.g. `"No description and single-word commit messages; this story is inferred from the code alone."` |
| `intent_delta` | required | May have empty arrays, must be present. |

### `beats`

The beats are the story. There is no paragraph field, and adding one back would undo the
only thing standing between a reviewer and four sentences they will skim.

A beat is one clause a person would actually say out loud. Labels are free text rather
than an enumeration, because changes come in more shapes than an enum can hold, but three
archetypes cover most of them:

| Shape | Labels |
|---|---|
| A fix | `Before` · `Impact` · `Now` |
| A refactor | `Was` · `Now` · `Watch` |
| A feature | `Need` · `Now` · `Next` |

Two beats is enough when the change is small. Four is the ceiling; a fifth beat means the
change is really two changes, which is what `seams` is for.

Write the beats so the three of them read as one sentence broken into steps. If a beat
could be deleted without the reader losing the thread, delete it.

**Confidence rule.** `high` needs a description or a linked issue that the diff
corroborates. `medium` is code plus useful commit messages, or a description that only
partly matches the diff. `low` is code alone. A `low`-confidence story is still written -
a reader with an inferred story is better off than a reader with none - but the report
says so: the `caveat` sits with the story, and the footer names what the story was read
from. Never present an inferred story as if it were sourced.

### `shape` and `tests`

Two of the questions a reviewer settles before reading anything, answered in the
masthead. `shape` is what kind of change this is, in one word, so a reader knows
which reading posture to take. `tests` says whether the behaviour this diff
changes is exercised by tests *arriving in the same diff* - a statement of fact
about the diff, never an opinion about whether the tests are enough.

- `yes` - tests in this diff exercise the changed behaviour.
- `partial` - some of it. `note` names what is exercised and what is not.
- `none` - no test in this diff touches the changed behaviour.
- `n/a` - there is no changed runtime behaviour to exercise. Required exactly
  when `behavior.changed` is false, and forbidden when it is true.

### `intent_delta`

The scope-creep detector, stated neutrally.

- `stated` - the change's own claim about itself, in one sentence (≤ 160), drawn from the
  description or title. `null` when there is no description. This is quoted from the
  author, so it is exempt from the verdict scan.
- `also_does[]` - things the diff does that the stated intent does not cover. `summary`
  ≤ 120. `kind` is `scope_creep` (a second substantial concern), `drive_by` (a small
  unrelated fix or cleanup), or `incidental` (a consequence of the main change that a
  reader would not predict from the description, such as a config default moving).
- `not_done[]` - things the stated intent claims that the diff does not appear to
  contain. `summary` ≤ 120, `note` ≤ 100. `note` gives the benign explanation when one
  exists.

Both arrays are descriptive. `"description says X; the diff also does Y"` is the voice.
`"this should have been a separate PR"` is not.

---

## `change_map`

Two things: a graph of what calls what, and a complete ledger of every file grouped by
architectural role.

```json
"change_map": {
  "summary": "One decision in the webhook layer, its persistence support, and tests.",
  "graph": { "nodes": [ ... ], "edges": [ ... ] },
  "groups": [
    {
      "id": "g-domain",
      "role": "domain",
      "label": "Webhook handling",
      "summary": "The dedupe guard and the handler that calls it.",
      "files": [
        {
          "path": "src/webhooks/dedupe.py",
          "moved_from": null,
          "status": "added",
          "change_kind": "new_logic",
          "significance": "core",
          "additions": 41,
          "deletions": 0,
          "hunk_ids": ["h1"],
          "note": "The guard itself: an insert-or-conflict on processed_events."
        }
      ]
    }
  ]
}
```

`summary` is optional, ≤ 140 chars.

### `graph` - what calls what

The section a reviewer opens instead of guessing which function in which file matters.
Nodes are **symbols**, not files: the functions, endpoints, tables and types the change
touches, plus enough unchanged neighbours to make them legible.

```json
"graph": {
  "nodes": [
    { "id": "n0", "label": "POST /webhooks/stripe", "kind": "entrypoint",
      "emphasis": "unchanged", "path": "src/api/webhooks.py", "hunk_ids": [] },
    { "id": "n1", "label": "claim_event()", "kind": "function",
      "emphasis": "added", "path": "src/webhooks/dedupe.py", "hunk_ids": ["h1"],
      "note": "Insert-or-conflict; the insert is the lock." },
    { "id": "n2", "label": "processed_events", "kind": "store",
      "emphasis": "added", "path": "migrations/0043_processed_events.sql", "hunk_ids": ["h9"] },
    { "id": "n3", "label": "DuplicateEvent", "kind": "error",
      "emphasis": "added", "path": "src/webhooks/dedupe.py", "hunk_ids": ["h1"] }
  ],
  "edges": [
    { "from": "n0", "to": "n1", "kind": "calls", "emphasis": "added",
      "label": "before the ledger", "evidence": { "hunk_ids": ["h4"] } },
    { "from": "n1", "to": "n2", "kind": "writes", "emphasis": "added",
      "evidence": { "hunk_ids": ["h1"] } },
    { "from": "n1", "to": "n3", "kind": "raises", "emphasis": "added",
      "evidence": { "ref": "src/webhooks/dedupe.py:31" } }
  ]
}
```

**Node fields.** `id` (required, unique), `label` (required, ≤ 34 - the symbol as a person
would say it: `claim_event()`, `POST /refunds`, `processed_events`), `kind` (required),
`emphasis` (required), `path` (optional), `hunk_ids` (required array, empty for unchanged
nodes), `note` (optional, ≤ 80).

**Unchanged neighbours usually live outside the diff, and that is the point.** The caller
that did not change is exactly the context a reviewer is missing when GitHub shows them
one file at a time, so `path` may name any file in the checkout, or be omitted entirely
for something with no single home (a database table, a queue). Two rules keep it honest:
a node whose `emphasis` is not `unchanged` must name the `hunk_ids` that changed it, and a
node carrying `hunk_ids` must have a `path` that appears in `groups`. Nothing links
through to code the report does not list.

**`kind` enumeration** - what a node is. It is not drawn as a shape of its own; the
graph renders as an indented text trace unless it genuinely branches, and when it is
drawn every node is a box:

| Value | Means |
|---|---|
| `entrypoint` | Something the outside world calls: route, CLI command, event handler, exported function. |
| `function` | A function, method, or procedure. |
| `type` | A class, struct, interface, or schema. |
| `store` | A table, collection, queue, cache, or file the change reads or writes. |
| `config` | A setting, flag, or environment value that participates in the path. |
| `external` | A third-party service or library boundary. |
| `error` | An exception, error type, or failure branch worth naming. |

**Edge fields.** `from`, `to` (required, node ids), `kind` (required: `calls` \|
`returns` \| `reads` \| `writes` \| `raises` \| `imports` \| `renders`), `emphasis`
(required), `label` (optional, ≤ 20), `evidence` (**required**).

**Every edge carries evidence.** `evidence` is `{ "hunk_ids": [...] }` when the
relationship is visible in the diff, or `{ "ref": "path/to/file.py:118" }` when it was
found by reading the checkout around the change. An edge you cannot point at a line for is
an edge you do not draw. A wrong arrow costs a reviewer more than a missing one.

**Size.** 2 to 12 nodes, and at least one node whose `emphasis` is not `unchanged`. Twelve
is not a budget to spend; most changes read best at five or six. Include an unchanged node
only when removing it would leave a changed node floating with no context.

**`graph: null`** is legal and is the right answer for a docs-only change, a
configuration-only change, or any diff with no call relationships worth drawing. The
section then renders the ledger alone. A null graph is an honest outcome; an invented one
is not.

**Off-graph files are derived, never declared.** The renderer computes which files in
`groups` have no node on the graph and reports them by group ("6 files ripple from this
and appear on no path: generated client 3, tests 2, lockfile 1"). There is no field for
that count, so it cannot drift out of step with the graph.

### `groups` - the ledger

**Group fields.** `id` (required, unique, referenced by `review_pass.skippable`),
`role` (required), `label` (required, ≤ 40, human phrase, not the role name), `summary`
(optional, ≤ 100), `order_note` (optional, ≤ 100), `files` (required, non-empty).

Groups are the areas the report is organised around: each renders as a section
carrying its own reading steps, checks, and files. Several groups may share a
`role` - a frontend change splits into components, state, and styling, all
`ui`. Order them by where the reading starts; the template leads with the
group that holds step 1 and keeps this order for the rest.

**Three to seven groups.** Fewer than three and the grouping is not doing
anything (one is still right for a genuinely single-concern change); more than
seven and the list itself becomes the thing a reader has to study. Merge related
concerns rather than exceeding seven.

`order_note` says why this area sits where it does in the reading order, when
the reason is not obvious: `"After the domain area: this is the surface that
exposes what it decides."` One clause; leave it off when the order explains
itself.

**`role` enumeration** - the vertical axis of the map:

| Value | Means |
|---|---|
| `api` | Externally reachable surface: HTTP routes, GraphQL resolvers, RPC handlers, CLI entry points, public library exports. |
| `domain` | Business logic and core types. |
| `persistence` | Repositories, queries, ORM models, migrations. |
| `tests` | Any test code, at any level. |
| `config` | Runtime configuration, environment defaults, feature flags. |
| `generated` | Machine-produced: OpenAPI/protobuf clients, snapshots, lockfiles. |
| `docs` | Prose. |
| `build` | Build scripts, CI definitions, dependency manifests, containerfiles. |
| `infra` | Infrastructure as code, deployment manifests. |
| `ui` | Frontend components, styles, templates. |
| `other` | Genuinely does not fit. Use sparingly; a map full of `other` is a failed map. |

**File fields.** `path` (required), `status` (required: `added` \| `modified` \|
`deleted` \| `renamed` \| `copied` \| `mode_changed` \| `binary`), `change_kind`
(required), `significance` (required), `additions`/`deletions` (required integers),
`hunk_ids` (required array, may be empty for binary or mode-only changes), `moved_from`
(optional, required when `status` is `renamed` or `copied`), `note` (optional, ≤ 100;
present for every `core` file).

**`change_kind` enumeration** - what sort of edit a file carries. The report shows a
plain word for the kinds that change how a row is read (`moved`, `rename`, `formatting`,
`generated`, `deleted`) and nothing for the rest, because new and modified logic is what
a changed file is by default. It is never a colour and never a key:

| Value | Means |
|---|---|
| `new_logic` | Behaviour that did not exist before. |
| `modified_logic` | Existing behaviour altered. |
| `moved` | Relocated with its body substantially intact. |
| `rename` | Identifier or path renamed, semantics unchanged. |
| `formatting` | Whitespace, import order, formatter output. |
| `generated` | Machine-produced output, not hand-edited. |
| `content` | Config values, constants, fixtures, prose, manifests. |
| `deleted` | Removal without replacement. |

**`significance` enumeration** - drives what a reader is asked to read:

| Value | Means |
|---|---|
| `core` | The change itself. Belongs in the reading order. |
| `supporting` | Needed to understand the core: the call site that changed shape, the test that pins the new behaviour, the migration the new column needs. Usually in the reading order. |
| `mechanical` | Ripple. Predictable from the core change. Safe to skim. |

**The promotion rule.** When you are unsure whether something is `supporting` or
`mechanical`, it is `supporting`. Hiding one line that mattered costs more than showing
twenty that did not.

---

## `contracts`

Every contract this change alters, as a before/after pair. A contract is a shape
someone outside this diff depends on: an API signature or response, a database
schema, a config default, a wire format, a feature flag, a CLI. Deltas beat
prose everywhere they apply, so these render as two-column tables, never as
sentences.

Required, and an empty array is a statement: precis looked and nothing with an
outside dependant changed shape. That is the answer a reviewer needs most often,
and it belongs in the report rather than being inferable from silence.

```json
"contracts": [
  {
    "id": "c1",
    "kind": "schema",
    "name": "processed_events",
    "before": null,
    "after": "id, event_id UNIQUE, claimed_at",
    "note": "New table; the UNIQUE constraint is what makes the guard atomic.",
    "hunk_ids": ["h9"],
    "callers": {
      "updated": 2,
      "untouched": ["src/reports/refund_audit.py:88"]
    }
  }
]
```

| Field | Req | Notes |
|---|---|---|
| `id` | required | Unique, `c<n>`. |
| `kind` | required | `api` \| `schema` \| `config` \| `wire` \| `flag` \| `cli`. |
| `name` | required | ≤ 60. The surface as a person would say it: `calculate_fee()`, `orders.legacy_refund_id`, `WEBHOOK_TIMEOUT`. |
| `before`, `after` | see note | Each ≤ 120 or `null`. At least one must be non-null: `before: null` is a new surface, `after: null` is a removed one. These are transcriptions of code - a signature, a shape, a value - not prose, and like hunk lines they are exempt from the verdict scan. |
| `note` | optional | ≤ 100, precis's voice, scanned. What a reader cannot see from the pair itself. |
| `hunk_ids` | required | Non-empty. A contract change that is not visible in the diff is not one precis reports. |
| `callers` | optional | The blast radius. See below. |

### `callers` - the blast radius

For a changed surface with callers elsewhere in the repository, say what
happened to them. `updated` (required integer) counts call sites this diff also
changes; `untouched` (required array, may be empty) lists the call sites it does
not, each as a `path:line` ref found by searching the checkout - the same
evidence rule as graph edges. The renderer derives the total, so it cannot
disagree with the parts.

This field is only for surfaces whose callers were actually searched for. A
`callers` you did not grep for is worse than none: an untouched call site the
report missed is exactly the kind of claim that kills trust in the rest of it.
Omit the field when the search was not done, and say so in
`coverage.limitations` when it could not be.

---

## `behavior`

Before/after for the core change only. This section is frequently absent-by-declaration
and that is a correct outcome, not a failure.

```json
"behavior": {
  "changed": true,
  "note": null,
  "summary": "A retried webhook used to reach the refund ledger a second time; it now stops at the dedupe guard and returns 200 without side effects.",
  "before": { "kind": "sequence", "title": "Before", "lanes": [...], "edges": [...] },
  "after":  { "kind": "sequence", "title": "After",  "lanes": [...], "nodes": [...], "edges": [...] },
  "deltas": [
    { "summary": "The ledger write no longer happens on a retry.", "hunk_ids": ["h1", "h4"] }
  ]
}
```

| Field | Req | Notes |
|---|---|---|
| `changed` | required | Boolean. |
| `note` | optional | **Required when `changed` is false.** ≤ 160 chars saying why there is no diagram, e.g. `"Pure extraction: every call path produces the same results as before."` The template renders this instead of the diagrams. |
| `summary` | optional | Required when `changed` is true. ≤ 180 chars naming the behavioural difference. |
| `before`, `after` | optional | Required when `changed` is true. [Diagram objects](#diagram-objects). |
| `deltas` | optional | Callouts of specific differences, each linkable to hunks. `summary` ≤ 110. |

### Diagram objects

precis diagrams are **data, not pictures**. The model names participants, steps, and
relationships; layout and rendering are the template's job. Nothing here has coordinates,
colours, or sizes.

```json
{
  "kind": "sequence",
  "title": "After",
  "lanes": [
    { "id": "stripe",  "label": "Stripe" },
    { "id": "handler", "label": "WebhookHandler" },
    { "id": "db",      "label": "processed_events" },
    { "id": "ledger",  "label": "RefundLedger" }
  ],
  "nodes": [
    { "id": "n1", "lane": "handler", "label": "duplicate detected", "kind": "note", "emphasis": "added" }
  ],
  "edges": [
    { "from": "stripe",  "to": "handler", "label": "charge.refunded (retry)", "kind": "call",   "emphasis": "unchanged" },
    { "from": "handler", "to": "db",      "label": "claim(event_id)",         "kind": "call",   "emphasis": "added" },
    { "from": "db",      "to": "handler", "label": "already claimed",         "kind": "return", "emphasis": "added" },
    { "from": "handler", "to": "stripe",  "label": "200 OK",                  "kind": "return", "emphasis": "unchanged" }
  ]
}
```

| Field | Req | Notes |
|---|---|---|
| `kind` | required | `sequence` (participants over time) or `flow` (a layered graph). |
| `title` | optional | Rendered above the diagram. |
| `lanes` | required for `sequence`, optional for `flow` | Ordered. For `sequence` these are the participants, left to right. For `flow` they are optional swimlane groupings. Each is `{ id, label }`. |
| `nodes` | required for `flow`, optional for `sequence` | For `flow`, the graph vertices. For `sequence`, optional notes anchored to a lane. |
| `edges` | required | For `sequence`, the messages in chronological order (array order is time). For `flow`, the graph edges. |

**Node fields.** `id` (required, unique in the diagram), `label` (required, ≤ 48 chars),
`lane` (optional, must reference a lane id), `kind` (required - `actor` \| `service` \|
`process` \| `decision` \| `store` \| `external` \| `queue` \| `note` \| `start` \|
`end`), `emphasis` (required).

**Edge fields.** `from`, `to` (required - node ids for `flow`, lane ids for `sequence`),
`label` (optional, ≤ 40 chars), `kind` (required - `call` \| `return` \| `async` \|
`error` \| `data`), `emphasis` (required), `hunk_ids` (optional; the code this edge was
read from).

**`emphasis` enumeration.** `unchanged` \| `added` \| `removed` \| `changed`. This is how
before/after reads at a glance: the `after` diagram carries `added` and `changed`, the
`before` diagram carries `removed` and `changed`. Keep both diagrams structurally similar
so the eye can diff them; do not redraw the world.

**Size limits.** A diagram with more than 8 lanes or 20 nodes is not a comprehension aid.
Abstract until it fits.

---

## `review_pass`

The pass a reviewer completes. Three parts in one section: what to **read**, in order;
what to **decide**, once the reading makes sense; and what can be **skipped**, with the
reason it can be.

The template renders every step and every check as a checkbox, keeps the ticks in
`localStorage` under the head SHA, and counts them in one line of plain text. Finishing
the pass is the point. A report that is only read has not been used.

```json
"review_pass": {
  "estimated_minutes": 9,
  "steps": [ ... ],
  "checks": [ ... ],
  "skippable": [ ... ]
}
```

| Field | Req | Notes |
|---|---|---|
| `estimated_minutes` | optional | Integer, for the guided path only, not the whole diff. |
| `steps` | required | Ordered, non-empty. The order is the product. |
| `checks` | required | Array, may be empty. Ordered by how much of a reader's time the item warrants. |
| `skippable` | required | Array, may be empty. Every file not in `steps` must appear in exactly one `skippable` group. The renderer checks this. |

### `steps` - what to read

```json
"steps": [
    {
      "n": 1,
      "title": "The dedupe guard",
      "why": "This is the whole change. Everything else exists to call it or to store its state.",
      "path": "src/webhooks/dedupe.py",
      "hunk_ids": ["h1"],
      "annotations": [
        { "hunk_id": "h1", "new_line": 24, "text": "The insert is the lock; a conflict means another delivery already claimed this event." }
      ]
    }
]
```

**Step fields.** `n` (required, 1-based, matches array position), `title` (required,
≤ 60), `why` (required, ≤ 140 - this is the load-bearing field; a step without a reason to
exist is noise), `path` (optional; the primary file, when the step has one), `hunk_ids`
(required, non-empty), `annotations` (optional).

**Annotation fields.** `hunk_id` (required), `new_line` or `old_line` (optional; the
absolute line number in the new or old file, used to anchor the note beside that line -
omit both to attach the note to the hunk as a whole), `text` (required, ≤ 150).

Annotations are the sharpest place for review-flavoured judgement to leak in. An
annotation says *what this line does* or *what it changes*, never *whether it is right*.

Anchored annotations also decide what a reader sees: a step renders only the
lines they anchor to, one line of context each side, with the full hunk behind
a fold. A step whose annotations anchor to no line shows no code until the
reader unfolds it.

**Reading-order construction rule.** Step 1 is the core change, not the entry point, not
the test, not the migration. A reader who stops after step 1 can say what the change is.
Ordering by call stack, by file path, or by "what runs first" all fail this. Order by
*what you must understand before the next thing makes sense*.

### `checks` - what to decide

The hardest part of the report to keep honest and the most valuable when it is. A check
names a surface the change touches, explains the mechanism, and then hands the reviewer a
question that is theirs to answer.

```json
"checks": [
  {
    "kind": "irreversible_migration",
    "title": "Migration drops orders.legacy_refund_id",
    "why": "The column is dropped in the same migration that backfills processed_events. A rollback does not restore it.",
    "question": "Does anything outside this service still read `orders.legacy_refund_id`?",
    "path": "migrations/0043_processed_events.sql",
    "hunk_ids": ["h9"]
  }
]
```

| Field | Req | Notes |
|---|---|---|
| `kind` | required | Closed enumeration, below. |
| `title` | required | ≤ 80 chars, names the surface, not a problem with it. |
| `why` | required | ≤ 180 chars. The mechanism and its blast radius. |
| `question` | required | ≤ 140 chars, **ends in a question mark**. See the rule below. |
| `path` | optional | Primary location. |
| `hunk_ids` | optional | Links into the code. **Required and non-empty** for the two rule kinds. |
| `rule` | optional | **Required for `documented_rule` and `rule_change`, forbidden on every other kind.** See below. |

**The question rule.** *A check is a question only the reviewer's context can answer.*
precis genuinely does not know the answer, and could not find it in the diff.

| | |
|---|---|
| ✅ | `"Does anything outside this service still read `orders.legacy_refund_id`?"` |
| ✅ | `"Is 30 seconds inside your gateway's own timeout?"` |
| ✅ | `"Which of your consumers parse this payload strictly?"` |
| ❌ | `"Is this retry policy too aggressive?"` |
| ❌ | `"Should the migration be split in two?"` |
| ❌ | `"Is this the right abstraction?"` |

The failures are verdicts wearing question marks. The test: if precis could answer it by
reading more of the diff, it is not a check - it is something precis should have worked
out and put in a step. If the answer depends on a system, a team, or a deployment precis
cannot see, it is a check.

### `skippable` - what can be left

```json
"skippable": [
  {
    "label": "Generated API client",
    "reason": "Regenerated from the OpenAPI spec by `make client`; every change follows from the two new response fields in step 3.",
    "confidence": "high",
    "group_ids": ["g-generated"],
    "files": ["clients/ts/src/models/Refund.ts"],
    "file_count": 11,
    "additions": 812,
    "deletions": 190
  }
]
```

**Fields.** `label` (required, ≤ 40), `reason` (required, ≤ 150 - one line that earns the
skip by explaining the mechanism, not by asserting unimportance), `confidence`
(required: `high` \| `medium`; a group you are not confident about does not belong here,
promote it into `steps` instead), `group_ids` (optional, references `change_map` groups),
`files` (required - the full list, so a reader can always look), `file_count`,
`additions`, `deletions` (required integers), `sample_hunk_id` (optional - one
representative hunk id, rendered behind a fold so a reader can see the shape of
the ripple without reading nineteen copies of it; the strongest form of a
mechanical skip is "the same edit, applied identically across N files - one
shown").

**`kind` enumeration:**

| Value | Flags |
|---|---|
| `behavioral` | Observable behaviour changes for an existing caller or user. |
| `security_surface` | Authentication, authorisation, secrets, crypto, input parsing, deserialisation, permissions, CORS. |
| `irreversible_migration` | Data or schema changes a rollback does not undo. |
| `public_api` | Contract visible outside this codebase: HTTP shape, exported symbols, event payloads. |
| `concurrency` | Locking, ordering, retries, idempotency, background jobs, shared mutable state. |
| `data_loss` | Deletes, truncations, destructive defaults. |
| `external_contract` | Behaviour that depends on or changes an agreement with a third-party service. |
| `dependency_surface` | New or upgraded dependency that reaches runtime. |
| `config_surface` | A default, limit, or timeout that changes production behaviour without code changing. |
| `feature_flag` | Behaviour gated behind a flag, including what happens when the flag flips. |
| `documented_rule` | The diff does something a rule the project has written down forbids, or omits something it requires. |
| `rule_change` | The diff changes the rule text itself. |

### `rule` - the project's own words

The two rule kinds set a document beside the diff, so they have to produce the
document. `rule` is where the project speaks in its own voice.

```json
{
  "kind": "documented_rule",
  "title": "CONTRIBUTING.md puts the policy check before the money moves",
  "rule": {
    "source": "CONTRIBUTING.md:52",
    "quote": "Money moves only after every policy check has passed.",
    "was": null
  },
  "why": "The refund reaches Stripe in `create_refund` before `policy.check` runs inside `record_refund`.",
  "question": "Is this ordering an agreed exception here, or does the rule still hold?",
  "path": "src/meridian/api/refunds.py",
  "hunk_ids": ["h7"]
}
```

| Field | Req | Notes |
|---|---|---|
| `source` | required | `path:line`, the same shape a graph edge's `ref` uses. Where the rule is written. |
| `quote` | required | ≤ 200. The operative sentence, **verbatim**. Never a paraphrase and never a summary of a document. |
| `was` | optional | ≤ 200. The wording this change replaces. **Required when `kind` is `rule_change`.** |

`quote` and `was` are **exempt from the verdict scan**, like `source.title` and
`story.intent_delta.stated`. Rules say "should" and "problem"; precis quotes
them as they are written. The check's own `title`, `why` and `question` are
precis's voice and are scanned as usual.

**Rules are read as of head.** A change that rewrites a rule is following the
new one, so it departs from nothing, and reporting otherwise would tell an
author their change breaks the rule it is replacing. This is why `rule_change`
exists: the edit is worth surfacing without being a departure.

**Every departure points at a changed line.** `hunk_ids` is required and
non-empty for both kinds, which is the graph-edge rule applied here. A rule that
states nothing a changed line can be held against, "keep functions small" and
its relatives, produces no check at all. The procedure is
`references/rules.md`.

**There is no `severity` field, and there will not be one.** Severity is a review verdict.
Array order carries emphasis; the report never scores.

**The wording test.** Every `why` must survive being read aloud to the change's author
without sounding like criticism. `"This path now retries on connection errors as well as
5xx, so a hung upstream produces 3x the request volume it did before"` passes. `"The retry
policy is too aggressive"` does not.

---

## The verdict scan

`validate_model.py` rejects a model whose prose contains, on a word boundary and
case-insensitively:

`should` · `bug` · `issue` · `incorrect` · `consider` · `problem` · `wrong` · `better` ·
`worse` · `suboptimal` · `unnecessary` · `redundant` · `misleading`

This is blunt on purpose. The model running the skill drifts toward reviewing, constantly,
and a validator that exits 1 is the only thing that has ever stopped it. When the scan
fires, the fix is always to say what the code does instead of what you think of it.

**Quoted text is exempt**, because it is someone else's voice and not precis's:
`source.title`, `source.description`, `source.linked_issues[].title`,
`story.intent_delta.stated`, `review_pass.checks[].rule`, and every line of code in
`hunks`. A PR titled "Fix double refund bug" keeps its title, and a house rule that says
"never land a change that should have a test" is quoted as written.

---

## `seams`

Independent concerns inside one change. Always computed, rendered when found.

```json
"seams": {
  "detected": true,
  "note": "Three groups of files that share no symbols and could each stand alone.",
  "clusters": [
    {
      "id": "s1",
      "label": "The HTTP client extraction",
      "summary": "Replaces four ad-hoc requests wrappers with one shared client.",
      "files": ["src/http/client.py", "src/payments/gateway.py"],
      "file_count": 28,
      "changed_lines": 610,
      "independent_of": ["s2", "s3"]
    }
  ]
}
```

`detected` is true when there are **two or more clusters** that share no changed symbols
and no direct call relationship. `note` (≤ 160) is required when `detected` is true. Each
cluster needs `id`, `label` (≤ 40), `summary` (≤ 140), `files`, `file_count`,
`changed_lines`; `independent_of` is optional and lists sibling cluster ids.

This section is a comprehension statement: *"this reads as three changes, here are the
seams"*. It is not advice to split the PR, and must not be phrased as such. The full
report always renders regardless of what seams says.

---

## `hunks`

One store, keyed by hunk id. Every other section refers to hunks by id and never inlines
diff text. This keeps the model small when a hunk is referenced from the change map, a
graph edge, a reading step, a delta, and a check at once.

```json
"hunks": {
  "h1": {
    "id": "h1",
    "path": "src/webhooks/dedupe.py",
    "old_path": null,
    "language": "python",
    "header": "@@ -0,0 +1,41 @@",
    "old_start": 0, "old_lines": 0,
    "new_start": 1, "new_lines": 41,
    "section": "class ProcessedEventStore:",
    "change_kind": "new_logic",
    "significance": "core",
    "truncated": false,
    "lines": [
      { "t": "+", "c": "def claim(self, event_id: str) -> bool:", "old": null, "new": 24 },
      { "t": " ", "c": "    conn = self._pool.acquire()",          "old": 12,   "new": 25 }
    ]
  }
}
```

| Field | Req | Notes |
|---|---|---|
| `id` | required | Matches the key. `h<n>`, stable across a run. |
| `path` | required | Path in the new tree. For a deleted file, the old path. |
| `old_path` | optional | Set when the file was renamed or copied. |
| `language` | optional | Lowercase identifier for syntax tinting (`python`, `typescript`, `sql`, `yaml`, …). Absent means no tinting. |
| `header` | optional | The position half of the `@@` line, e.g. `@@ -24,8 +25,9 @@`. The context git appends after it belongs in `section`; the template renders the two in separate spans, so a header carrying both prints the context twice. |
| `old_start`, `old_lines`, `new_start`, `new_lines` | required | Integers from the hunk header. |
| `section` | optional | The function or class context git puts after `@@`. |
| `change_kind`, `significance` | required | Same enumerations as `change_map`. A file may contain hunks of differing significance; this is how a `core` hunk inside an otherwise mechanical file stays visible. |
| `truncated` | required | `true` when `lines` is a subset of the real hunk. The template shows an explicit marker; it never silently shortens. |
| `lines` | required | Ordered. `t` is `" "` context, `"+"` addition, `"-"` deletion. `c` is the line content **without** the leading marker, tabs preserved, trailing newline stripped. `old`/`new` are absolute line numbers in the respective file, `null` where the line does not exist there. |

Hunks referenced by `review_pass.steps` must have complete `lines`. Hunks that are only
counted (a lockfile, a mechanical group) may be present with `truncated: true` and a short
`lines` array, or omitted from the store entirely as long as nothing references them.

---

## Prose and code references

Prose fields are plain text and are escaped on render. Within them, a backtick-delimited
span is rendered as inline code:

```
"why": "The insert into `processed_events` is the lock; a conflict means a duplicate."
```

That is the only markup the template interprets. No links, no bold, no lists. If a
sentence needs a list, it is two sentences or it belongs in a different field.

---

## `since_previous` (designed, unused in v1)

Incremental mode reserves this shape now so adding it later is additive rather than
breaking. v1 generators do not emit it; v1 renderers ignore it.

```json
"since_previous": {
  "base": { "sha": "..." },
  "head": { "sha": "..." },
  "generated_at": "2026-08-01T09:00:00Z",
  "summary": "Two new commits: the guard moved behind a feature flag and a test was added.",
  "changed_step_ids": [1, 3],
  "new_hunk_ids": ["h52", "h53"],
  "resolved_check_ids": []
}
```

When present, the template marks the affected steps and checks as new or changed since the
previous report, and offers a filter to show only those. Ticks already recorded against
unchanged steps survive.

---

# Part 2 - The pre-model

What `parse_diff.py` and `classify.py` produce. Deterministic: given the same diff bytes
and the same classification rules, byte-identical output. No judgement, no prose beyond
mechanical reasons, no network.

```json
{
  "schema_version": "1.0",
  "source": { ... },
  "stats": { ... },
  "files": [ ... ],
  "hunks": { ... },
  "budget": { ... }
}
```

`source` and `stats` use the same shapes as the report model, minus anything requiring
judgement: `source` has no composed `title` for bare diffs (it is `null`), and `stats` has
no `signal_ratio`.

## `files[]`

```json
{
  "path": "clients/ts/src/models/Refund.ts",
  "old_path": null,
  "status": "modified",
  "additions": 74,
  "deletions": 12,
  "similarity": null,
  "is_binary": false,
  "mode_change": null,
  "language": "typescript",
  "hunk_ids": ["h18", "h19"],
  "classification": {
    "role": "generated",
    "generated": true,
    "vendored": false,
    "lockfile": false,
    "test": false,
    "formatting_only": false,
    "whitespace_only": false,
    "significance_hint": "mechanical",
    "reasons": [
      "path matches clients/**",
      "file header contains 'DO NOT EDIT'"
    ]
  }
}
```

| Field | Notes |
|---|---|
| `status` | `added` \| `modified` \| `deleted` \| `renamed` \| `copied` \| `mode_changed` \| `binary`. |
| `similarity` | Integer 0–100 from git's rename detection, else `null`. |
| `mode_change` | `{ "from": "100644", "to": "100755" }` or `null`. |
| `classification.role` | Best-effort role from path conventions. The analysis phase may override it; when it does, it does so in the report model and the pre-model is left alone. |
| `classification.generated` | Path convention, a `@generated`/`DO NOT EDIT` header, or a known generator output directory. |
| `classification.vendored` | `vendor/`, `third_party/`, `node_modules/`, and friends. |
| `classification.lockfile` | Known lockfile names. |
| `classification.formatting_only` | Every changed line, after normalising whitespace, has an identical counterpart on the other side. |
| `classification.whitespace_only` | Stricter: changes are whitespace exclusively. |
| `classification.significance_hint` | `core` \| `supporting` \| `mechanical`. A **hint**. The analysis phase owns the final `significance` and is expected to disagree sometimes - a one-line change in a generated file is still mechanical, but a one-line change in a lockfile that pins a different major version is not. |
| `classification.reasons` | Machine-readable-ish strings explaining every non-default classification. These exist so a human can audit why something was called mechanical. Never empty for a file hinted `mechanical`. |

## `hunks{}`

Identical to the report model's hunk objects, minus `change_kind` and `significance`
(which require judgement), plus:

| Field | Notes |
|---|---|
| `elided` | `true` when the parser deliberately omitted `lines` for budget reasons. Distinct from `truncated`, which means partially included. |
| `fingerprint` | Stable hash of the hunk's changed lines. Used by incremental mode to tell a re-ordered hunk from a genuinely new one. |

## `budget`

```json
"budget": {
  "tier": "core",
  "max_hunk_lines": 400,
  "max_bytes": 200000,
  "hunks_total": 51,
  "hunks_included": 22,
  "hunks_elided": 29,
  "bytes_included": 48120
}
```

The two scripts split this. `parse_diff.py` shortens any single hunk past
`max_hunk_lines` and marks it `truncated`; it elides nothing and leaves the tier `full`.
`classify.py` then spends `max_bytes` on the hunks worth quoting: when the diff is larger
than the budget it empties hunk bodies, mechanical first, then supporting, then core,
biggest hunk first within each. An elided hunk keeps its header, its counts, and its
place in the file - the report can still say what changed there, it just cannot quote it.

The tier follows from what that cost: `full` when nothing was elided, `core` when only
mechanical hunks were, `summary` once anything else had to go. The analysis phase reads
what it is given and reports the result in `coverage`. The two must agree: `coverage.tier`
is copied from `budget.tier` unless the analysis phase read less than it was offered.

## `warnings`

Array of strings, empty when the diff parsed cleanly. Each one is something the scripts
could not do faithfully: a merge diff they refused, a hunk whose body ran out before its
header said it should, hunks shortened to fit. These are the raw material for
`coverage.limitations` - the analysis phase rewrites them for a reader rather than
copying them, but it may not silently drop one.

---

# Part 3 - The analysis file

The document the analysis phase writes, and the only one written by hand. It is a report
model in every respect but one: its `hunks` entries carry judgement and nothing else.

```json
"hunks": {
  "h1": { "change_kind": "new_logic",      "significance": "core" },
  "h9": { "change_kind": "dependency",     "significance": "mechanical", "quote_lines": 8 }
}
```

| Field | Req | Notes |
|---|---|---|
| `change_kind` | required | Same enumeration as `change_map`. |
| `significance` | required | Same enumeration as `change_map`. Never inferred from `classification.significance_hint` by a script; the hint is a starting point for a reader, not an answer. |
| `quote_lines` | optional | Positive integer. Quote only the first N lines of this hunk and mark it `truncated`. For a long noise hunk that is worth showing the shape of and not worth reading. |

Any other key is an error. In particular `lines` is an error: diff text is copied by
`build_model.py` from the pre-model, never authored here. That is the whole reason the
analysis file exists as a separate document - a retyped diff line is the one mistake in a
precis report that a reviewer cannot catch by reading the report.

`build_model.py` then:

- copies `path`, `old_path`, `language`, `header`, the four line counts, `section`, and
  `lines` from the pre-model hunk with the same id;
- sets `truncated` when the parser truncated the hunk, the budget elided it, or
  `quote_lines` shortened it;
- fills `stats.files_changed`, `additions`, `deletions`, `hunks` and
  `changed_lines_by_role` from the pre-model when absent, and **fails** when present and
  different;
- fills `coverage.tier`, `coverage.hunks_total`, and `coverage.files_total` when absent;
- stamps `source.generated_by` and `source.generated_at` when absent;
- fails on a hunk id the parser never produced, and on a hunk referenced anywhere in the
  document that the analysis did not classify.

It validates the assembled model and writes nothing if that fails.

---

# Part 4 - A minimal valid report model

The smallest document the renderer accepts. Every optional field omitted, every required
field present. Useful as a template smoke test and as a floor for what a degraded run
still produces.

```json
{
  "schema_version": "1.1",
  "source": {
    "kind": "patch_file",
    "title": "Unnamed patch",
    "base": { "ref": null, "sha": null },
    "head": { "ref": null, "sha": null },
    "generated_by": "precis 0.1.0"
  },
  "coverage": {
    "tier": "full",
    "hunks_total": 1, "hunks_read": 1,
    "files_total": 1, "files_read": 1,
    "limitations": ["Patch file carried no commit metadata, so no base or head SHA is recorded."]
  },
  "stats": {
    "files_changed": 1, "additions": 1, "deletions": 1, "hunks": 1,
    "signal_ratio": 1.0
  },
  "story": {
    "headline": "The order confirmation email now uses the customer's locale.",
    "beats": [
      { "label": "Was", "text": "Every confirmation email rendered with a hardcoded `en-US` locale." },
      { "label": "Now", "text": "It renders with the locale stored on the customer record." }
    ],
    "shape": "bugfix",
    "tests": { "state": "none" },
    "confidence": "low",
    "evidence": ["code"],
    "caveat": "This patch arrived with no description or commit messages; the story is inferred from the code alone.",
    "intent_delta": { "stated": null, "also_does": [], "not_done": [] }
  },
  "contracts": [],
  "change_map": {
    "graph": null,
    "groups": [
      {
        "id": "g1",
        "role": "domain",
        "label": "Order notifications",
        "files": [
          {
            "path": "src/orders/notify.py",
            "status": "modified",
            "change_kind": "modified_logic",
            "significance": "core",
            "additions": 1, "deletions": 1,
            "hunk_ids": ["h1"]
          }
        ]
      }
    ]
  },
  "behavior": {
    "changed": true,
    "summary": "Customers with a non-English locale now receive the confirmation email in their own language.",
    "before": {
      "kind": "flow",
      "nodes": [
        { "id": "a", "label": "send_confirmation", "kind": "process", "emphasis": "unchanged" },
        { "id": "b", "label": "render(en-US)", "kind": "process", "emphasis": "removed" }
      ],
      "edges": [ { "from": "a", "to": "b", "kind": "call", "emphasis": "removed" } ]
    },
    "after": {
      "kind": "flow",
      "nodes": [
        { "id": "a", "label": "send_confirmation", "kind": "process", "emphasis": "unchanged" },
        { "id": "b", "label": "render(customer.locale)", "kind": "process", "emphasis": "added" }
      ],
      "edges": [ { "from": "a", "to": "b", "kind": "call", "emphasis": "added" } ]
    }
  },
  "review_pass": {
    "steps": [
      {
        "n": 1,
        "title": "The locale switch",
        "why": "The entire patch is this one argument.",
        "path": "src/orders/notify.py",
        "hunk_ids": ["h1"]
      }
    ],
    "checks": [
      {
        "kind": "behavioral",
        "title": "Confirmation email language now varies by customer",
        "why": "Any customer whose record carries a locale other than en-US now receives different content than before.",
        "question": "Do rendered templates exist for every locale your customer records can hold?"
      }
    ],
    "skippable": []
  },
  "seams": { "detected": false },
  "hunks": {
    "h1": {
      "id": "h1",
      "path": "src/orders/notify.py",
      "language": "python",
      "header": "@@ -90,3 +90,3 @@ def send_confirmation(order):",
      "old_start": 90, "old_lines": 3, "new_start": 90, "new_lines": 3,
      "change_kind": "modified_logic",
      "significance": "core",
      "truncated": false,
      "lines": [
        { "t": " ", "c": "    template = load_template(\"order_confirmation\")", "old": 90, "new": 90 },
        { "t": "-", "c": "    body = template.render(locale=\"en-US\", order=order)", "old": 91, "new": null },
        { "t": "+", "c": "    body = template.render(locale=order.customer.locale, order=order)", "old": null, "new": 91 },
        { "t": " ", "c": "    mailer.send(order.customer.email, body)", "old": 92, "new": 92 }
      ]
    }
  }
}
```

---

# Part 5 - Invariants the renderer checks

`render_report.py` validates these before writing HTML and fails loudly rather than
producing a report that lies:

1. `schema_version` major version is known.
2. Every `hunk_ids` reference resolves to a key in `hunks`.
3. Every `review_pass.steps[].hunk_ids` resolves to a hunk with `truncated: false`.
4. Every file in `change_map` appears either in a `review_pass.steps[].path`/hunk set or
   in exactly one `review_pass.skippable[].files`. Nothing is silently dropped.
5. `steps[].n` equals its 1-based array position.
6. `story.caveat` is present when `story.confidence` is not `high`.
7. `behavior.note` is present when `behavior.changed` is false; `behavior.summary`,
   `before`, and `after` are present when it is true.
8. `seams.note` is present when `seams.detected` is true, and `clusters` has ≥ 2 entries.
9. Every diagram edge endpoint resolves: to a lane id for `sequence`, to a node id for
   `flow`. Every node `lane` resolves.
10. `coverage.limitations` is an array (possibly empty), never a string.
11. Every path in `hunks` appears in `change_map`. The report never shows code from
    a file it does not list.
12. Every prose field is within its character cap.
13. No prose field in precis's own voice contains verdict vocabulary.
14. Every `review_pass.checks[].question` ends in a question mark.
15. `change_map.graph`, when not null, has 2 to 12 nodes, at least one of them not
    `unchanged`; every edge endpoint resolves to a node id; every edge carries `evidence`
    with either `hunk_ids` or a `path:line` `ref`; every node `path` appears in
    `change_map.groups`.
16. A `documented_rule` or `rule_change` check carries a `rule` with a `path:line`
    `source` and a `quote`; a `rule_change` also carries `was`; no other check kind
    carries a `rule` at all.
17. A `documented_rule` or `rule_change` check names at least one hunk.
18. `coverage.rules_read`, when present, is an array of strings.
19. `story.tests.state` is `n/a` exactly when `behavior.changed` is false, and
    `note` is present when `state` is `partial`.
20. Every `contracts` entry carries at least one of `before`/`after`, a non-empty
    `hunk_ids`, and, when `callers` is present, an integer `updated` and an
    `untouched` array of `path:line` refs.
21. A `skippable` group's `sample_hunk_id`, when present, resolves to a hunk in
    the store whose `path` is one of that group's `files`.

A validation failure is a bug in the analysis phase, not something to render around.
