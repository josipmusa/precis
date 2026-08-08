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
    model["attention"][0]["hunk_ids"] = ["h9999"]
    hits = problems_matching(model, "unknown hunk 'h9999'")
    assert hits and "attention[0]" in hits[0]


def test_reading_step_may_not_reference_a_truncated_hunk(monster):
    hid = next(h for h, v in monster["hunks"].items() if v["truncated"])
    monster["reading_order"]["steps"][0]["hunk_ids"] = [hid]
    assert problems_matching(monster, "truncated hunk")


def test_step_numbering_must_match_position(model):
    model["reading_order"]["steps"][1]["n"] = 7
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
    skip = model["reading_order"]["skippable"][0]
    skip["files"] = skip["files"] + ["src/meridian/refunds/policy.py"]
    skip["file_count"] = len(skip["files"])
    assert problems_matching(model, "both in the reading order and in the skippable")


def test_the_same_file_may_not_be_skipped_twice(model):
    a, b = model["reading_order"]["skippable"][0], model["reading_order"]["skippable"][1]
    b["files"] = b["files"] + a["files"]
    b["file_count"] = len(b["files"])
    assert problems_matching(model, "is also in skippable group")


def test_file_count_must_match_the_file_list(model):
    model["reading_order"]["skippable"][0]["file_count"] = 99
    assert problems_matching(model, "file_count is 99")


def test_low_confidence_story_without_a_caveat_is_refused(model):
    model["story"]["confidence"] = "low"
    model["story"]["caveat"] = None
    assert problems_matching(model, "caveat is required")


def test_behavior_changed_false_needs_a_note(model):
    model["behavior"] = {"changed": False}
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
    model["attention"][0]["kind"] = "codesmell"
    assert problems_matching(model, "role is 'backend'")
    assert problems_matching(model, "change_kind is 'refactor'")
    assert problems_matching(model, "kind is 'codesmell'")


def test_severity_on_an_attention_item_is_refused(model):
    """precis flags significance; it never scores. The schema enforces it."""
    model["attention"][0]["severity"] = "high"
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
    model["reading_order"]["steps"][0]["annotations"][0]["new_line"] = 99999
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
    model["reading_order"]["skippable"][0]["confidence"] = "low"
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
    model["attention"][0]["kind"] = "nope"
    problems = validate(model)
    assert len(problems) >= 3
    assert all(isinstance(p, str) and ": " in p for p in problems)


def test_a_hunk_from_a_file_the_map_omits_is_caught(model):
    model["hunks"]["h19"]["path"] = "src/meridian/not_in_the_map.py"
    assert problems_matching(model, "does not appear in change_map")
