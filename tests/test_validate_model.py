"""The validator has to bite.

Every invariant in references/schema.md Part 4 gets a mutation here: take a valid
fixture, break exactly one thing, assert the validator names it. A validator that
never fails is worse than no validator, because the contract looks enforced.
"""
import copy

import pytest

from validate_model import validate


@pytest.fixture()
def model(fixtures):
    return copy.deepcopy(fixtures["medium"])


@pytest.fixture()
def monster(fixtures):
    return copy.deepcopy(fixtures["monster"])


def problems_matching(model, needle):
    return [p for p in validate(model) if needle in p]


def test_a_valid_model_produces_no_problems(model):
    assert validate(model) == []


def test_unknown_major_schema_version_is_refused(model):
    model["schema_version"] = "2.0"
    assert problems_matching(model, "not supported")


def test_missing_section_is_reported(model):
    del model["seams"]
    assert problems_matching(model, "missing required section 'seams'")


def test_dangling_hunk_reference_names_its_location(model):
    model["review_pass"]["checks"][0]["hunk_ids"] = ["h9999"]
    hits = problems_matching(model, "unknown hunk 'h9999'")
    assert hits and "review_pass.checks[0]" in hits[0]


def test_reading_step_may_not_reference_a_truncated_hunk(monster):
    hid = next(h for h, v in monster["hunks"].items() if v["truncated"])
    monster["review_pass"]["steps"][0]["hunk_ids"] = [hid]
    assert problems_matching(monster, "truncated hunk")


def test_step_numbering_must_match_position(model):
    model["review_pass"]["steps"][1]["n"] = 7
    assert problems_matching(model, "n is 7, expected 2")


def test_a_file_in_neither_steps_nor_skippable_is_caught(model):
    """The invariant that stops precis silently dropping part of a diff."""
    group = model["change_map"]["groups"][0]
    group["files"].append({
        "path": "src/meridian/orphan.py",
        "status": "modified",
        "change_kind": "modified_logic",
        "significance": "supporting",
        "additions": 3,
        "deletions": 1,
        "hunk_ids": [],
    })
    assert problems_matching(model, "neither in the reading order nor in any skippable")


def test_a_file_in_both_steps_and_skippable_is_caught(model):
    skip = model["review_pass"]["skippable"][0]
    skip["files"] = skip["files"] + ["src/meridian/refunds/policy.py"]
    skip["file_count"] = len(skip["files"])
    assert problems_matching(model, "both in the reading order and in the skippable")


def test_the_same_file_may_not_be_skipped_twice(model):
    a, b = model["review_pass"]["skippable"][0], model["review_pass"]["skippable"][1]
    b["files"] = b["files"] + a["files"]
    b["file_count"] = len(b["files"])
    assert problems_matching(model, "is also in skippable group")


def test_file_count_must_match_the_file_list(model):
    model["review_pass"]["skippable"][0]["file_count"] = 99
    assert problems_matching(model, "file_count is 99")


def test_low_confidence_story_without_a_caveat_is_refused(model):
    model["story"]["confidence"] = "low"
    model["story"]["caveat"] = None
    assert problems_matching(model, "caveat is required")


def test_behavior_changed_false_needs_a_note(model):
    model["behavior"] = {"changed": False, "note": None}
    assert problems_matching(model, "note is required when changed is false")


def test_behavior_changed_true_needs_both_diagrams(model):
    del model["behavior"]["after"]
    assert problems_matching(model, "after is required")


def test_diagram_edge_must_point_at_a_declared_node(model):
    model["behavior"]["after"]["edges"][0]["to"] = "nope"
    assert problems_matching(model, "is not a declared node id")


def test_sequence_diagram_edge_must_point_at_a_declared_lane(fixtures):
    small = copy.deepcopy(fixtures["small"])
    small["behavior"]["after"]["edges"][0]["from"] = "nope"
    assert problems_matching(small, "is not a declared lane id")


def test_node_lane_must_be_declared(model):
    model["behavior"]["after"]["nodes"][0]["lane"] = "ghost"
    assert problems_matching(model, "lane 'ghost' is not declared")


def test_unknown_enumeration_values_are_reported(model):
    model["change_map"]["groups"][0]["role"] = "backend"
    model["change_map"]["groups"][0]["files"][0]["change_kind"] = "refactor"
    model["review_pass"]["checks"][0]["kind"] = "codesmell"
    assert problems_matching(model, "role is 'backend'")
    assert problems_matching(model, "change_kind is 'refactor'")
    assert problems_matching(model, "kind is 'codesmell'")


