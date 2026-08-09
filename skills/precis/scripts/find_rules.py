#!/usr/bin/env python3
"""Find the documents in this repository that state rules, scoped to the diff.

A project's rules live in its own files: CLAUDE.md, CONTRIBUTING.md, an ADR, a
style guide. This script says which of those documents govern the code a change
touches. It does not read them for meaning and it never decides whether the
change departs from anything - that is the analysis phase's job, and it needs a
human-auditable list of what it was given.

Discovery is a script rather than a grep composed on the spot because
`coverage.rules_read` is a record of what was read, and a record has to be the
same on the second run as on the first.

Scoping to the diff is the whole idea: it walks up from each directory the
change touches to the repository root, so a monorepo package that this change
never touches contributes none of its rules. Documents come back nearest-first,
because the rules closest to the code are the ones a reader needs first, and the
root document still governs so it is still listed.

Usage:
    python3 find_rules.py pre_model.json [--root .] [-o rules.json]
    python3 classify.py - | python3 find_rules.py - --root .

Exits 0 when the checkout was searched, 1 when the input is not a pre-model.
"""
from __future__ import annotations

import argparse
import json
import posixpath
import sys
from pathlib import Path

# Both caps exist to stop a pathological repository handing the analysis phase
# more prose than the diff. Whatever they exclude is named in `skipped`: a
# silent cap reads like "there was nothing else", which is the one thing this
# script must never imply.
MAX_DOCS = 12
MAX_BYTES = 120_000

# Looked for in every directory between a changed file and the repository root.
CONVENTIONAL = (
    "CLAUDE.md",
    "AGENTS.md",
    ".cursorrules",
    ".github/copilot-instructions.md",
    "CONTRIBUTING.md",
    "STYLE.md",
    "CONVENTIONS.md",
)

# Document extensions. A file the change edits that carries one of these is
# relevant to the change by construction, whatever it is called.
DOC_SUFFIXES = (".md", ".mdx", ".rst", ".adoc")

# Under `docs/`, the two shapes that hold rules rather than prose.
DECISION_DIR = "docs/adr"
RULE_WORDS = ("convention", "style")

CONVENTIONAL_REASON = "matches a conventional rules filename"
DECISION_REASON = "an architecture decision record under docs/"
GUIDE_REASON = "a conventions or style document under docs/"
CHANGED_REASON = "changed by this diff"


def _safe(path: str):
    """A repository-relative path, or None for one that leaves the checkout."""
    clean = posixpath.normpath((path or "").strip().replace("\\", "/"))
    if not clean or clean == "." or clean.startswith("/") or clean.startswith(".."):
        return None
    return clean


def _ancestors(directory: str):
    """The directory and every directory above it, nearest first."""
    current = directory
    while True:
        yield current
        if not current:
            return
        current = posixpath.dirname(current)


def _child(directory: Path, name: str):
    """One path segment, matched without regard to case.

    Case-insensitive because `claude.md` and `CLAUDE.md` are the same house
    rules, and a report that missed one over a capital letter would be lying by
    omission. Ties resolve by name so the answer stays deterministic.
    """
    exact = directory / name
    if exact.exists():
        return exact
    if not directory.is_dir():
        return None
    lowered = name.lower()
    matches = sorted((p for p in directory.iterdir() if p.name.lower() == lowered),
                     key=lambda p: p.name)
    return matches[0] if matches else None


def _resolve(root: Path, directory: str, relative: str):
    """`directory/relative` under `root`, as a repository-relative path."""
    current = root / directory if directory else root
    for part in relative.split("/"):
        found = _child(current, part)
        if found is None:
            return None
        current = found
    if not current.is_file():
        return None
    try:
        return current.relative_to(root).as_posix()
    except ValueError:  # pragma: no cover - _child never climbs out of root
        return None


