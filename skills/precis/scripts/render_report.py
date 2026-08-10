#!/usr/bin/env python3
"""Render a precis report model into one self-contained HTML file.

The template is the only thing that knows what a report looks like. This script
does three jobs and no more: validate the model against the contract, embed it
as a JSON blob, and write the result. It never composes markup, and the analysis
phase never writes markup either.

    render_report.py report.json                 -> report.html, beside the model
    render_report.py report.json -o out.html
    render_report.py - -o -                      < report.json > report.html
    render_report.py report.json --digest out.md          -> report and digest
    render_report.py report.json --digest out.md --no-html -> digest only

The digest is ten-ish lines of markdown built from the same validated model:
intent, shape, the flags, and the areas in reading order. It is the piece that
lives where reviewers already are - a PR comment, a chat message - and points
at the full report. For a trivial change it can be the whole deliverable.
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from validate_model import validate  # noqa: E402

SKILL_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE = SKILL_ROOT / "assets" / "template.html"

MODEL_TOKEN = "__PRECIS_MODEL__"
TITLE_TOKEN = "__PRECIS_TITLE__"


def embed_json(model):
    """Serialise the model so it cannot escape its own <script> element.

    Every `<` in JSON is inside a string literal, so replacing it with the
    `\\u003c` escape keeps the document valid JSON and makes `</script` and
    `<!--` unrepresentable. U+2028 and U+2029 are legal in JSON strings but
    terminate a line in older JavaScript parsers, so they go too.
    """
    payload = json.dumps(model, ensure_ascii=False, separators=(",", ":"))
    return (
        payload.replace("<", "\\u003c")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def escape_html(text):
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def document_title(model):
    source = model.get("source") or {}
    title = source.get("title") or "precis report"
    identifier = source.get("identifier")
    return f"{title} {identifier}" if identifier else title


def render(model, template_text):
    if MODEL_TOKEN not in template_text:
        raise ValueError(f"template has no {MODEL_TOKEN} placeholder")
    html = template_text.replace(TITLE_TOKEN, escape_html(document_title(model)))
    # Model last: the payload may legitimately contain the title token as text.
    return html.replace(MODEL_TOKEN, embed_json(model))


SHAPE_TEXT = {"feature": "feature", "bugfix": "bug fix", "refactor": "refactor",
              "docs": "docs", "chore": "chore", "mixed": "mixed change"}
TESTS_TEXT = {
    "yes": "tests in this diff exercise the changed behaviour.",
    "partial": "tests in this diff exercise part of the changed behaviour.",
    "none": "no test in this diff exercises the changed behaviour.",
    "n/a": "no changed runtime behaviour to exercise.",
}


def ordered_groups(model):
    """Groups in reading order: the one holding step 1 leads, the rest keep the
    model's own order. The same rule the template applies."""
    groups = (model.get("change_map") or {}).get("groups") or []
    hunks = model.get("hunks") or {}
    owner = {}
    for group in groups:
        for entry in group.get("files") or []:
            owner[entry.get("path")] = group.get("id")
    first = {}
    for step in (model.get("review_pass") or {}).get("steps") or []:
        path = step.get("path")
        if not path:
            hid = (step.get("hunk_ids") or [None])[0]
            path = (hunks.get(hid) or {}).get("path")
        gid = owner.get(path)
        if gid is not None and gid not in first:
            first[gid] = step.get("n")
    indexed = list(enumerate(groups))
    indexed.sort(key=lambda pair: (first.get(pair[1].get("id"), float("inf")), pair[0]))
    return [group for _, group in indexed]


