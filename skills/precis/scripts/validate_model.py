#!/usr/bin/env python3
"""Validate a precis report model against the contract in references/schema.md.

The schema is the contract between the analysis phase and the template. This is
that contract in executable form: `render_report.py` runs it before writing HTML,
and the test suite runs it against every fixture.

Two of the checks here are the product rather than hygiene. Character caps keep
the report readable by a human in a hurry; the verdict scan keeps precis out of
the business of judging code. Both fail the run. Guidance drifts, and the model
running this skill drifts toward reviewing every single time; a validator that
exits 1 is the only thing that has reliably stopped it.

A failure here is a bug in whatever produced the model, not something to render
around. The renderer refuses rather than emitting a report that lies.

Usage:
    python3 validate_model.py report.json [report.json ...]

Exits 0 when every document is valid, 1 otherwise.
"""
from __future__ import annotations

import json
import re
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
SHAPES = {"feature", "bugfix", "refactor", "docs", "chore", "mixed"}
TEST_STATES = {"yes", "partial", "none", "n/a"}
CONTRACT_KINDS = {"api", "schema", "config", "wire", "flag", "cli"}
EVIDENCE = {"pr_description", "linked_issue", "commit_messages", "branch_name", "code"}
DELTA_KINDS = {"scope_creep", "drive_by", "incidental"}
ATTENTION_KINDS = {"behavioral", "security_surface", "irreversible_migration",
                   "public_api", "concurrency", "data_loss", "external_contract",
                   "dependency_surface", "config_surface", "feature_flag",
                   "documented_rule", "rule_change"}
# The two kinds that set a document beside the diff. Both carry a `rule`, and
# nothing else may: precis quotes a rule or it does not mention one.
RULE_KINDS = {"documented_rule", "rule_change"}
DIAGRAM_KINDS = {"sequence", "flow"}
NODE_KINDS = {"actor", "service", "process", "decision", "store", "external",
              "queue", "note", "start", "end"}
EDGE_KINDS = {"call", "return", "async", "error", "data"}
GRAPH_NODE_KINDS = {"entrypoint", "function", "type", "store", "config",
                    "external", "error"}
REL_KINDS = {"calls", "returns", "reads", "writes", "raises", "imports", "renders"}
EMPHASIS = {"unchanged", "added", "removed", "changed"}
LINE_TYPES = {" ", "+", "-"}

MAX_GRAPH_NODES = 12
MIN_GRAPH_NODES = 2

# A reviewer who wanted paragraphs would have read the diff.
VERDICT_WORDS = ("should", "bug", "issue", "incorrect", "consider", "problem",
                 "wrong", "better", "worse", "suboptimal", "unnecessary",
                 "redundant", "misleading")
VERDICT_RE = re.compile(r"\b(%s)\b" % "|".join(VERDICT_WORDS), re.I)

# Keys whose string values are prose precis wrote itself. Bare string arrays are
# paths and enum values almost everywhere, so they are named rather than assumed.
PROSE_KEYS = {"headline", "text", "why", "summary", "note", "reason", "label",
              "question", "caveat", "title"}
PROSE_ARRAYS = {"coverage.limitations"}

# Prose precis is quoting rather than writing. A PR titled "Fix double refund
# bug" keeps its title; the author's words are evidence, not precis's voice, and
# a house rule that says "never ship a change that should have a test" is the
# document's voice. Matched against a path with its array indices removed, so
# one entry covers every element of a list.
QUOTED = ("source.title", "source.description", "source.linked_issues",
          "source.commits", "story.intent_delta.stated",
          "review_pass.checks[].rule")

INDEX_RE = re.compile(r"\[\d+\]")

REF_RE = re.compile(r"^[^\s:]+:\d+$")


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


def _text(rep, obj, key, where, limit, required=True):
    """Required-ness and the character cap in one place, since they always pair."""
    value = obj.get(key)
    if value is None or value == "":
        if required:
            rep.fail(where, "%s is required" % key)
        return
    if not isinstance(value, str):
        rep.fail(where, "%s must be a string, got %r" % (key, value))
        return
    if len(value) > limit:
        rep.fail(where, "%s is %d characters, the cap is %d: %r"
                 % (key, len(value), limit, value[:56] + "..."))


