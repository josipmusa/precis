#!/usr/bin/env python3
"""Validate a precis report model against the contract in references/schema.md.

The schema is the contract between the analysis phase and the template. This is
that contract in executable form: `render_report.py` runs it before writing HTML,
and the test suite runs it against every fixture.

A failure here is a bug in whatever produced the model, not something to render
around. The renderer refuses rather than emitting a report that lies.

Usage:
    python3 validate_model.py report.json [report.json ...]

Exits 0 when every document is valid, 1 otherwise.
"""
from __future__ import annotations

import json
import sys

SUPPORTED_MAJOR = 1

ROLES = {"api", "domain", "persistence", "tests", "config", "generated",
         "docs", "build", "infra", "ui", "other"}
CHANGE_KINDS = {"new_logic", "modified_logic", "moved", "rename", "formatting",
                "generated", "content", "deleted"}
SIGNIFICANCE = {"core", "supporting", "mechanical"}
CONFIDENCE = {"high", "medium", "low"}
FILE_STATUS = {"added", "modified", "deleted", "renamed", "copied",
               "mode_changed", "binary"}
SOURCE_KINDS = {"github_pr", "gitlab_mr", "git_range", "patch_file"}
COVERAGE_TIERS = {"full", "core", "summary"}
EVIDENCE = {"pr_description", "linked_issue", "commit_messages", "branch_name", "code"}
DELTA_KINDS = {"scope_creep", "drive_by", "incidental"}
ATTENTION_KINDS = {"behavioral", "security_surface", "irreversible_migration",
                   "public_api", "concurrency", "data_loss", "external_contract",
                   "dependency_surface", "config_surface", "feature_flag"}
DIAGRAM_KINDS = {"sequence", "flow"}
NODE_KINDS = {"actor", "service", "process", "decision", "store", "external",
              "queue", "note", "start", "end"}
EDGE_KINDS = {"call", "return", "async", "error", "data"}
EMPHASIS = {"unchanged", "added", "removed", "changed"}
LINE_TYPES = {" ", "+", "-"}


class Report:
    """Accumulates problems so one run reports every failure, not just the first."""

    def __init__(self, label: str) -> None:
        self.label = label
        self.problems: list[str] = []

    def fail(self, where: str, message: str) -> None:
        self.problems.append("%s: %s" % (where, message))

    def require(self, cond: bool, where: str, message: str) -> bool:
        if not cond:
            self.fail(where, message)
        return cond

    def enum(self, value, allowed: set, where: str, field: str) -> None:
        if value not in allowed:
            self.fail(where, "%s is %r, expected one of %s"
                      % (field, value, sorted(allowed)))


def _int(rep, obj, key, where):
    value = obj.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        rep.fail(where, "%s must be an integer, got %r" % (key, value))


def _validate_diagram(rep, diagram, where):
    if not isinstance(diagram, dict):
        rep.fail(where, "diagram must be an object")
        return
    rep.enum(diagram.get("kind"), DIAGRAM_KINDS, where, "kind")
    kind = diagram.get("kind")
    lanes = diagram.get("lanes") or []
    nodes = diagram.get("nodes") or []
    edges = diagram.get("edges")

    lane_ids = set()
    for i, lane in enumerate(lanes):
        if "id" not in lane or "label" not in lane:
            rep.fail("%s.lanes[%d]" % (where, i), "needs id and label")
            continue
        if lane["id"] in lane_ids:
            rep.fail("%s.lanes[%d]" % (where, i), "duplicate lane id %r" % lane["id"])
        lane_ids.add(lane["id"])

    node_ids = set()
    for i, node in enumerate(nodes):
        nwhere = "%s.nodes[%d]" % (where, i)
        if "id" not in node or "label" not in node:
            rep.fail(nwhere, "needs id and label")
            continue
        if node["id"] in node_ids:
            rep.fail(nwhere, "duplicate node id %r" % node["id"])
        node_ids.add(node["id"])
        rep.enum(node.get("kind"), NODE_KINDS, nwhere, "kind")
        rep.enum(node.get("emphasis"), EMPHASIS, nwhere, "emphasis")
        if node.get("lane") is not None and node["lane"] not in lane_ids:
            rep.fail(nwhere, "lane %r is not declared" % node["lane"])

    if kind == "sequence":
        rep.require(bool(lanes), where, "a sequence diagram needs lanes")
        endpoints, what = lane_ids, "lane"
    else:
        rep.require(bool(nodes), where, "a flow diagram needs nodes")
        endpoints, what = node_ids, "node"

    if not isinstance(edges, list) or not edges:
        rep.fail(where, "edges must be a non-empty array")
        return
    for i, edge in enumerate(edges):
        ewhere = "%s.edges[%d]" % (where, i)
        rep.enum(edge.get("kind"), EDGE_KINDS, ewhere, "kind")
        rep.enum(edge.get("emphasis"), EMPHASIS, ewhere, "emphasis")
        for end in ("from", "to"):
            if edge.get(end) not in endpoints:
                rep.fail(ewhere, "%s %r is not a declared %s id"
                         % (end, edge.get(end), what))


