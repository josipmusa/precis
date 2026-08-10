# Turning facts into a report model

The pre-model says what changed. This phase says what it means, in the shape
`references/schema.md` defines. It is the only phase with judgement in it, and
the only one that can produce something a reviewer would resent.

What you write is the **analysis file**: the report model with hollow hunks.
Every section in full, and a `hunks` map whose entries carry only the judgement
about each hunk:

```json
"hunks": {
  "h1": { "change_kind": "new_logic", "significance": "core" },
  "h2": { "change_kind": "modified_logic", "significance": "core" },
  "h9": { "change_kind": "dependency", "significance": "mechanical", "quote_lines": 8 }
}
```

`build_model.py` fills in the paths, headers, line numbers, and the diff lines
themselves from the pre-model. **Do not copy diff text into the analysis.** Not
one line: a line you retype is a line the report quotes that the repository may
not contain, and it is the one error in a precis report that a reviewer cannot
catch by reading. `quote_lines` is the only lever you have over the copy - it
quotes the first N lines of a long noise hunk and marks it truncated. A hunk you
send a reviewer to read in `steps` may not be truncated, and the validator says
so if you try.

Every hunk you mention anywhere has to appear in the map. That is deliberate:
the map is the record that you decided about each one.

**The rule that overrides everything else here: precis does not review code.**
No verdicts, no findings, no quality opinions, no suggestions, no "this could
be". You are writing the briefing a reviewer reads *before* they form an
opinion, and every sentence that forms one for them takes the review away from
the person whose job it is. `scripts/validate_model.py` scans for the vocabulary
of judgement and exits 1 on a hit. It is a floor, not a ceiling: prose can be
judgemental without using any of those words, and that is on you to notice.

The test for any sentence: **would this still be true and useful if the reviewer
ends up rejecting the change?** "The retry loop now runs before the idempotency
check" survives that. "The retry loop should run after the check" does not.

---

## Order of work

1. Read the whole pre-model. Files, counts, classifications, warnings.
2. Read the core and supporting hunks properly. Not skimmed.
3. Resolve the call graph against the checkout (below). This is the step that
   needs the repository and not just the diff.
4. Inventory the changed contracts and grep for their callers (below). Also a
   checkout step, and the single highest-leverage one.
5. Read the rule documents `find_rules.py` found. `references/rules.md`.
6. Write `story` (with `shape` and `tests`), then `behavior`, then `contracts`,
   then `review_pass`, then `seams`.
7. Fill `change_map.groups` from the classification, adjusting where you
   disagree with the hint, and `stats.signal_ratio` from your final calls.
8. Write `coverage` last, from `budget`, `warnings`, and the documents you read.
9. Validate. Fix. Validate again.

---

## The call graph

`change_map.graph` is the part of the report a diff view structurally cannot
produce, and it is worth the effort it costs. Its job: let a reviewer see which
symbol calls which across files, including the ones that did not change.

**Find the symbols.** From the core hunks, list what was added, removed, or
changed: functions, methods, endpoints, types, tables, config keys. These are
your changed nodes.

**Find the neighbours by grepping the checkout**, not by guessing:

```bash
grep -rn "claim(" --include='*.py' src/ | head -40
grep -rn "from meridian.webhooks.dedupe import" --include='*.py' .
```

A caller that did not change is exactly the context GitHub hides, so it belongs
on the graph, drawn muted. Follow one hop out from each changed symbol - callers
in, callees out. Two hops produces a picture nobody reads.

**Every edge needs evidence.** Each edge carries either `hunk_ids` (the change
itself created or altered this relationship) or `ref` as `path:line` (this call
exists in the checkout, at that line, unchanged). *An edge you cannot point at a
line for is an edge you do not draw.* Not "these probably talk to each other" -
find the line or leave it out.

**Node rules that the validator enforces:**

- A node whose `emphasis` is anything but `unchanged` must carry the `hunk_ids`
  that changed it.
- A node carrying `hunk_ids` must have a `path` that appears in
  `change_map.groups`.
- An unchanged neighbour usually has no `hunk_ids` and often sits outside the
  diff entirely. That is the point of it.
- Between 2 and 12 nodes. Past a dozen it stops being a map and becomes a
  hairball; pick the spine of the change and let the ledger carry the rest.

The renderer derives how many mapped files appear on no path and says so on the
page. There is no field for that number, so it cannot drift.