def digest(model, report_name=None):
    """A ~10-line markdown digest of the model: the header answers, then the
    areas in reading order. Every sentence is either copied from a validated
    prose field or assembled from counted facts, so it inherits the model's
    guarantees, the verdict scan included."""
    src = model.get("source") or {}
    story = model.get("story") or {}
    stats = model.get("stats") or {}
    behavior = model.get("behavior") or {}
    contracts = model.get("contracts") or []
    seams = model.get("seams") or {}
    tests = story.get("tests") or {}

    who = " ".join(x for x in (src.get("identifier"), src.get("title")) if x)
    shape = SHAPE_TEXT.get(story.get("shape"), story.get("shape") or "change")
    lines = ["**%s** (%s)" % (who or "precis digest", shape)]
    if story.get("headline"):
        lines.append(story["headline"])

    changed = (stats.get("additions") or 0) + (stats.get("deletions") or 0)
    ratio = stats.get("signal_ratio")
    if isinstance(ratio, (int, float)):
        lines.append("%s changed lines in %s files; %d%% of them are the change itself."
                     % (format(changed, ","), stats.get("files_changed", 0),
                        round(ratio * 100)))

    if behavior.get("changed"):
        lines.append("Behaviour: %s" % (behavior.get("summary")
                                        or "runtime behaviour changes."))
    else:
        lines.append("Behaviour: %s" % (behavior.get("note")
                                        or "no runtime behaviour changes."))

    if contracts:
        names = ", ".join("`%s`" % c.get("name") for c in contracts)
        head = ("one surface changes shape" if len(contracts) == 1
                else "%d surfaces change shape" % len(contracts))
        lines.append("Contracts: %s: %s." % (head, names))
    else:
        lines.append("Contracts: nothing someone outside this diff depends on "
                     "changes shape.")

    tests_text = TESTS_TEXT.get(tests.get("state"))
    if tests_text:
        note = tests.get("note")
        lines.append("Tests: %s%s" % (tests_text, " %s" % note if note else ""))

    groups = ordered_groups(model)
    if groups:
        listed = "; ".join("%d) %s" % (i + 1, g.get("label"))
                           for i, g in enumerate(groups))
        lines.append("Read in %d area%s: %s."
                     % (len(groups), "" if len(groups) == 1 else "s", listed))

    if seams.get("detected"):
        lines.append("Reads as %d independent changes."
                     % len(seams.get("clusters") or []))

    if report_name:
        lines.append("Full report: %s" % report_name)
    return "\n".join(lines) + "\n"


def read_model(path):
    text = sys.stdin.read() if path == "-" else pathlib.Path(path).read_text(encoding="utf-8")
    return json.loads(text)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("model", help="report model JSON, or - for stdin")
    parser.add_argument("-o", "--output", help="output path, or - for stdout")
    parser.add_argument(
        "--template", default=str(DEFAULT_TEMPLATE), help="override the HTML template"
    )
    parser.add_argument(
        "--digest",
        help="also write a ~10-line markdown digest here, or - for stdout",
    )
    parser.add_argument(
        "--no-html",
        action="store_true",
        help="write only the digest; for a trivial change the digest is the deliverable",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="render without checking the contract (for template development only)",
    )
    args = parser.parse_args(argv)

    if args.no_html and not args.digest:
        print("precis: --no-html without --digest would write nothing", file=sys.stderr)
        return 2

    try:
        model = read_model(args.model)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"precis: cannot read model: {exc}", file=sys.stderr)
        return 2

    if not args.skip_validation:
        problems = validate(model, label=args.model)
        if problems:
            print(
                f"precis: {len(problems)} contract violation(s); refusing to render.",
                file=sys.stderr,
            )
            for problem in problems:
                print(f"  {problem}", file=sys.stderr)
            return 1

    out = None
    if not args.no_html:
        if args.output == "-":
            out = "-"
        elif args.output:
            out = pathlib.Path(args.output)
        elif args.model == "-":
            print("precis: reading from stdin requires -o", file=sys.stderr)
            return 2
        else:
            out = pathlib.Path(args.model).with_suffix(".html")

    if out is not None:
        try:
            template_text = pathlib.Path(args.template).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"precis: cannot read template: {exc}", file=sys.stderr)
            return 2
        html = render(model, template_text)
        if out == "-":
            sys.stdout.write(html)
        else:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(html, encoding="utf-8")
            print(out)

    if args.digest:
        report_name = out.name if isinstance(out, pathlib.Path) else None
        text = digest(model, report_name=report_name)
        if args.digest == "-":
            sys.stdout.write(text)
        else:
            dest = pathlib.Path(args.digest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text, encoding="utf-8")
            print(dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