def _validate_hunks(rep, model):
    hunks = model.get("hunks")
    if not isinstance(hunks, dict):
        rep.fail("hunks", "must be an object keyed by hunk id")
        return {}
    for hid, hunk in hunks.items():
        where = "hunks[%s]" % hid
        if hunk.get("id") != hid:
            rep.fail(where, "id field %r does not match its key" % hunk.get("id"))
        if not hunk.get("path"):
            rep.fail(where, "path is required")
        for key in ("old_start", "old_lines", "new_start", "new_lines"):
            _int(rep, hunk, key, where)
        if not isinstance(hunk.get("truncated"), bool):
            rep.fail(where, "truncated must be a boolean")
        rep.enum(hunk.get("change_kind"), CHANGE_KINDS, where, "change_kind")
        rep.enum(hunk.get("significance"), SIGNIFICANCE, where, "significance")

        lines = hunk.get("lines")
        if not isinstance(lines, list):
            rep.fail(where, "lines must be an array")
            continue
        old_count = new_count = 0
        for i, row in enumerate(lines):
            lwhere = "%s.lines[%d]" % (where, i)
            if row.get("t") not in LINE_TYPES:
                rep.fail(lwhere, "t is %r, expected ' ', '+' or '-'" % row.get("t"))
                continue
            if not isinstance(row.get("c"), str):
                rep.fail(lwhere, "c must be a string")
            if row["t"] in " -":
                old_count += 1
            if row["t"] in " +":
                new_count += 1
        if not hunk.get("truncated"):
            if old_count != hunk.get("old_lines") or new_count != hunk.get("new_lines"):
                rep.fail(where,
                         "line counts disagree with the header: counted -%d/+%d, "
                         "header says -%s/+%s"
                         % (old_count, new_count, hunk.get("old_lines"), hunk.get("new_lines")))
    return hunks


def _collect_refs(model):
    """Every (location, hunk_id) pair in the document, so bad references name themselves."""
    refs = []

    def walk(node, path):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "hunk_ids" and isinstance(value, list):
                    for hid in value:
                        refs.append(("%s.hunk_ids" % path, hid))
                elif key == "hunk_id" and isinstance(value, str):
                    refs.append(("%s.hunk_id" % path, value))
                else:
                    walk(value, "%s.%s" % (path, key))
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, "%s[%d]" % (path, i))

    for section in ("story", "change_map", "behavior", "reading_order",
                    "attention", "seams"):
        walk(model.get(section), section)
    return refs