**It is usually read as text, not as a picture.** A graph that does not branch -
no node with two or more changed callers or callees - renders as an indented
trace, which is more legible than a drawing and pastes into a pull request
comment. Write node labels and edge labels so they read in a line of text: an
edge label is a phrase like `first`, `per service`, or `issubclass`, and a
`note` on a node is the sentence a reader gets instead of a tooltip.

**Draw only what changed.** The graph exists to show a structural delta: a new
component, a new call edge, a moved boundary, plus the one hop of unchanged
neighbours that makes the delta legible. If the change adds, removes, and moves
no relationship - a value change, a docs change, a rename with the same call
shape - `graph: null` is the right answer and the page renders no map at all.
A map of unchanged code is decoration, and the reader pays for decoration in
trust.

---

## `contracts` - what changed shape

For every surface someone outside this diff depends on - an API signature or
response, a schema, a config default, a wire format, a feature flag, a CLI -
write a before/after pair. Transcribe, do not describe: `before` and `after`
are the shape as code says it, and the renderer sets them in a two-row table.
An empty `contracts` array is itself the answer most reviewers came for, so
emptiness has to be earned by having looked.

**Then find the callers.** This is the question a diff view structurally
cannot answer: who else uses this, and did the change reach them?

```bash
grep -rn "calculate_fee(" --include='*.py' src/ | grep -v tests/
grep -rn "fully_refunded" -r src/ docs/
```

Count the call sites outside the changed surface's own file. The ones this diff
also updates go in `callers.updated`; the ones it does not touch go in
`callers.untouched`, each as `path:line`. Write `callers` only for surfaces you
actually searched; an untouched call site the report missed costs more trust
than the whole field earns. If the checkout was not available, omit `callers`
and say so in `coverage.limitations`.

Keep it to surfaces whose contract changed. A touched private helper is not a
contract, and listing it here buries the two entries that matter.

---

## `change_map.groups` - the areas

The groups are the backbone of the rendered report. Each one becomes an area
section that carries its own reading steps, its own checks, its own skip groups,
and its own file list, so a reviewer works one area at a time. A lazy grouping
is a lazy report; this is the section where the segmentation earns its keep.

**Label by purpose, never by directory.** "Digest header construction", not
"src/requests". "API contract", not "handlers". The `role` is metadata the page
never shows; the label is the only thing that says what this part of the change
is *for*, so it has to carry both the layer and the purpose.

**One role, several areas, whenever the change has several concerns.** The
role enumeration is coarse on purpose, and nothing limits a role to one group.
A backend change usually falls into areas like the domain decision, the API
contract it surfaces through, the persistence that backs it, and the tests
that pin it. A frontend-heavy change almost never reads well as one `ui`
group: split it into the areas a frontend reviewer actually thinks in, such as
components, state and data flow, styling, routing, and the API client
boundary, each its own `ui`-role group with its own label.

**Three to seven areas.** One is right for a genuinely single-concern change;
past seven the list of areas becomes its own reading assignment, so merge
related concerns instead. The decomposition is the report's spine and this cap
is what keeps the spine visible.

**Order groups by where the reading starts.** The renderer leads with the area
that holds step 1 and keeps your order for areas with nothing to read, so put
the core-bearing group first and the mechanical tail last. When the order
carries a dependency - this area defines the interface the next one consumes -
say so in `order_note`, one clause.

**Write `summary` for every area a reviewer will spend time in.** One line on
what this part of the change is doing; it renders directly under the area's
title.

---

## `story`

Three or four labelled beats, 2-4 of them, each a label and one or two
sentences. Three archetypes that work:

- **WAS / NOW / WATCH** - a behaviour change. What the system did, what it does
  now, what that touches.
- **BEFORE / IMPACT / NOW** - a bug fix. The broken behaviour, who felt it, the
  new behaviour.
- **NEED / NOW / NEXT** - a feature. What was missing, what exists now, what is
  deliberately left for later.

Beats are not a summary of the diff. A reviewer can already see 43 files
changed; what they cannot see is that 40 of them are one mechanical consequence
of the three that matter.

**`shape` and `tests` both land in the masthead.** `shape` is the first word of
the metadata line and never appears again, so it is one word for what kind of
change this reads as; reach for `mixed` whenever the diff genuinely carries more
than one kind, because `mixed` is a finding, not a failure to decide, and it
usually travels with `seams`. `tests` states whether
tests *in this diff* exercise the changed behaviour: `yes`, `partial` (the
`note` names what is and is not exercised), `none`, or `n/a` when
`behavior.changed` is false. It is a statement of fact about the diff. Whether
the tests are sufficient is the reviewer's call, and wording that implies an
answer fails the verdict scan or deserves to.

