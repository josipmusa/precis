"""The fixtures are the schema's test suite.

Every fixture must validate, must be internally consistent with the diff it was
built from, and must keep the anti-review guarantee that the whole tool rests on.
"""
import json
import re

import pytest
from conftest import FIXTURES, REFERENCES

from validate_model import validate


def test_every_fixture_has_its_source_diff(fixture_model):
    name, _ = fixture_model
    assert (FIXTURES / f"{name}.diff").exists(), (
        f"{name}.json has no {name}.diff; a fixture is a pair"
    )


def test_fixture_validates(fixture_model):
    name, model = fixture_model
    problems = validate(model, name)
    assert problems == [], "\n".join(problems)


def test_schema_doc_minimal_example_validates():
    """The schema points at a shipped minimal model that remains valid."""
    text = (REFERENCES / "schema.md").read_text(encoding="utf-8")
    marker = "- A minimal valid report model"
    assert marker in text, "schema.md lost its minimal example section"
    assert "assets/fixtures/small.json" in text[text.index(marker):]
    model = json.loads((FIXTURES / "small.json").read_text(encoding="utf-8"))
    problems = validate(model, "schema.md minimal example")
    assert problems == [], "\n".join(problems)


def test_stats_match_the_hunks(fixture_model):
    """stats are deterministic facts; they must agree with the hunk store."""
    name, model = fixture_model
    counted_files = sum(len(g["files"]) for g in model["change_map"]["groups"])
    assert counted_files == model["stats"]["files_changed"]

    additions = sum(f["additions"] for g in model["change_map"]["groups"] for f in g["files"])
    deletions = sum(f["deletions"] for g in model["change_map"]["groups"] for f in g["files"])
    assert additions == model["stats"]["additions"]
    assert deletions == model["stats"]["deletions"]


def test_coverage_counts_are_consistent(fixture_model):
    name, model = fixture_model
    coverage = model["coverage"]
    assert coverage["hunks_read"] <= coverage["hunks_total"]
    assert coverage["files_read"] <= coverage["files_total"]
    assert coverage["hunks_total"] == model["stats"]["hunks"]
    assert coverage["files_total"] == model["stats"]["files_changed"]
    if coverage["tier"] == "full":
        assert coverage["hunks_read"] == coverage["hunks_total"]
        assert not any(h["truncated"] for h in model["hunks"].values()), (
            "a 'full' read cannot contain truncated hunks"
        )


def test_reading_order_starts_at_a_core_hunk(fixture_model):
    """Step 1 is the change itself, never the entry point or the test."""
    name, model = fixture_model
    first = model["review_pass"]["steps"][0]
    kinds = {model["hunks"][h]["significance"] for h in first["hunk_ids"]}
    assert "core" in kinds, (
        f"{name}: step 1 ({first['title']!r}) references no core hunk"
    )


def test_mechanical_hunks_are_never_in_the_reading_order_alone(fixture_model):
    """A step made only of mechanical hunks is asking a reader to read ripple."""
    name, model = fixture_model
    for step in model["review_pass"]["steps"]:
        kinds = {model["hunks"][h]["significance"] for h in step["hunk_ids"]}
        assert kinds != {"mechanical"}, (
            f"{name}: step {step['n']} ({step['title']!r}) is entirely mechanical"
        )


# Words that turn a comprehension artifact into a review. This is the product
# constraint, enforced. See references/analysis.md.
VERDICT_WORDS = [
    r"\bshould\b", r"\bshouldn't\b", r"\bought to\b", r"\bmust be fixed\b",
    r"\bbug\b", r"\bbuggy\b", r"\bbroken\b", r"\bincorrect\b", r"\bwrong\b",
    r"\bconsider\b", r"\bsuggest\b", r"\brecommend\b", r"\bimprove\b",
    r"\bcleaner\b", r"\bbetter\b", r"\bbad\b", r"\bpoor\b", r"\bugly\b",
    r"\bcode smell\b", r"\banti-pattern\b", r"\bnit\b", r"\bnitpick\b",
    r"\brisky\b", r"\bdangerous\b", r"\bunsafe\b", r"\bproblem\b",
    r"\bissue with\b", r"\bfails to\b", r"\bmissing\b", r"\bneeds to\b",
]

# Prose the report itself speaks. `source.description` is the author's own text
# and `hunks[].lines[].c` is their code; precis quotes both verbatim.
def _authored_prose(model):
    out = []

    def walk(node, path):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("description", "lines"):
                    continue
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]")
        elif isinstance(node, str):
            out.append((path, node))

    for section in ("story", "change_map", "behavior", "review_pass",
                    "seams", "coverage"):
        walk(model.get(section), section)
    return out


def test_no_review_verdicts_anywhere(fixture_model):
    """The hard rule, as a test. precis describes; it never judges."""
    name, model = fixture_model
    hits = []
    for path, text in _authored_prose(model):
        for pattern in VERDICT_WORDS:
            if re.search(pattern, text, re.I):
                hits.append(f"{name} {path}: {pattern} in {text[:110]!r}")
    assert hits == [], "\n".join(hits)


def test_checks_never_carry_a_score(fixture_model):
    name, model = fixture_model
    for item in model["review_pass"]["checks"]:
        assert "severity" not in item
        assert "priority" not in item
        assert "score" not in item


def test_every_check_asks_a_question_precis_cannot_answer(fixture_model):
    """A check hands the decision to the reviewer. If it does not end in a
    question mark it has become an assertion, which is a verdict."""
    name, model = fixture_model
    for item in model["review_pass"]["checks"]:
        question = item["question"]
        assert question.rstrip().endswith("?"), f"{name}: {question!r}"
        assert len(question) <= 140, f"{name}: question is {len(question)} chars"


