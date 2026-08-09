# Checking a change against the project's own rules

Most repositories write their rules down: `CLAUDE.md`, `CONTRIBUTING.md`, a
style guide, an ADR. This phase sets those documents beside the diff and turns
each place the two disagree into a check the reviewer answers.

It is the same move `intent_delta` makes against the PR description, one step
further out. There, precis quotes what the author said and states what the diff
does. Here it quotes what the project said and states what the diff does. In
both, the quote is evidence and the reader decides.

**This is not a linter and it is not a review.** precis does not know whether a
departure matters. A team departs from its own written rules constantly and for
good reasons, and the question at the end of every one of these checks is the
one precis genuinely cannot answer:

> The document says this. The change does that. Is this an agreed exception?

---

## 1. Find the documents

```bash
python3 skills/precis/scripts/find_rules.py /tmp/precis.pre.json --root . -o /tmp/precis.rules.json
```

Deterministic, like `parse_diff.py` and `classify.py`, and for the same reason:
`coverage.rules_read` is a record of what was read, so it has to be the same on
the second run as on the first. Do not go looking by hand instead.

What comes back is a list of documents, nearest-first, each with the reasons it
was picked, whether the diff touches it, and its size. Anything the caps
excluded is in `skipped`, and `skipped` is not optional reading: a document that
was dropped is a document whose rules you have not checked.

Read the documents it names. Read them properly, not by grepping for imperatives.

## 2. Resolve each rule as it stands at head

**A change that rewrites a rule is following the new rule, not departing from
the old one.** This is the failure this phase most needs to avoid: telling an
author their change breaks a rule that the change itself is replacing.

So for any document with `in_diff: true`, the text that governs is the text
after the change:

```bash
git show b81d0f6a2c94e7358d1a6f0b3e9c4275ad8e1602:CONTRIBUTING.md
```

If that fails, which it does for a fork whose objects were never fetched,
reconstruct the rule from the `+` lines of that document's own hunks; you have
them in the pre-model. If neither works, check nothing from that document and
put a line in `coverage.limitations` saying which one and why.

For a document the diff does not touch, the working tree is already head.

## 3. Decide what is a rule you can check

Two tests, and a candidate has to pass both.

**It is stated as a rule.** An instruction, a prohibition, a requirement. "Every
migration is reversible." "Never import from `internal/` outside its package."
Not a description of how something works today, and not an aspiration.

**You can quote it and point at a changed line.** The quote is one sentence,
verbatim, with the file and line it is written on. The departure is a hunk id.

> *A departure you cannot point at a changed line for is a departure you do not
> report.*

That is the graph-edge rule again, and it is what keeps this phase from becoming
a linter with opinions. "Keep functions small" states no line you can point at,
so it produces nothing. `validate_model.py` enforces both halves: the `rule`
object and non-empty `hunk_ids`.

Only the changed lines are in scope. Code this change never touched is not this
change's departure, however far from the rules it sits.

## 4. Write the check

Two kinds:

| Kind | Use it when |
|---|---|
| `documented_rule` | The diff does something a rule in force at head forbids, or omits something it requires. |
| `rule_change` | The diff changes the rule text itself. `was` carries the wording it replaces. |

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

**`quote` is the document's voice.** Verbatim, one operative sentence, and never
your paraphrase of a paragraph. It is exempt from the verdict scan for exactly
that reason: rules say "should" and "problem" and precis quotes them as written.
Never reproduce a document at length; quote the sentence the hunk bears on.

**`why` is your voice** and is scanned like every other field. It states what
the diff does at that line. It does not say the code is at fault. A `why` that
would sting read aloud to the author has become a review.

**`question` is the reviewer's.** "Is this an agreed exception?" and "which
callers still expect the old wording?" are theirs to answer. "Is this rule
right?" is not a question about the change at all.

**A `rule_change` is not a departure.** Nobody did anything wrong by editing a
document. The check exists because a rewritten rule is easy to miss in a large
diff and because the reviewer is the only one who knows what else was written
against the old wording.

## 5. Record what you read

`coverage.rules_read` is the list of documents you actually read, and the three
states are different answers:

| | |
|---|---|
| A list of paths | These documents were read. |
| `[]` | precis looked and this change touches nothing that states rules. |
| absent | precis did not look, and `coverage.limitations` says why. |

Never list a document you did not open, and never leave the field off after a
run that read something. It is the only way a reader can tell a clean report
from a report where this phase never happened.

## Never

- Edit a rules document, or propose an edit to one. precis reads.
- Summarise a document, or reproduce more of one than the sentence in question.
- Raise a departure from a rule this same change rewrites.
- Raise a departure you cannot quote and anchor to a changed line.