def test_severity_on_a_check_is_refused(model):
    """precis flags significance; it never scores. The schema enforces it."""
    model["review_pass"]["checks"][0]["severity"] = "high"
    assert problems_matching(model, "does not score findings")


def test_hunk_line_counts_must_match_the_header(model):
    hunk = model["hunks"]["h19"]
    hunk["lines"] = hunk["lines"][:-1]
    assert problems_matching(model, "line counts disagree with the header")


def test_a_truncated_hunk_is_exempt_from_the_line_count_check(model):
    hunk = model["hunks"]["h19"]
    hunk["lines"] = hunk["lines"][:-1]
    hunk["truncated"] = True
    assert not problems_matching(model, "line counts disagree")


def test_annotation_line_must_exist_in_its_hunk(model):
    model["review_pass"]["steps"][0]["annotations"][0]["new_line"] = 99999
    assert problems_matching(model, "is not a line in hunk")


def test_seams_detected_needs_two_clusters_and_a_note(model):
    model["seams"] = {"detected": True, "note": None, "clusters": [{"id": "s1"}]}
    assert problems_matching(model, "note is required when detected is true")
    assert problems_matching(model, "two or more clusters")


def test_seam_independent_of_must_reference_a_sibling(monster):
    monster["seams"]["clusters"][0]["independent_of"] = ["s9"]
    assert problems_matching(monster, "unknown cluster 's9'")


def test_duplicate_file_across_change_map_groups_is_caught(model):
    groups = model["change_map"]["groups"]
    groups[1]["files"].append(copy.deepcopy(groups[0]["files"][0]))
    assert problems_matching(model, "also appears in group")


def test_renamed_file_needs_moved_from(monster):
    entry = next(f for g in monster["change_map"]["groups"] for f in g["files"]
                 if f["status"] == "renamed")
    del entry["moved_from"]
    assert problems_matching(monster, "moved_from is required")


def test_skippable_confidence_below_medium_is_refused(model):
    model["review_pass"]["skippable"][0]["confidence"] = "low"
    assert problems_matching(model, "anything less confident belongs in steps")


def test_signal_ratio_outside_zero_to_one_is_refused(model):
    model["stats"]["signal_ratio"] = 1.4
    assert problems_matching(model, "signal_ratio must be a number in [0, 1]")


def test_limitations_must_be_an_array_not_a_string(model):
    model["coverage"]["limitations"] = "none"
    assert problems_matching(model, "limitations must be an array")


def test_a_non_object_model_is_rejected_without_crashing():
    assert validate([1, 2, 3]) == ["root: report model must be a JSON object"]


def test_every_problem_is_a_readable_string(model):
    model["schema_version"] = "9.9"
    del model["story"]["headline"]
    model["review_pass"]["checks"][0]["kind"] = "nope"
    problems = validate(model)
    assert len(problems) >= 3
    assert all(isinstance(p, str) and ": " in p for p in problems)


def test_a_hunk_from_a_file_the_map_omits_is_caught(model):
    model["hunks"]["h19"]["path"] = "src/meridian/not_in_the_map.py"
    assert problems_matching(model, "does not appear in change_map")


# ---------------------------------------------- caps, verdicts, and the graph

def test_an_over_long_field_names_itself(model):
    model["review_pass"]["steps"][0]["why"] = "x" * 200
    hits = problems_matching(model, "the cap is 140")
    assert hits and "review_pass.steps[0]" in hits[0]
    assert "200 characters" in hits[0]


def test_the_story_paragraph_cannot_come_back(model):
    model["story"]["paragraph"] = "Once upon a time there were four sentences."
    assert problems_matching(model, "carried by beats")


def test_beats_must_number_two_to_four(model):
    model["story"]["beats"] = model["story"]["beats"][:1]
    assert problems_matching(model, "beats must be an array of 2 to 4")


def test_a_verdict_word_is_refused_with_its_location(model):
    model["review_pass"]["checks"][0]["why"] = "The migration order here is wrong."
    hits = problems_matching(model, "reads as a verdict")
    assert hits and "review_pass.checks[0].why" in hits[0]


def test_the_authors_own_words_are_not_scanned(model):
    """A PR titled "Fix double refund bug" keeps its title."""
    model["source"]["title"] = "Fix the double refund bug"
    model["source"]["description"] = "This should never have shipped."
    model["story"]["intent_delta"]["stated"] = "Fix a bug in the refund path."
    assert not problems_matching(model, "reads as a verdict")


def test_a_check_that_asserts_instead_of_asking_is_refused(model):
    model["review_pass"]["checks"][0]["question"] = "This migration needs splitting."
    assert problems_matching(model, "must end in a question mark")