def _is_document(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return (path.lower().endswith(DOC_SUFFIXES)
            or any(name.lower() == c.rsplit("/", 1)[-1].lower() for c in CONVENTIONAL))


def _guides(root: Path, directory: str):
    """The rule-shaped documents under one directory's `docs/`."""
    found = []
    decisions = (root / directory / DECISION_DIR) if directory else (root / DECISION_DIR)
    if decisions.is_dir():
        for entry in sorted(decisions.iterdir(), key=lambda p: p.name):
            if entry.is_file() and entry.suffix.lower() == ".md":
                found.append((entry.relative_to(root).as_posix(), DECISION_REASON))
    docs = (root / directory / "docs") if directory else (root / "docs")
    if docs.is_dir():
        for entry in sorted(docs.iterdir(), key=lambda p: p.name):
            if not entry.is_file() or entry.suffix.lower() != ".md":
                continue
            if any(word in entry.name.lower() for word in RULE_WORDS):
                found.append((entry.relative_to(root).as_posix(), GUIDE_REASON))
    return found


def find(pre_model: dict, root) -> dict:
    """Every rule document governing the code this change touches."""
    root = Path(root)
    files = pre_model.get("files") or []

    in_diff, deleted = {}, set()
    for entry in files:
        path = _safe(entry.get("path") or entry.get("old_path") or "")
        if path is None:
            continue
        if entry.get("status") == "deleted":
            deleted.add(path)
        in_diff[path] = list(entry.get("hunk_ids") or [])

    touched = sorted({posixpath.dirname(p) for p in in_diff})

    # path -> {"reasons": [...], "distance": int}. Distance is how far the
    # document sits above the nearest code the change touches.
    found: dict = {}

    def record(path: str, reason: str, distance: int) -> None:
        seen = found.setdefault(path, {"reasons": [], "distance": distance})
        if reason not in seen["reasons"]:
            seen["reasons"].append(reason)
        seen["distance"] = min(seen["distance"], distance)

    for directory in touched:
        for distance, ancestor in enumerate(_ancestors(directory)):
            for relative in CONVENTIONAL:
                resolved = _resolve(root, ancestor, relative)
                if resolved is not None:
                    record(resolved, CONVENTIONAL_REASON, distance)
            for path, reason in _guides(root, ancestor):
                record(path, reason, distance)

    # A document the change edits is relevant to the change by construction, and
    # it may not exist on disk at all when the checkout sits on the base.
    for path in sorted(in_diff):
        if path not in deleted and _is_document(path):
            record(path, CHANGED_REASON, 0)

    skipped = []
    for path in sorted(p for p in found if p in deleted):
        found.pop(path)
        skipped.append("%s: deleted by this change, so it states no rule at head" % path)

    order = sorted(found, key=lambda p: (found[p]["distance"], p))

    docs, spent = [], 0
    for path in order:
        size = None
        target = root / path
        if target.is_file():
            size = target.stat().st_size
        if len(docs) >= MAX_DOCS:
            skipped.append("%s: past the %d document cap" % (path, MAX_DOCS))
            continue
        if spent >= MAX_BYTES:
            skipped.append("%s: past the %d byte cap" % (path, MAX_BYTES))
            continue
        spent += size or 0
        docs.append({
            "path": path,
            "reasons": found[path]["reasons"],
            "in_diff": path in in_diff,
            "hunk_ids": in_diff.get(path, []),
            "bytes": size,
        })

    return {"schema_version": "1.0", "docs": docs, "skipped": skipped}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pre_model", help="classify.py output, or - for stdin")
    ap.add_argument("--root", default=".", help="the checkout to search (default .)")
    ap.add_argument("-o", "--out", help="write here instead of stdout")
    ap.add_argument("--compact", action="store_true")
    args = ap.parse_args(argv)

    raw = sys.stdin.read() if args.pre_model == "-" else \
        open(args.pre_model, encoding="utf-8").read()
    try:
        model = json.loads(raw)
    except json.JSONDecodeError as exc:
        sys.stderr.write("find_rules: not JSON: %s\n" % exc)
        return 1
    if not isinstance(model, dict) or "files" not in model:
        sys.stderr.write("find_rules: this is not a pre-model; run parse_diff.py first\n")
        return 1

    result = find(model, args.root)
    text = json.dumps(result, indent=None if args.compact else 2,
                      ensure_ascii=False, sort_keys=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(args.out)
    else:
        sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