def _validate_diagram(rep, diagram, where):
    if not isinstance(diagram, dict):
        rep.fail(where, "diagram must be an object")
        return
    rep.enum(diagram.get("kind"), DIAGRAM_KINDS, where, "kind")
    kind = diagram.get("kind")
    lanes = diagram.get("lanes") or []
    nodes = diagram.get("nodes") or []
    edges = diagram.get("edges")

    _text(rep, diagram, "title", where, 40, required=False)

    lane_ids = set()
    for i, lane in enumerate(lanes):
        if "id" not in lane or "label" not in lane:
            rep.fail("%s.lanes[%d]" % (where, i), "needs id and label")
            continue
        if lane["id"] in lane_ids:
            rep.fail("%s.lanes[%d]" % (where, i), "duplicate lane id %r" % lane["id"])
        lane_ids.add(lane["id"])
        _text(rep, lane, "label", "%s.lanes[%d]" % (where, i), 28)

    node_ids = set()
    for i, node in enumerate(nodes):
        nwhere = "%s.nodes[%d]" % (where, i)
        if "id" not in node or "label" not in node:
            rep.fail(nwhere, "needs id and label")
            continue
        if node["id"] in node_ids:
            rep.fail(nwhere, "duplicate node id %r" % node["id"])
        node_ids.add(node["id"])
        _text(rep, node, "label", nwhere, 48)
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
        _text(rep, edge, "label", ewhere, 40, required=False)
        for end in ("from", "to"):
            if edge.get(end) not in endpoints:
                rep.fail(ewhere, "%s %r is not a declared %s id"
                         % (end, edge.get(end), what))


def _validate_rule(rep, check, where):
    """A check that sets a document beside the diff has to produce the document.

    The quote is the project's own wording and the `path:line` is where it says
    it, so a reader can go and read the rule rather than taking precis's word
    for what it says. Without both, the check is precis asserting a rule.
    """
    kind = check.get("kind")
    rule = check.get("rule")

    if kind not in RULE_KINDS:
        if rule is not None:
            rep.fail(where, "rule belongs only to a %s check, not to %r"
                     % (" or ".join(sorted(RULE_KINDS)), kind))
        return

    if not isinstance(rule, dict):
        rep.fail(where, "rule is required for a %r check: quote the wording and "
                        "name the file and line it is written on" % kind)
        return

    rwhere = where + ".rule"
    _text(rep, rule, "quote", rwhere, 200)
    _text(rep, rule, "was", rwhere, 200, required=kind == "rule_change")
    source = rule.get("source")
    if not isinstance(source, str) or not REF_RE.match(source):
        rep.fail(rwhere, "source must anchor the rule to a line, as "
                         "CONTRIBUTING.md:40, got %r" % source)

    # The graph-edge rule, applied here: an edge you cannot point at a line for
    # is an edge you do not draw.
    if not check.get("hunk_ids"):
        rep.fail(where, "a %r check must name the hunks it points at; a "
                        "departure with no changed line to show is not one "
                        "precis reports" % kind)