# --------------------------------------------- checks against a stated rule

def rule_check(**over):
    check = {
        "kind": "documented_rule",
        "title": "CONTRIBUTING.md asks for a test beside each behaviour change",
        "rule": {
            "source": "CONTRIBUTING.md:40",
            "quote": "Every behaviour change ships with the test that pins it.",
            "was": None,
        },
        "why": "The refund policy change arrives with no test alongside it.",
        "question": "Is this covered by a test that lives outside this repository?",
        "path": "src/meridian/refunds/policy.py",
        "hunk_ids": ["h1"],
    }
    check.update(over)
    return check


def test_a_well_formed_rule_check_validates(model):
    model["review_pass"]["checks"].append(rule_check())
    assert validate(model) == []


def test_a_rule_check_without_its_rule_is_refused(model):
    """The quote and its `path:line` are the evidence. Without them the check is
    precis asserting a rule rather than pointing at one."""
    model["review_pass"]["checks"].append(rule_check(rule=None))
    assert problems_matching(model, "rule is required")


def test_a_rule_on_any_other_kind_is_refused(model):
    model["review_pass"]["checks"][0]["rule"] = rule_check()["rule"]
    assert problems_matching(model, "rule belongs only to")


def test_a_rule_must_be_anchored_to_a_line(model):
    model["review_pass"]["checks"].append(
        rule_check(rule={"source": "CONTRIBUTING.md", "quote": "Ship a test."}))
    assert problems_matching(model, "CONTRIBUTING.md:40")


def test_a_rule_change_must_quote_the_wording_it_replaces(model):
    model["review_pass"]["checks"].append(rule_check(
        kind="rule_change",
        title="CONTRIBUTING.md changes what it asks of a behaviour change",
        question="Which existing files are expected to follow the new wording?"))
    assert problems_matching(model, "was is required")


def test_a_departure_must_point_at_a_changed_line(model):
    """The graph-edge rule, applied here: a departure you cannot point at a line
    for is a departure you do not report."""
    model["review_pass"]["checks"].append(rule_check(hunk_ids=[]))
    assert problems_matching(model, "must name the hunks")


def test_a_quoted_rule_may_say_should(model):
    """Rules routinely say "should". Precis quotes them as they are written."""
    model["review_pass"]["checks"].append(rule_check(rule={
        "source": "CONTRIBUTING.md:40",
        "quote": "You should never land a behaviour change without a test.",
        "was": "Consider adding a test; a missing one is a problem in review.",
    }, kind="rule_change",
        question="Which existing files are expected to follow the new wording?"))
    assert not problems_matching(model, "reads as a verdict")


def test_precis_own_words_beside_a_quoted_rule_are_still_scanned(model):
    model["review_pass"]["checks"].append(
        rule_check(why="The rule is wrong about where tests belong."))
    hits = problems_matching(model, "reads as a verdict")
    assert hits and ".why" in hits[0]


def test_rules_read_records_what_was_read(model):
    model["coverage"]["rules_read"] = ["CONTRIBUTING.md", "docs/adr/0004-errors.md"]
    assert validate(model) == []


def test_rules_read_must_be_an_array_not_a_string(model):
    model["coverage"]["rules_read"] = "CONTRIBUTING.md"
    assert problems_matching(model, "rules_read must be an array")


def test_a_graph_edge_without_evidence_is_refused(model):
    del model["change_map"]["graph"]["edges"][0]["evidence"]
    assert problems_matching(model, "evidence is required")


def test_a_graph_edge_needs_hunks_or_a_line_reference(model):
    model["change_map"]["graph"]["edges"][0]["evidence"] = {"ref": "somewhere in the file"}
    assert problems_matching(model, "path/to/file.py:118")


def test_a_changed_graph_node_must_name_its_hunks(model):
    node = next(n for n in model["change_map"]["graph"]["nodes"] if n["emphasis"] != "unchanged")
    node["hunk_ids"] = []
    assert problems_matching(model, "hunk_ids must name the hunks that changed this node")


def test_an_unchanged_graph_node_may_live_outside_the_diff(fixtures):
    """The caller that did not change is exactly the context GitHub hides."""
    small = copy.deepcopy(fixtures["small"])
    outside = [n for n in small["change_map"]["graph"]["nodes"]
               if n["emphasis"] == "unchanged" and n.get("path")]
    assert outside, "the small fixture should carry unchanged context nodes"
    assert validate(small) == []