def validate(model, label="report") -> list[str]:
    """Return a list of human-readable problems. Empty means valid."""
    rep = Report(label)

    if not isinstance(model, dict):
        return ["root: report model must be a JSON object"]

    version = model.get("schema_version")
    if not isinstance(version, str) or not version.split(".")[0].isdigit():
        rep.fail("schema_version", "missing or malformed: %r" % version)
    elif int(version.split(".")[0]) != SUPPORTED_MAJOR:
        rep.fail("schema_version",
                 "major version %s is not supported (this build understands %d.x)"
                 % (version, SUPPORTED_MAJOR))

    for key in ("source", "coverage", "stats", "story", "change_map",
                "behavior", "reading_order", "attention", "seams", "hunks"):
        if key not in model:
            rep.fail("root", "missing required section %r" % key)
    if rep.problems and "hunks" not in model:
        return rep.problems

    # ---- source
    source = model.get("source") or {}
    rep.enum(source.get("kind"), SOURCE_KINDS, "source", "kind")
    if not source.get("title"):
        rep.fail("source", "title is required")
    if not source.get("generated_by"):
        rep.fail("source", "generated_by is required")
    for end in ("base", "head"):
        ref = source.get(end)
        if not isinstance(ref, dict) or "sha" not in ref:
            rep.fail("source.%s" % end, "must be an object with a sha key (null is allowed)")

    # ---- coverage
    coverage = model.get("coverage") or {}
    rep.enum(coverage.get("tier"), COVERAGE_TIERS, "coverage", "tier")
    for key in ("hunks_total", "hunks_read", "files_total", "files_read"):
        _int(rep, coverage, key, "coverage")
    if not isinstance(coverage.get("limitations"), list):
        rep.fail("coverage", "limitations must be an array, even when empty")

    # ---- stats
    stats = model.get("stats") or {}
    for key in ("files_changed", "additions", "deletions", "hunks"):
        _int(rep, stats, key, "stats")
    ratio = stats.get("signal_ratio")
    if not isinstance(ratio, (int, float)) or not 0.0 <= ratio <= 1.0:
        rep.fail("stats", "signal_ratio must be a number in [0, 1], got %r" % ratio)

    # ---- story
    story = model.get("story") or {}
    if not story.get("headline"):
        rep.fail("story", "headline is required")
    if not story.get("paragraph"):
        rep.fail("story", "paragraph is required")
    rep.enum(story.get("confidence"), CONFIDENCE, "story", "confidence")
    evidence = story.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        rep.fail("story", "evidence must be a non-empty array")
    else:
        for item in evidence:
            rep.enum(item, EVIDENCE, "story.evidence", "entry")
    if story.get("confidence") in ("medium", "low") and not story.get("caveat"):
        rep.fail("story", "caveat is required when confidence is not 'high'")
    delta = story.get("intent_delta")
    if not isinstance(delta, dict):
        rep.fail("story", "intent_delta is required (arrays may be empty)")
    else:
        for key in ("also_does", "not_done"):
            if not isinstance(delta.get(key), list):
                rep.fail("story.intent_delta", "%s must be an array" % key)
        for i, item in enumerate(delta.get("also_does") or []):
            where = "story.intent_delta.also_does[%d]" % i
            if not item.get("summary"):
                rep.fail(where, "summary is required")
            rep.enum(item.get("kind"), DELTA_KINDS, where, "kind")

    # ---- hunks
    hunks = _validate_hunks(rep, model)

    # ---- change_map
    change_map = model.get("change_map") or {}
    groups = change_map.get("groups")
    mapped_files = {}
    if not isinstance(groups, list) or not groups:
        rep.fail("change_map", "groups must be a non-empty array")
        groups = []
    group_ids = set()
    for gi, group in enumerate(groups):
        where = "change_map.groups[%d]" % gi
        gid = group.get("id")
        if not gid:
            rep.fail(where, "id is required")
        elif gid in group_ids:
            rep.fail(where, "duplicate group id %r" % gid)
        group_ids.add(gid)
        rep.enum(group.get("role"), ROLES, where, "role")
        if not group.get("label"):
            rep.fail(where, "label is required")
        files = group.get("files")
        if not isinstance(files, list) or not files:
            rep.fail(where, "files must be a non-empty array")
            continue
        for fi, entry in enumerate(files):
            fwhere = "%s.files[%d]" % (where, fi)
            path = entry.get("path")
            if not path:
                rep.fail(fwhere, "path is required")
                continue
            if path in mapped_files:
                rep.fail(fwhere, "%r also appears in group %r" % (path, mapped_files[path]))
            mapped_files[path] = gid
            rep.enum(entry.get("status"), FILE_STATUS, fwhere, "status")
            rep.enum(entry.get("change_kind"), CHANGE_KINDS, fwhere, "change_kind")
            rep.enum(entry.get("significance"), SIGNIFICANCE, fwhere, "significance")
            _int(rep, entry, "additions", fwhere)
            _int(rep, entry, "deletions", fwhere)
            if not isinstance(entry.get("hunk_ids"), list):
                rep.fail(fwhere, "hunk_ids must be an array (empty is allowed)")
            if entry.get("status") in ("renamed", "copied") and not entry.get("moved_from"):
                rep.fail(fwhere, "moved_from is required when status is %r" % entry["status"])

    # ---- behavior
    behavior = model.get("behavior") or {}
    changed = behavior.get("changed")
    if not isinstance(changed, bool):
        rep.fail("behavior", "changed must be a boolean")
    elif changed:
        if not behavior.get("summary"):
            rep.fail("behavior", "summary is required when changed is true")
        for side in ("before", "after"):
            if behavior.get(side) is None:
                rep.fail("behavior", "%s is required when changed is true" % side)
            else:
                _validate_diagram(rep, behavior[side], "behavior.%s" % side)
    else:
        if not behavior.get("note"):
            rep.fail("behavior", "note is required when changed is false")

    # ---- reading_order
    reading = model.get("reading_order") or {}
    steps = reading.get("steps")
    skippable = reading.get("skippable")
    step_paths, step_hunks = set(), set()
    if not isinstance(steps, list) or not steps:
        rep.fail("reading_order", "steps must be a non-empty array")
        steps = []
    for i, step in enumerate(steps):
        where = "reading_order.steps[%d]" % i
        if step.get("n") != i + 1:
            rep.fail(where, "n is %r, expected %d" % (step.get("n"), i + 1))
        for key in ("title", "why"):
            if not step.get(key):
                rep.fail(where, "%s is required" % key)
        hids = step.get("hunk_ids")
        if not isinstance(hids, list) or not hids:
            rep.fail(where, "hunk_ids must be a non-empty array")
            hids = []
        for hid in hids:
            step_hunks.add(hid)
            hunk = hunks.get(hid)
            if hunk is not None and hunk.get("truncated"):
                rep.fail(where, "step references truncated hunk %r; a guided step "
                                "must show complete code" % hid)
        if step.get("path"):
            step_paths.add(step["path"])
        for ai, note in enumerate(step.get("annotations") or []):
            awhere = "%s.annotations[%d]" % (where, ai)
            if not note.get("text"):
                rep.fail(awhere, "text is required")
            if not note.get("hunk_id"):
                rep.fail(awhere, "hunk_id is required")
                continue
            hunk = hunks.get(note["hunk_id"])
            if hunk is None:
                continue
            for side, field in (("new", "new_line"), ("old", "old_line")):
                if note.get(field) is None:
                    continue
                if not any(row.get(side) == note[field] for row in hunk.get("lines", [])):
                    rep.fail(awhere, "%s %r is not a line in hunk %s"
                             % (field, note[field], note["hunk_id"]))

    if not isinstance(skippable, list):
        rep.fail("reading_order", "skippable must be an array, even when empty")
        skippable = []
    skipped_files = {}
    for i, group in enumerate(skippable):
        where = "reading_order.skippable[%d]" % i
        for key in ("label", "reason"):
            if not group.get(key):
                rep.fail(where, "%s is required" % key)
        if group.get("confidence") not in ("high", "medium"):
            rep.fail(where, "confidence must be 'high' or 'medium'; anything less "
                            "confident belongs in steps")
        for key in ("file_count", "additions", "deletions"):
            _int(rep, group, key, where)
        files = group.get("files")
        if not isinstance(files, list):
            rep.fail(where, "files must be an array")
            continue
        if group.get("file_count") != len(files):
            rep.fail(where, "file_count is %r but files lists %d entries"
                     % (group.get("file_count"), len(files)))
        for path in files:
            if path in skipped_files:
                rep.fail(where, "%r is also in skippable group %r"
                         % (path, skipped_files[path]))
            skipped_files[path] = group.get("label")
        for gid in group.get("group_ids") or []:
            if gid not in group_ids:
                rep.fail(where, "group_ids references unknown change_map group %r" % gid)

    # Nothing may be silently dropped: every mapped file is read or explicitly skipped.
    for path, gid in sorted(mapped_files.items()):
        in_steps = path in step_paths
        if not in_steps:
            for group in groups:
                for entry in group.get("files") or []:
                    if entry.get("path") == path:
                        in_steps = any(h in step_hunks for h in entry.get("hunk_ids") or [])
        in_skip = path in skipped_files
        if in_steps and in_skip:
            rep.fail("reading_order", "%r is both in the reading order and in the "
                                      "skippable group %r" % (path, skipped_files[path]))
        elif not in_steps and not in_skip:
            rep.fail("reading_order", "%r (change_map group %r) is neither in the "
                                      "reading order nor in any skippable group" % (path, gid))

    # ---- attention
    attention = model.get("attention")
    if not isinstance(attention, list):
        rep.fail("attention", "must be an array, even when empty")
    else:
        for i, item in enumerate(attention):
            where = "attention[%d]" % i
            rep.enum(item.get("kind"), ATTENTION_KINDS, where, "kind")
            for key in ("title", "why"):
                if not item.get(key):
                    rep.fail(where, "%s is required" % key)
            if "severity" in item:
                rep.fail(where, "severity is not part of the contract; precis does "
                                "not score findings")

    # ---- seams
    seams = model.get("seams") or {}
    detected = seams.get("detected")
    if not isinstance(detected, bool):
        rep.fail("seams", "detected must be a boolean")
    elif detected:
        if not seams.get("note"):
            rep.fail("seams", "note is required when detected is true")
        clusters = seams.get("clusters")
        if not isinstance(clusters, list) or len(clusters) < 2:
            rep.fail("seams", "detected means two or more clusters")
            clusters = []
        cluster_ids = {c.get("id") for c in clusters}
        for i, cluster in enumerate(clusters):
            where = "seams.clusters[%d]" % i
            for key in ("id", "label", "summary"):
                if not cluster.get(key):
                    rep.fail(where, "%s is required" % key)
            files = cluster.get("files")
            if not isinstance(files, list) or not files:
                rep.fail(where, "files must be a non-empty array")
                continue
            if cluster.get("file_count") != len(files):
                rep.fail(where, "file_count is %r but files lists %d entries"
                         % (cluster.get("file_count"), len(files)))
            for other in cluster.get("independent_of") or []:
                if other not in cluster_ids:
                    rep.fail(where, "independent_of references unknown cluster %r" % other)

    # ---- dangling hunk references, reported with their location
    for where, hid in _collect_refs(model):
        if hid not in hunks:
            rep.fail(where, "references unknown hunk %r" % hid)

    # ---- the hunk store may not contain code from a file the map does not show
    for hid, hunk in sorted(hunks.items()):
        path = hunk.get("path")
        if path and path not in mapped_files:
            rep.fail("hunks[%s]" % hid,
                     "path %r does not appear in change_map; the report would show "
                     "code from a file it never lists" % path)

    return rep.problems


def main(argv):
    if len(argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    failed = False
    for path in argv[1:]:
        try:
            with open(path, encoding="utf-8") as fh:
                model = json.load(fh)
        except (OSError, ValueError) as exc:
            print("%s: could not be read as JSON: %s" % (path, exc))
            failed = True
            continue
        problems = validate(model, path)
        if problems:
            failed = True
            print("%s: %d problem(s)" % (path, len(problems)))
            for problem in problems:
                print("  - %s" % problem)
        else:
            print("%s: valid" % path)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