def _validate_graph(rep, graph, mapped_files):
    """The symbol graph: what calls what, and how we know."""
    where = "change_map.graph"
    if graph is None:
        return
    if not isinstance(graph, dict):
        rep.fail(where, "must be an object or null")
        return

    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        rep.fail(where, "nodes must be an array")
        return
    if not MIN_GRAPH_NODES <= len(nodes) <= MAX_GRAPH_NODES:
        rep.fail(where, "nodes has %d entries; a graph carries %d to %d, and a "
                        "change with nothing to draw sets graph to null"
                 % (len(nodes), MIN_GRAPH_NODES, MAX_GRAPH_NODES))

    node_ids = set()
    changed = False
    for i, node in enumerate(nodes):
        nwhere = "%s.nodes[%d]" % (where, i)
        nid = node.get("id")
        if not nid:
            rep.fail(nwhere, "id is required")
        elif nid in node_ids:
            rep.fail(nwhere, "duplicate node id %r" % nid)
        node_ids.add(nid)
        _text(rep, node, "label", nwhere, 34)
        _text(rep, node, "note", nwhere, 80, required=False)
        rep.enum(node.get("kind"), GRAPH_NODE_KINDS, nwhere, "kind")
        rep.enum(node.get("emphasis"), EMPHASIS, nwhere, "emphasis")
        touched = node.get("emphasis") != "unchanged"
        changed = changed or touched
        path = node.get("path")
        hids = node.get("hunk_ids")
        if not isinstance(hids, list):
            rep.fail(nwhere, "hunk_ids must be an array (empty is allowed)")
            hids = []
        # Unchanged neighbours are context and usually live outside the diff.
        # Anything the change touched has to point at the code that touched it.
        if touched and not hids:
            rep.fail(nwhere, "emphasis is %r, so hunk_ids must name the hunks that "
                             "changed this node" % node.get("emphasis"))
        if hids and not path:
            rep.fail(nwhere, "path is required when hunk_ids is non-empty")
        elif hids and path not in mapped_files:
            rep.fail(nwhere, "path %r carries hunks but does not appear in "
                             "change_map.groups" % path)

    if nodes and not changed:
        rep.fail(where, "every node is 'unchanged'; the graph must show at least "
                        "one thing this change touched")

    edges = graph.get("edges")
    if not isinstance(edges, list) or not edges:
        rep.fail(where, "edges must be a non-empty array")
        return
    for i, edge in enumerate(edges):
        ewhere = "%s.edges[%d]" % (where, i)
        rep.enum(edge.get("kind"), REL_KINDS, ewhere, "kind")
        rep.enum(edge.get("emphasis"), EMPHASIS, ewhere, "emphasis")
        _text(rep, edge, "label", ewhere, 20, required=False)
        for end in ("from", "to"):
            if edge.get(end) not in node_ids:
                rep.fail(ewhere, "%s %r is not a declared node id" % (end, edge.get(end)))
        # An edge you cannot point at a line for is an edge you do not draw.
        ev = edge.get("evidence")
        if not isinstance(ev, dict):
            rep.fail(ewhere, "evidence is required: either hunk_ids or a path:line ref")
            continue
        hids, ref = ev.get("hunk_ids"), ev.get("ref")
        if isinstance(hids, list) and hids:
            continue
        if isinstance(ref, str) and REF_RE.match(ref):
            continue
        rep.fail(ewhere, "evidence must carry a non-empty hunk_ids array or a "
                         "ref of the form 'path/to/file.py:118', got %r" % (ev,))


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
                elif key in ("hunk_id", "sample_hunk_id") and isinstance(value, str):
                    refs.append(("%s.%s" % (path, key), value))
                else:
                    walk(value, "%s.%s" % (path, key))
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, "%s[%d]" % (path, i))

    for section in ("story", "change_map", "contracts", "behavior", "review_pass",
                    "seams"):
        walk(model.get(section), section)
    return refs


def _authored_prose(model):
    """Every (location, string) precis wrote in its own voice.

    The hunk store is diff text and the quoted fields are the author's words;
    neither is precis speaking, so neither is scanned.
    """
    found = []

    def quoted(path):
        return INDEX_RE.sub("[]", path).startswith(QUOTED)

    def walk(node, path):
        if quoted(path):
            return
        if isinstance(node, dict):
            for key, value in node.items():
                here = "%s.%s" % (path, key)
                if isinstance(value, str):
                    if key in PROSE_KEYS and not quoted(here):
                        found.append((here, value))
                elif isinstance(value, list) and here in PROSE_ARRAYS:
                    for i, item in enumerate(value):
                        if isinstance(item, str):
                            found.append(("%s[%d]" % (here, i), item))
                else:
                    walk(value, here)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, "%s[%d]" % (path, i))

    for key, value in model.items():
        if key == "hunks":
            continue
        walk(value, key)
    return found