def test_a_graph_node_with_hunks_must_be_in_the_change_map(model):
    node = next(n for n in model["change_map"]["graph"]["nodes"] if n["hunk_ids"])
    node["path"] = "src/meridian/nowhere.py"
    assert problems_matching(model, "does not appear in\nchange_map.groups".replace("\n", " "))


def test_a_graph_of_only_unchanged_nodes_is_refused(model):
    for node in model["change_map"]["graph"]["nodes"]:
        node["emphasis"] = "unchanged"
        node["hunk_ids"] = []
    assert problems_matching(model, "must show at least")


def test_too_many_graph_nodes_is_refused(model):
    graph = model["change_map"]["graph"]
    template = graph["nodes"][0]
    while len(graph["nodes"]) <= 12:
        clone = copy.deepcopy(template)
        clone["id"] = "extra%d" % len(graph["nodes"])
        graph["nodes"].append(clone)
    assert problems_matching(model, "a graph carries 2 to 12")


def test_a_null_graph_is_valid(model):
    model["change_map"]["graph"] = None
    assert validate(model) == []


def test_a_missing_graph_key_is_refused(model):
    del model["change_map"]["graph"]
    assert problems_matching(model, "use null when there is no call relationship")


def test_the_old_sections_are_refused_by_name(model):
    model["attention"] = []
    model["reading_order"] = {}
    assert problems_matching(model, "attention was merged into review_pass.checks")
    assert problems_matching(model, "reading_order was merged into review_pass")


# ------------------------------------------- shape, tests, and the contracts

def test_an_unknown_story_shape_is_refused(model):
    model["story"]["shape"] = "improvement"
    assert problems_matching(model, "shape is 'improvement'")


def test_story_tests_is_required(model):
    del model["story"]["tests"]
    assert problems_matching(model, "tests is required")


def test_tests_na_is_required_exactly_when_behavior_is_unchanged(model):
    model["story"]["tests"] = {"state": "n/a"}
    assert problems_matching(model, "may not be 'n/a' when behavior.changed is true")
    model["behavior"] = {"changed": False, "note": "Pure rename: every call path "
                                                   "produces the same results."}
    model["story"]["tests"] = {"state": "yes"}
    assert problems_matching(model, "must be 'n/a' when behavior.changed is false")


def test_partial_test_coverage_needs_a_note(model):
    model["story"]["tests"] = {"state": "partial"}
    assert problems_matching(model, "note is required")


def test_contracts_must_be_an_array(model):
    model["contracts"] = None
    assert problems_matching(model, "contracts")


def contract(**over):
    entry = {
        "id": "c1",
        "kind": "schema",
        "name": "processed_events",
        "before": None,
        "after": "id, event_id UNIQUE, claimed_at",
        "hunk_ids": ["h19"],
    }
    entry.update(over)
    return entry


def test_a_well_formed_contract_validates(model):
    model["contracts"] = [contract()]
    assert validate(model) == []


def test_a_contract_needs_a_before_or_an_after(model):
    model["contracts"] = [contract(after=None)]
    assert problems_matching(model, "at least one of before/after")


def test_a_contract_must_point_at_the_diff(model):
    model["contracts"] = [contract(hunk_ids=[])]
    assert problems_matching(model, "hunk_ids must be a non-empty array")


def test_a_contract_hunk_reference_must_resolve(model):
    model["contracts"] = [contract(hunk_ids=["h9999"])]
    hits = problems_matching(model, "unknown hunk 'h9999'")
    assert hits and "contracts[0]" in hits[0]


def test_an_untouched_caller_must_be_a_line_reference(model):
    model["contracts"] = [contract(callers={"updated": 2,
                                            "untouched": ["somewhere nearby"]})]
    assert problems_matching(model, "must be a path:line ref")


def test_contract_before_and_after_are_code_not_prose(model):
    """A signature called shouldRetry() is a transcription, not a verdict."""
    model["contracts"] = [contract(before="shouldRetry(attempt)",
                                   after="shouldRetry(attempt, budget)")]
    assert not problems_matching(model, "reads as a verdict")


def test_a_contract_note_is_still_precis_voice(model):
    model["contracts"] = [contract(note="The old default was wrong.")]
    hits = problems_matching(model, "reads as a verdict")
    assert hits and "contracts[0].note" in hits[0]


def test_a_skip_sample_must_come_from_the_groups_own_files(model):
    skip = model["review_pass"]["skippable"][0]
    outside = next(h for h, v in model["hunks"].items()
                   if v["path"] not in skip["files"])
    skip["sample_hunk_id"] = outside
    assert problems_matching(model, "is not one of this group's files")
