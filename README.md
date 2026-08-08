# precis

**precis is not a code review tool. It's a tool that helps humans review code.**

A *précis* is a concise summary of a text's essential points. It also starts with "PR."

precis takes a pull request, merge request, or plain `git diff` range and produces a
**comprehension artifact**: one self-contained HTML report that explains what the change
does, which parts are the actual change, which parts are ripple, and in what order to
read them.

It never tells you whether the code is good. That is your job. precis exists to make
that job take two minutes of orientation instead of twenty.

---

> **Status: under construction.** This README is a stub. It gets written properly in
> Phase 3, with screenshots from `examples/`. See the project brief for the plan.

## Layout

```
precis/
├── .claude-plugin/marketplace.json   # /plugin marketplace add <owner>/precis
├── skills/precis/                    # the skill
│   ├── SKILL.md
│   ├── scripts/                      # deterministic diff parsing + rendering
│   ├── references/                   # ingestion, analysis, schema
│   └── assets/                       # HTML template + fixtures
├── examples/                         # real rendered reports
└── tests/                            # pytest
```

## License

MIT. See [LICENSE](LICENSE).
