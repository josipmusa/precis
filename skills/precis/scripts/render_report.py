#!/usr/bin/env python3
"""Render a precis report model into one self-contained HTML file.

The template is the only thing that knows what a report looks like. This script
does three jobs and no more: validate the model against the contract, embed it
as a JSON blob, and write the result. It never composes markup, and the analysis
phase never writes markup either.

    render_report.py report.json                 -> report.html, beside the model
    render_report.py report.json -o out.html
    render_report.py - -o -                      < report.json > report.html
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
        "--skip-validation",
        action="store_true",
        help="render without checking the contract (for template development only)",
    )
    args = parser.parse_args(argv)

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

    try:
        template_text = pathlib.Path(args.template).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"precis: cannot read template: {exc}", file=sys.stderr)
        return 2

    html = render(model, template_text)

    if args.output == "-":
        sys.stdout.write(html)
        return 0

    if args.output:
        out = pathlib.Path(args.output)
    elif args.model == "-":
        print("precis: reading from stdin requires -o", file=sys.stderr)
        return 2
    else:
        out = pathlib.Path(args.model).with_suffix(".html")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
