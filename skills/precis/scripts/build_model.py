#!/usr/bin/env python3
"""Assemble a report model from an analysis file and the pre-model.

The analysis phase writes judgement: the story, the map, the reading order, the
checks. It does not write diff text. Every hunk body in a report is a verbatim
copy of what the parser found, and a verbatim copy is a job for a machine - a
retyped diff line is a report that quotes code the repository does not contain.

So the analysis file is a report model with hollow hunks: each entry carries
only the judgement fields, `change_kind` and `significance`, and optionally
`quote_lines` to quote a long noise hunk in part. This script fills in the rest
from the pre-model, checks the deterministic numbers against it, validates the
result, and refuses to write anything that fails.

    build_model.py analysis.json --pre pre.json -o model.json
    build_model.py analysis.json --pre pre.json -o -

The hollow hunk store is also the checklist: a hunk referenced anywhere in the
analysis but missing from it is an error naming the id, because significance is
a judgement and a script guessing it would be the model rubber-stamping itself.
"""
import argparse
import datetime
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from validate_model import _collect_refs, validate  # noqa: E402

VERSION = "0.1.0"

# Copied straight across. `elided` and `fingerprint` stay behind: the first is
# folded into `truncated`, the second is a parser-internal identity check.
CARRIED = (
    "id", "path", "old_path", "language", "header",
    "old_start", "old_lines", "new_start", "new_lines",
    "section", "lines",
)

# Everything the analysis is allowed to say about a hunk. `quote_lines` is the
# one lever over the copy itself: quote the first N lines of a long noise hunk
# rather than all of it. It shortens, it never edits.
JUDGEMENT = frozenset({"change_kind", "significance", "quote_lines"})


def assemble(analysis, pre, generated_at=None):
    """Return (model, problems). A non-empty problems list means do not write."""
    problems = []
    model = json.loads(json.dumps(analysis))     # never mutate the caller's file
    pre_hunks = pre.get("hunks") or {}

    stubs = model.get("hunks")
    if not isinstance(stubs, dict):
        return model, ["hunks must be an object keyed by hunk id, even when hollow"]

    # Nothing may be referenced that the analysis did not consider.
    referenced = {hid for _, hid in _collect_refs(model)}
    for hid in sorted(referenced - set(stubs)):
        where = ", ".join(sorted({w for w, h in _collect_refs(model) if h == hid}))
        problems.append(
            "%s references hunk %r, which the analysis does not classify; add it "
            "to `hunks` with a change_kind and a significance" % (where, hid))

    built = {}
    for hid, stub in stubs.items():
        if not isinstance(stub, dict):
            problems.append("hunks.%s must be an object carrying change_kind and "
                            "significance" % hid)
            continue
        source = pre_hunks.get(hid)
        if source is None:
            problems.append("hunks.%s is not in the pre-model; the ids come from "
                            "parse_diff.py and are not invented here" % hid)
            continue
        for field in ("change_kind", "significance"):
            if not stub.get(field):
                problems.append("hunks.%s is missing %s, which only the analysis "
                                "can decide" % (hid, field))
        for extra in stub:
            if extra not in JUDGEMENT:
                problems.append("hunks.%s carries %r; the analysis writes %s here, "
                                "and everything else is copied"
                                % (hid, extra, " and ".join(sorted(JUDGEMENT))))

        hunk = {key: source.get(key) for key in CARRIED}
        hunk["id"] = hid
        lines = source.get("lines") or []
        quote = stub.get("quote_lines")
        if quote is not None:
            if not isinstance(quote, int) or isinstance(quote, bool) or quote < 1:
                problems.append("hunks.%s has quote_lines %r; it must be a positive "
                                "count of lines to quote" % (hid, quote))
            else:
                hunk["lines"] = lines[:quote]
        # A hunk the budget dropped is one whose lines are a subset of the real
        # ones - an empty subset. Shortening one here is the same statement, and
        # the report has one word for it.
        hunk["truncated"] = bool(
            source.get("truncated") or source.get("elided")
            or len(hunk["lines"] or []) < len(lines))
        hunk["change_kind"] = stub.get("change_kind")
        hunk["significance"] = stub.get("significance")
        built[hid] = hunk

    model["hunks"] = built
    problems += _reconcile(model, pre)
    _add_compatibility_carrier(model)
    _stamp(model, generated_at)
    return model, problems


