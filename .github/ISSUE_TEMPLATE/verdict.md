---
name: A report expressed an opinion
about: precis said whether the code was good, which it must never do
title: ''
labels: verdict
assignees: ''
---

precis has one rule: it never says whether a change is good. Every model running the skill
drifts toward reviewing, so when one gets through, the guard that should have caught it
needs fixing rather than the sentence.

**The sentence**
Quote it exactly, and say which field it came from if you know (`story.headline`,
`review_pass.checks[2].why`, and so on).

**Why it reads as a verdict**
Sometimes it is a banned word the scan missed. More often the prose is judgemental without
using one, which is the harder case and the more useful report.

**The report**
Attach the model or the HTML if you can share it.
