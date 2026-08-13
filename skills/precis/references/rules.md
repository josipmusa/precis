# Repository rules

Project instructions are context for explaining a change. They are not a source
of generic findings or a parallel policy checklist.

## Selection

Use `find_rules.py` to identify `AGENTS.md`, `CLAUDE.md`, contribution guides,
ADRs, and other documents governing the changed paths. Read the selected files
and record them in `coverage.rules_read`. If they could not be read, name that
in `coverage.limitations`.

## Use

- Match the repository's terms in the outcome and concern map.
- Use architecture documents to explain why boundaries and dependencies exist.
- Use stated ticket or contribution rules to clarify scope.
- A changed rule may explain why mechanical ripple is large.
- Quote a rule only when exact wording is needed, and anchor it to `path:line`.

Do not turn every applicable rule into a risk flag. A flag still needs a
concrete changed decision, a failure condition, and evidence status. A clean
comparison may produce no flags.

If a change intentionally updates a rule document, treat the new wording as the
head revision's context. Explain the transition when it affects the change's
intent or composition. Do not accuse the code of violating the wording it is
replacing.