def _add_compatibility_carrier(model):
    """Supply the retired 1.x review-pass carrier when new analysis omits it.

    The validator still accepts stored 1.x models during the schema transition,
    but new analysis should not spend tokens inventing review choreography that
    is stripped before rendering. This mechanical carrier satisfies old model
    invariants and is never embedded in the HTML presentation model.
    """
    if "review_pass" in model:
        return

    hunks = model.get("hunks") or {}
    groups = (model.get("change_map") or {}).get("groups") or []
    steps = []
    skipped = []
    n = 1
    for group in groups:
        for entry in group.get("files") or []:
            ids = [hid for hid in entry.get("hunk_ids") or []
                   if hid in hunks and not hunks[hid].get("truncated")]
            if ids:
                steps.append({
                    "n": n,
                    "title": entry["path"][-60:],
                    "path": entry["path"],
                    "why": "Compatibility carrier for the 1.x model validator.",
                    "hunk_ids": ids,
                    "annotations": [],
                })
                n += 1
            else:
                skipped.append({
                    "label": entry["path"][-40:],
                    "reason": "No complete hunk body is available in the analysis budget.",
                    "confidence": "high",
                    "file_count": 1,
                    "additions": entry.get("additions", 0),
                    "deletions": entry.get("deletions", 0),
                    "files": [entry["path"]],
                    "group_ids": [group["id"]],
                })
    model["review_pass"] = {
        "estimated_minutes": 0,
        "steps": steps,
        "checks": [],
        "skippable": skipped,
    }


def _reconcile(model, pre):
    """Deterministic numbers come from the pre-model, or they disagree loudly."""
    problems = []
    pre_stats, budget = pre.get("stats") or {}, pre.get("budget") or {}
    stats = model.setdefault("stats", {})
    for field in ("files_changed", "additions", "deletions", "hunks"):
        counted = pre_stats.get(field)
        if counted is None:
            continue
        if field not in stats:
            stats[field] = counted
        elif stats[field] != counted:
            problems.append(
                "stats.%s says %r; the pre-model counted %r. Every number in a "
                "report comes from the pre-model." % (field, stats[field], counted))
    if "changed_lines_by_role" not in stats and pre_stats.get("changed_lines_by_role"):
        stats["changed_lines_by_role"] = pre_stats["changed_lines_by_role"]

    coverage = model.setdefault("coverage", {})
    coverage.setdefault("tier", budget.get("tier"))
    if budget.get("hunks_total") is not None:
        coverage.setdefault("hunks_total", budget["hunks_total"])
    if pre_stats.get("files_changed") is not None:
        coverage.setdefault("files_total", pre_stats["files_changed"])
    return problems


def _stamp(model, generated_at):
    source = model.setdefault("source", {})
    source.setdefault("generated_by", "precis %s" % VERSION)
    if not source.get("generated_at"):
        stamp = generated_at or datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        source["generated_at"] = stamp


def _read(path):
    text = sys.stdin.read() if path == "-" else pathlib.Path(path).read_text(encoding="utf-8")
    return json.loads(text)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("analysis", help="analysis JSON with hollow hunks, or - for stdin")
    parser.add_argument("--pre", required=True, help="pre-model from classify.py")
    parser.add_argument("-o", "--output", help="output path, or - for stdout")
    parser.add_argument("--generated-at",
                        help="fix source.generated_at instead of using the clock, "
                             "so a rebuilt example does not churn")
    args = parser.parse_args(argv)

    try:
        analysis = _read(args.analysis)
        pre = _read(args.pre)
    except (OSError, json.JSONDecodeError) as exc:
        print("precis: cannot read input: %s" % exc, file=sys.stderr)
        return 2

    model, problems = assemble(analysis, pre, generated_at=args.generated_at)
    problems += validate(model, label=args.output or "model")
    if problems:
        print("precis: %d problem(s); refusing to write a model that lies."
              % len(problems), file=sys.stderr)
        for problem in problems:
            print("  %s" % problem, file=sys.stderr)
        return 1

    payload = json.dumps(model, ensure_ascii=False, indent=2) + "\n"
    if args.output in (None, "-"):
        sys.stdout.write(payload)
        return 0
    out = pathlib.Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(payload, encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