def verdict_words(model):
    """Prose that reviews rather than describes. Returns (location, word) pairs."""
    hits = []
    for where, text in _authored_prose(model):
        match = VERDICT_RE.search(text)
        if match:
            hits.append((where, match.group(0)))
    return hits


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
                "contracts", "behavior", "review_pass", "seams", "hunks"):
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
    _text(rep, coverage, "note", "coverage", 160, required=False)
    limitations = coverage.get("limitations")
    if not isinstance(limitations, list):
        rep.fail("coverage", "limitations must be an array, even when empty")
    else:
        for i, item in enumerate(limitations):
            if not isinstance(item, str):
                rep.fail("coverage.limitations[%d]" % i, "must be a string")
            elif len(item) > 120:
                rep.fail("coverage.limitations[%d]" % i,
                         "is %d characters, the cap is 120" % len(item))
    # Absent means precis never looked, and owes `limitations` a reason. Present
    # and empty means it looked and this project states no rules. The two are
    # different answers and the report shows them differently.
    rules_read = coverage.get("rules_read")
    if rules_read is not None:
        if not isinstance(rules_read, list):
            rep.fail("coverage", "rules_read must be an array of paths, even "
                                 "when empty")
        else:
            for i, item in enumerate(rules_read):
                if not isinstance(item, str):
                    rep.fail("coverage.rules_read[%d]" % i, "must be a string")
                elif len(item) > 120:
                    rep.fail("coverage.rules_read[%d]" % i,
                             "is %d characters, the cap is 120" % len(item))

    # ---- stats
    stats = model.get("stats") or {}
    for key in ("files_changed", "additions", "deletions", "hunks"):
        _int(rep, stats, key, "stats")
    ratio = stats.get("signal_ratio")
    if not isinstance(ratio, (int, float)) or not 0.0 <= ratio <= 1.0:
        rep.fail("stats", "signal_ratio must be a number in [0, 1], got %r" % ratio)

    # ---- story
    story = model.get("story") or {}
    _text(rep, story, "headline", "story", 100)
    _text(rep, story, "caveat", "story", 160, required=False)
    beats = story.get("beats")
    if not isinstance(beats, list) or not 2 <= len(beats) <= 4:
        rep.fail("story", "beats must be an array of 2 to 4 entries, got %r"
                 % (len(beats) if isinstance(beats, list) else beats))
        beats = beats if isinstance(beats, list) else []
    for i, beat in enumerate(beats):
        bwhere = "story.beats[%d]" % i
        if not isinstance(beat, dict):
            rep.fail(bwhere, "must be an object with label and text")
            continue
        _text(rep, beat, "label", bwhere, 14)
        _text(rep, beat, "text", bwhere, 100)
    if "paragraph" in story:
        rep.fail("story", "paragraph is not part of the contract; the story is "
                          "carried by beats")
    rep.enum(story.get("shape"), SHAPES, "story", "shape")
    tests = story.get("tests")
    if not isinstance(tests, dict):
        rep.fail("story", "tests is required: { state, note } saying whether tests "
                          "in this diff exercise the changed behaviour")
    else:
        rep.enum(tests.get("state"), TEST_STATES, "story.tests", "state")
        _text(rep, tests, "note", "story.tests", 100,
              required=tests.get("state") == "partial")
        behavior_changed = (model.get("behavior") or {}).get("changed")
        if behavior_changed is False and tests.get("state") != "n/a":
            rep.fail("story.tests", "state must be 'n/a' when behavior.changed is "
                                    "false; there is no changed behaviour to exercise")
        if behavior_changed is True and tests.get("state") == "n/a":
            rep.fail("story.tests", "state may not be 'n/a' when behavior.changed "
                                    "is true; say yes, partial, or none")
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
        if delta.get("stated") is not None:
            _text(rep, delta, "stated", "story.intent_delta", 160)
        for key in ("also_does", "not_done"):
            if not isinstance(delta.get(key), list):
                rep.fail("story.intent_delta", "%s must be an array" % key)
        for i, item in enumerate(delta.get("also_does") or []):
            where = "story.intent_delta.also_does[%d]" % i
            _text(rep, item, "summary", where, 120)
            rep.enum(item.get("kind"), DELTA_KINDS, where, "kind")
        for i, item in enumerate(delta.get("not_done") or []):
            where = "story.intent_delta.not_done[%d]" % i
            _text(rep, item, "summary", where, 120)
            _text(rep, item, "note", where, 100, required=False)

    # ---- hunks
    hunks = _validate_hunks(rep, model)

    # ---- change_map
    change_map = model.get("change_map") or {}
    _text(rep, change_map, "summary", "change_map", 140, required=False)
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
        _text(rep, group, "label", where, 40)
        _text(rep, group, "summary", where, 100, required=False)
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
            _text(rep, entry, "note", fwhere, 100, required=False)
            _int(rep, entry, "additions", fwhere)
            _int(rep, entry, "deletions", fwhere)
            if not isinstance(entry.get("hunk_ids"), list):
                rep.fail(fwhere, "hunk_ids must be an array (empty is allowed)")
            if entry.get("status") in ("renamed", "copied") and not entry.get("moved_from"):
                rep.fail(fwhere, "moved_from is required when status is %r" % entry["status"])

    if "graph" not in change_map:
        rep.fail("change_map", "graph is required; use null when there is no call "
                               "relationship worth drawing")
    else:
        _validate_graph(rep, change_map.get("graph"), mapped_files)

    # ---- contracts
    contracts = model.get("contracts")
    if not isinstance(contracts, list):
        rep.fail("contracts", "must be an array, even when empty; an empty array "
                              "says precis looked and no contract changed shape")
        contracts = []
    contract_ids = set()
    for i, entry in enumerate(contracts):
        where = "contracts[%d]" % i
        if not isinstance(entry, dict):
            rep.fail(where, "must be an object")
            continue
        cid = entry.get("id")
        if not cid:
            rep.fail(where, "id is required")
        elif cid in contract_ids:
            rep.fail(where, "duplicate contract id %r" % cid)
        contract_ids.add(cid)
        rep.enum(entry.get("kind"), CONTRACT_KINDS, where, "kind")
        _text(rep, entry, "name", where, 60)
        _text(rep, entry, "note", where, 100, required=False)
        # before/after are transcriptions of code, exempt from the verdict scan
        # like hunk lines, but they still have caps.
        for side in ("before", "after"):
            value = entry.get(side)
            if value is not None and not isinstance(value, str):
                rep.fail(where, "%s must be a string or null" % side)
            elif isinstance(value, str) and len(value) > 120:
                rep.fail(where, "%s is %d characters, the cap is 120"
                         % (side, len(value)))
        if entry.get("before") is None and entry.get("after") is None:
            rep.fail(where, "at least one of before/after is required; null before "
                            "is a new surface, null after is a removed one")
        if not isinstance(entry.get("hunk_ids"), list) or not entry.get("hunk_ids"):
            rep.fail(where, "hunk_ids must be a non-empty array; a contract change "
                            "the diff does not show is not one precis reports")
        callers = entry.get("callers")
        if callers is not None:
            cwhere = where + ".callers"
            if not isinstance(callers, dict):
                rep.fail(cwhere, "must be an object with updated and untouched")
            else:
                _int(rep, callers, "updated", cwhere)
                untouched = callers.get("untouched")
                if not isinstance(untouched, list):
                    rep.fail(cwhere, "untouched must be an array, even when empty")
                else:
                    for ri, ref in enumerate(untouched):
                        if not isinstance(ref, str) or not REF_RE.match(ref):
                            rep.fail("%s.untouched[%d]" % (cwhere, ri),
                                     "must be a path:line ref, as "
                                     "src/reports/audit.py:88, got %r" % (ref,))

    # ---- behavior
    behavior = model.get("behavior") or {}
    changed = behavior.get("changed")
    if not isinstance(changed, bool):
        rep.fail("behavior", "changed must be a boolean")
    elif changed:
        _text(rep, behavior, "summary", "behavior", 180)
        for side in ("before", "after"):
            if behavior.get(side) is None:
                rep.fail("behavior", "%s is required when changed is true" % side)
            else:
                _validate_diagram(rep, behavior[side], "behavior.%s" % side)
        for i, item in enumerate(behavior.get("deltas") or []):
            _text(rep, item, "summary", "behavior.deltas[%d]" % i, 110)
    else:
        if not behavior.get("note"):
            rep.fail("behavior", "note is required when changed is false")
        else:
            _text(rep, behavior, "note", "behavior", 160)

    # ---- review_pass
    review = model.get("review_pass") or {}
    if "preamble" in review:
        rep.fail("review_pass", "preamble is not part of the contract; the section "
                                "subtitle carries the framing")
    steps = review.get("steps")
    checks = review.get("checks")
    skippable = review.get("skippable")
    step_paths, step_hunks = set(), set()
    if not isinstance(steps, list) or not steps:
        rep.fail("review_pass", "steps must be a non-empty array")
        steps = []
    for i, step in enumerate(steps):
        where = "review_pass.steps[%d]" % i
        if step.get("n") != i + 1:
            rep.fail(where, "n is %r, expected %d" % (step.get("n"), i + 1))
        _text(rep, step, "title", where, 60)
        _text(rep, step, "why", where, 140)
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
            _text(rep, note, "text", awhere, 150)
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

    if not isinstance(checks, list):
        rep.fail("review_pass", "checks must be an array, even when empty")
        checks = []
    for i, item in enumerate(checks):
        where = "review_pass.checks[%d]" % i
        rep.enum(item.get("kind"), ATTENTION_KINDS, where, "kind")
        _text(rep, item, "title", where, 80)
        _text(rep, item, "why", where, 180)
        _text(rep, item, "question", where, 140)
        question = item.get("question")
        if isinstance(question, str) and question and not question.rstrip().endswith("?"):
            rep.fail(where, "question must end in a question mark; a check is "
                            "something the reviewer decides, not something precis "
                            "asserts: %r" % question)
        if "severity" in item:
            rep.fail(where, "severity is not part of the contract; precis does "
                            "not score findings")
        _validate_rule(rep, item, where)

    if not isinstance(skippable, list):
        rep.fail("review_pass", "skippable must be an array, even when empty")
        skippable = []
    skipped_files = {}
    for i, group in enumerate(skippable):
        where = "review_pass.skippable[%d]" % i
        _text(rep, group, "label", where, 40)
        _text(rep, group, "reason", where, 150)
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
        sample = group.get("sample_hunk_id")
        if sample is not None:
            hunk = hunks.get(sample)
            if hunk is None:
                rep.fail(where, "sample_hunk_id references unknown hunk %r" % sample)
            elif hunk.get("path") not in files:
                rep.fail(where, "sample_hunk_id %r is from %r, which is not one of "
                                "this group's files" % (sample, hunk.get("path")))

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
            rep.fail("review_pass", "%r is both in the reading order and in the "
                                    "skippable group %r" % (path, skipped_files[path]))
        elif not in_steps and not in_skip:
            rep.fail("review_pass", "%r (change_map group %r) is neither in the "
                                    "reading order nor in any skippable group" % (path, gid))

    if "attention" in model:
        rep.fail("root", "attention was merged into review_pass.checks")
    if "reading_order" in model:
        rep.fail("root", "reading_order was merged into review_pass")

    # ---- seams
    seams = model.get("seams") or {}
    detected = seams.get("detected")
    if not isinstance(detected, bool):
        rep.fail("seams", "detected must be a boolean")
    elif detected:
        if not seams.get("note"):
            rep.fail("seams", "note is required when detected is true")
        else:
            _text(rep, seams, "note", "seams", 160)
        clusters = seams.get("clusters")
        if not isinstance(clusters, list) or len(clusters) < 2:
            rep.fail("seams", "detected means two or more clusters")
            clusters = []
        cluster_ids = {c.get("id") for c in clusters}
        for i, cluster in enumerate(clusters):
            where = "seams.clusters[%d]" % i
            if not cluster.get("id"):
                rep.fail(where, "id is required")
            _text(rep, cluster, "label", where, 40)
            _text(rep, cluster, "summary", where, 140)
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

    # ---- precis describes, it does not judge
    for where, word in verdict_words(model):
        rep.fail(where, "reads as a verdict: %r. Say what the code does, not what "
                        "you make of it." % word)

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
