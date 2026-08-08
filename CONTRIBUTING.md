# Contributing to precis

Thanks for looking. precis is small on purpose, and there is one rule that governs
everything else.

## The one rule

**precis never reviews code.** No verdicts, no bug reports, no quality opinions, no
"you should". It reconstructs intent, maps structure, orders reading, and flags what
deserves attention. The moment output says *whether code is good*, it has stopped being
precis.

If you are adding a feature, ask yourself: does this help a human understand the change,
or does it tell them what to think about it? Only the first kind gets merged.

## Running the tests

precis uses the Python standard library and `pytest` for tests. No runtime dependencies.

```bash
python3 -m pytest tests/ -q
```

## Rendering a fixture

Every change to `assets/template.html` or `scripts/render_report.py` should be checked
against all three fixtures, at desktop and narrow widths, in light and dark mode.

```bash
python3 skills/precis/scripts/render_report.py \
  skills/precis/assets/fixtures/medium.json \
  --out /tmp/medium.html
open /tmp/medium.html
```

## Adding a fixture

Fixtures live in `skills/precis/assets/fixtures/` as a pair: a source diff
(`<name>.diff`) and the report model it produces (`<name>.json`).

1. Write or capture a real unified diff. Sanitize it completely: invented repo, invented
   package names, no employer, client, or infrastructure detail. The fixture domain is a
   fictional SaaS orders/billing service called Meridian; stay in it if you can.
2. Run the diff through `parse_diff.py` and `classify.py` to get the pre-model.
3. Write the report model by hand, the way the analysis phase would.
4. Validate it: `python3 -m pytest tests/test_fixtures.py -q`.

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
- No network calls beyond `gh`, `glab`, and `git`. No telemetry, ever.

## Reporting a comprehension failure

The most useful bug report for precis is not a crash. It is: *"I read the report, then I
read the diff, and the report sent me to the wrong place first"* or *"it hid something in
`mechanical` that I needed to read."* Those are the failures that matter. Include the
diff if you can share it.
