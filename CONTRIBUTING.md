# Contributing to precis

Thanks for looking. precis is small on purpose, and there is one rule that governs
everything else.

## The one rule

**precis never replaces code review.** It reconstructs intent, maps structure, explains
change composition, and reports only concrete risk boundaries with evidence status. It
does not show code, order a review, track progress, or produce an approval verdict.

If you are adding a feature, ask yourself: does this help a human understand the change,
or does it tell them what to think about it? Only the first kind gets merged.

## Running the tests

precis uses the Python standard library and `pytest` for tests. No runtime dependencies.

```bash
python3 -m pytest tests/ -q
```

## Where things live

```
skills/precis/
├── SKILL.md                  the instructions the model actually reads
├── references/
│   ├── schema.md             the contract: both models, field by field
│   ├── ingestion.md          getting a diff out of GitHub, GitLab, or git
│   └── analysis.md           turning facts into an analysis without reviewing
├── scripts/
│   ├── parse_diff.py         unified diff to facts
│   ├── classify.py           signal, noise, and the content budget
│   ├── build_model.py        analysis plus the parser's hunks to one report model
│   ├── validate_model.py     the contract, executable
│   └── render_report.py      model plus template to one HTML file
└── assets/
    ├── template.html         the only thing that draws
    └── fixtures/             three worked examples: 3, 13, and 40 files
```

The rule that keeps the layers apart: **the analysis explains, and scripts establish
facts.** A diff line is never typed by hand. `build_model.py` reconciles analysis with
parsed facts, while `render_report.py` strips source bodies and retired review-pass data
before embedding the presentation model.

## Rendering a fixture

Every change to `assets/template.html` or `scripts/render_report.py` should be checked
against all three fixtures, at desktop and narrow widths, in light and dark mode.

```bash
python3 skills/precis/scripts/render_report.py \
  skills/precis/assets/fixtures/medium.json -o /tmp/medium.html
open /tmp/medium.html
```

The three shipped examples are real pull requests and exercise shapes the fixtures do
not, so they are worth a look too:

```bash
python3 skills/precis/scripts/render_report.py examples/httpx-3768.json -o /tmp/httpx.html
```

## Adding a fixture

Fixtures live in `skills/precis/assets/fixtures/` as a pair: a source diff
(`<name>.diff`) and the report model it produces (`<name>.json`).

1. Write or capture a real unified diff. Sanitize it completely: invented repo, invented
   package names, no employer, client, or infrastructure detail. The fixture domain is a
   fictional SaaS orders/billing service called Meridian; stay in it if you can.
2. Run the diff through `parse_diff.py` and `classify.py` to get the pre-model.
3. Write the analysis: a report model whose `hunks` entries carry only `change_kind` and
   `significance`. Do not paste diff text into it.
4. `build_model.py analysis.json --pre pre.json -o fixtures/<name>.json`.
5. Validate: `python3 -m pytest tests/test_fixtures.py -q`.

Fixtures are the schema's test suite. If a fixture cannot express something real, that
is a schema gap worth reporting.

## Pull requests

- Conventional commit messages (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).
- Tests pass, fixtures render.
- If you change `references/schema.md`, bump `schema_version` and update all three
  fixtures in the same PR. The schema is the contract between the analysis phase and the
  template; a drifting contract breaks both ends silently.
- No new runtime dependencies without a justification in the README. "Python stdlib only"
  is a feature, not an accident: the skill has to run inside someone else's agent
  sandbox without a package install step.
- Python 3.9 syntax. CI runs the suite on 3.9, 3.12 and 3.13.
- No network calls beyond `gh`, `glab`, and `git`. No telemetry, ever. The rendered page
  makes no requests at all, and a test enforces that.
- Plain hyphens, not em dashes. There is a test for that too.

## Reporting a comprehension failure

The most useful bug report for precis is not a crash. It is: *"I read the report, then I
read the diff, and the report sent me to the wrong place first"* or *"it hid something in
`mechanical` that I needed to read."* Those are the failures that matter. Include the
diff if you can share it.