`intent_delta` compares the author's stated intent against what the diff does.
It is **evidence, not accusation**: `stated` quotes the author verbatim,
`observed` states what the code does, and the delta is a fact the reviewer may
find entirely reasonable. If there is no description, omit the field. Never
infer intent from the code and then compare the code to it.

---

## `behavior`

The before/after pair. Same shape on both sides so the diff between the two
diagrams is the change. Rules that keep it honest:

- If a path did not exist before, the `before` side says so with a
  `not_done` entry rather than drawing a phantom.
- `changed: false` needs a `note` saying what stayed the same and why that is
  worth stating.
- Node labels stay under 48 characters. A diagram that needs a paragraph is a
  paragraph.

---

## `review_pass`

The checklist a reviewer completes. Two kinds of item, one numbering.

**`steps` - what to read.** Ordered so each one makes sense given the previous
ones: definition before use, migration before the code that depends on it,
interface before implementation. Each step names its hunks, and those hunks must
be present in full - a step pointing at an elided hunk is a step a reviewer
cannot do. Steps render inside the area that owns their file, numbered across
the whole pass, so the order survives the grouping.

**Anchored annotations are the code a reader sees.** A step shows only the
lines its annotations anchor to, with a line of context each side; the full
hunk sits behind a fold. Anchor an annotation to every line a reader has to
see, because a step with no anchored annotation shows no code until the reader
unfolds it. An annotation says what the line does, never what you think of it.

**`checks` - what to decide.** Each carries a `question`, and the question rule
is absolute:

> **A check is a question only the reviewer's context can answer.**

"Is the migration reversible?" is not a check - read the file and say so.
"Is a two-minute row lock on `orders` acceptable during your deploy window?" is
a check: precis cannot know the deploy window. Every question ends in `?` and
the validator enforces it.

Two check kinds quote a document rather than describing a surface:
`documented_rule`, where the change departs from a rule the project has written
down, and `rule_change`, where the change rewrites the rule. Both carry a `rule`
object and both have their own procedure, which is `references/rules.md`. The
short version: rules are read as of head, the quote is verbatim with the line it
is written on, and a departure you cannot point at a changed line for is a
departure you do not report.

**`skippable` - what can be left.** Groups of files with a reason. This is where
the 40-file refactor gets its 32 files back. The reason has to be a fact
("regenerated by `scripts/regen_clients.sh`, no hand edits"), not reassurance
("these are fine"). When the group is the same edit applied many times, set
`sample_hunk_id` to one representative hunk: "the same swap, nineteen times -
one shown" earns the skip better than any sentence, and it costs the reader
four lines to verify.

---

## `seams`

Places where this change meets something outside it: a public API, a queue, a
feature flag, another team's code. `detected: true` needs a `note` naming the
seam. `detected: false` is a real answer and is often the useful one.

---

## Writing rules

Every prose field has a character cap in `validate_model.py` and the caps are
not advisory. They exist because a reviewer in a hurry reads short lines and
skips paragraphs, so a paragraph is a field that will not be read.

- Plain text. A backtick span renders as inline code; nothing else is markup.
- No lists inside a field. A list is two fields or it is one sentence.
- Name things the way the code names them. `claim()`, not "the claiming
  mechanism".
- Quote the author verbatim where you quote them at all. Their words are
  evidence; paraphrase makes them yours.
- Never write a number you did not get from the pre-model.

---

## Finish

```bash
python3 scripts/build_model.py /tmp/precis.analysis.json \
  --pre /tmp/precis.pre.json -o /tmp/precis.model.json
python3 scripts/render_report.py /tmp/precis.model.json -o precis-1184.html \
  --digest precis-1184.md
```

`build_model.py` copies the hunk bodies in, reconciles your counts against the
pre-model, and validates. `render_report.py` validates again before it writes.
Both refuse rather than producing a report that lies, and both name the field
that failed. **Never hand-write HTML, never edit the rendered page, never patch
the template to make a particular report work.** The template renders from the
JSON blob and nothing else; if something cannot be expressed in the model, that
is a schema conversation, not a workaround.