def test_low_confidence_story_is_labelled(fixture_model):
    name, model = fixture_model
    story = model["story"]
    if story["confidence"] != "high":
        assert story.get("caveat"), f"{name}: unlabelled {story['confidence']} confidence story"


def test_skippable_groups_earn_the_skip(fixture_model):
    """A reason that does not explain the mechanism is a demand for trust."""
    name, model = fixture_model
    for group in model["review_pass"]["skippable"]:
        assert len(group["reason"]) > 60, (
            f"{name}: {group['label']!r} reason is too thin to earn a skip: "
            f"{group['reason']!r}"
        )


def test_diagram_sizes_stay_comprehensible(fixture_model):
    name, model = fixture_model
    behavior = model["behavior"]
    if not behavior["changed"]:
        return
    for side in ("before", "after"):
        diagram = behavior[side]
        assert len(diagram.get("lanes") or []) <= 8, f"{name}.{side}: too many lanes"
        assert len(diagram.get("nodes") or []) <= 20, f"{name}.{side}: too many nodes"
        for node in diagram.get("nodes") or []:
            assert len(node["label"]) <= 48, f"{name}.{side}: label too long: {node['label']!r}"
        for edge in diagram.get("edges") or []:
            if edge.get("label"):
                assert len(edge["label"]) <= 40, (
                    f"{name}.{side}: edge label too long: {edge['label']!r}"
                )


def test_headline_is_a_statement_not_a_verdict(fixture_model):
    name, model = fixture_model
    headline = model["story"]["headline"]
    assert len(headline) <= 100, f"{name}: headline is {len(headline)} chars"
    assert not headline.endswith("?"), f"{name}: headline is a question"


# ------------------------------------------------------- the shape of a page

# Nothing in the report may become a wall of text. The validator caps each field
# individually; this is the ceiling across all of them, and the guarantee that
# report length tracks the change rather than the size of the diff. The layer
# narratives are the one deliberate exception: 2-4 sentences per group is the
# layer chapter's whole content, so the budget carries their allowance.
PROSE_BUDGET_WORDS = 2300
FIRST_SCREEN_WORDS = 70


def test_no_field_is_a_wall_of_text(fixture_model):
    from validate_model import _authored_prose
    name, model = fixture_model
    for where, text in _authored_prose(model):
        cap = 480 if where.endswith(".narrative") else 180
        assert len(text) <= cap, f"{name} {where}: {len(text)} chars, {text[:80]!r}"


def test_the_report_stays_within_its_prose_budget(fixture_model):
    from validate_model import _authored_prose
    name, model = fixture_model
    words = sum(len(text.split()) for _, text in _authored_prose(model))
    assert words <= PROSE_BUDGET_WORDS, f"{name}: {words} words of prose"


def test_the_first_screen_scans_in_seconds(fixture_model):
    """Headline plus beats is everything above the fold. It has to be readable
    in one look, on any size of change."""
    name, model = fixture_model
    story = model["story"]
    words = len(story["headline"].split())
    words += sum(len(b["label"].split()) + len(b["text"].split()) for b in story["beats"])
    assert words <= FIRST_SCREEN_WORDS, f"{name}: first screen is {words} words"
    assert 2 <= len(story["beats"]) <= 4


def test_the_graph_stays_readable(fixture_model):
    """Twelve nodes is the ceiling, and every node the change touched points at
    the hunks that touched it."""
    name, model = fixture_model
    graph = model["change_map"]["graph"]
    if graph is None:
        return
    assert 2 <= len(graph["nodes"]) <= 12, f"{name}: {len(graph['nodes'])} nodes"
    mapped = {f["path"] for g in model["change_map"]["groups"] for f in g["files"]}
    for node in graph["nodes"]:
        if node["emphasis"] != "unchanged":
            assert node["hunk_ids"], f"{name}: {node['label']!r} claims a change with no hunk"
        if node["hunk_ids"]:
            assert node["path"] in mapped, f"{name}: {node['path']!r} is not in the change map"
    for edge in graph["edges"]:
        evidence = edge["evidence"]
        assert evidence.get("hunk_ids") or re.match(r"^[^\s:]+:\d+$", evidence.get("ref", "")), (
            f"{name}: edge {edge['from']}->{edge['to']} has no evidence"
        )


def lines_by_significance(model):
    """The page's own arithmetic: per hunk where the hunks account for the
    whole file, per file where a truncated or missing hunk would lose lines."""
    hunks = model["hunks"]
    by = {"core": 0, "supporting": 0, "mechanical": 0}
    for group in model["change_map"]["groups"]:
        for entry in group["files"]:
            ids = entry.get("hunk_ids") or []
            found = [hunks.get(i) for i in ids]
            if not found or any(h is None or h["truncated"] for h in found):
                by[entry["significance"]] += entry["additions"] + entry["deletions"]
                continue
            for hunk in found:
                changed = sum(1 for line in hunk["lines"] if line["t"] != " ")
                by[hunk.get("significance") or entry["significance"]] += changed
    return by


def test_the_stated_signal_ratio_matches_the_model_it_describes(fixture_model):
    """The headline percentage and the bar beside it are the same number twice.

    A report that says 14% next to a bar drawn from a different sum is a report
    arguing with itself, and the reader has no way to tell which half is right.
    """
    name, model = fixture_model
    by = lines_by_significance(model)
    total = sum(by.values())
    assert total, name
    stated = model["stats"]["signal_ratio"]
    derived = by["core"] / total
    assert abs(stated - derived) <= 0.01, (
        f"{name}: signal_ratio is {stated}, the model's own lines give "
        f"{derived:.2f} ({by['core']} core of {total})"
    )
