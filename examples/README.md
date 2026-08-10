# Examples

Three reports precis produced from three real, open pull requests. Nothing here
is invented: the diffs came from `gh pr diff`, the call graphs were resolved
against a checkout of each project at the PR head, and every quoted line is a
verbatim copy made by `build_model.py`.

Each example ships as a pair. The `.html` is the artifact a reviewer opens: one
file, no server, no network. The `.json` beside it is the report model it was
rendered from, which is the contract, so you can re-render it, validate it, or
diff it against your own run.

| Example | Pull request | Shape of the change |
|---|---|---|
| `requests-7413` | [psf/requests#7413](https://github.com/psf/requests/pull/7413) | 2 files, +35 −0. A two-line fix and the test that pins it. |
| `alembic-1805` | [sqlalchemy/alembic#1805](https://github.com/sqlalchemy/alembic/pull/1805) | 11 files, +214 −2. A new extension point, with docs, scaffolds and tests. |
| `httpx-3768` | [encode/httpx#3768](https://github.com/encode/httpx/pull/3768) | 17 files, +56 −67. One lint rule, and sixteen files of consequence. |

They were picked to be different from each other rather than to be flattering.
The requests report spends most of its space on two lines. The alembic report
has to order eleven files so the reader meets each one after the thing it
depends on. The httpx report is the case precis exists for: 17 files where one
of them is a decision and the rest are what the decision produced, which is why
it says only 14% of the changed lines are the change itself.

## Opening them

```bash
open examples/httpx-3768.html          # macOS
xdg-open examples/httpx-3768.html      # Linux
```

GitHub will not render a stored HTML file, so clicking the `.html` in the web UI
shows you source. Clone the repository, or download the raw file, and open it
from disk.

## Re-rendering one

The model is the input; the template is the only thing that draws.

```bash
python3 skills/precis/scripts/render_report.py examples/httpx-3768.json -o /tmp/httpx.html
```

To rebuild a model from scratch you need the diff and the pre-model as well;
`skills/precis/SKILL.md` has the four-step pipeline.

## About the quoted code

These reports embed excerpts of each project's source, as any diff view does.
The excerpts remain under their projects' own licences, and none of them is
relicensed by being quoted here:

- **psf/requests** - Apache License 2.0. Copyright Kenneth Reitz and contributors.
- **sqlalchemy/alembic** - MIT License. Copyright Michael Bayer and contributors.
- **encode/httpx** - BSD 3-Clause License. Copyright Encode OSS Ltd.

precis's own MIT licence covers the report format, the template, and the prose
precis wrote. If you are one of these projects' maintainers and would rather not
appear here, open an issue and the example comes out.

## A note on what these are not

None of these reports says whether the pull request is any good. That is not
modesty about the analysis, it is the whole design: a reviewer handed a
conclusion stops reviewing. Each report ends in a checklist of questions the
reviewer's own context is needed to answer, and precis does not know the answers
to any of them.
