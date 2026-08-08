# Turning facts into a report model

The pre-model says what changed. This phase says what it means, in the shape
`references/schema.md` defines. It is the only phase with judgement in it, and
the only one that can produce something a reviewer would resent.

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
4. Write `story`, then `behavior`, then `review_pass`, then `seams`.
5. Fill `change_map.groups` from the classification, adjusting where you
   disagree with the hint, and `stats.signal_ratio` from your final calls.
6. Write `coverage` last, from `budget` and `warnings`.
7. Validate. Fix. Validate again.

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
cannot do.

**`checks` - what to decide.** Each carries a `question`, and the question rule
is absolute:

> **A check is a question only the reviewer's context can answer.**

"Is the migration reversible?" is not a check - read the file and say so.
"Is a two-minute row lock on `orders` acceptable during your deploy window?" is
a check: precis cannot know the deploy window. Every question ends in `?` and
the validator enforces it.

**`skippable` - what can be left.** Groups of files with a reason. This is where
the 40-file refactor gets its 32 files back. The reason has to be a fact
("regenerated by `scripts/regen_clients.sh`, no hand edits"), not reassurance
("these are fine").

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
python3 scripts/validate_model.py /tmp/precis.model.json
python3 scripts/render_report.py /tmp/precis.model.json -o precis-1184.html
```

`render_report.py` validates again before it writes, and refuses rather than
producing a report that lies. **Never hand-write HTML, never edit the rendered
page, never patch the template to make a particular report work.** The template
renders from the JSON blob and nothing else; if something cannot be expressed in
the model, that is a schema conversation, not a workaround.
