"""The assembly step, held to the fixtures it has to be able to reproduce.

`build_model.py` exists so that no diff line is ever retyped. The test that
matters most is therefore the round trip: hollow out a hand-written fixture,
rebuild it from the parsed diff, and require the result back. If the script can
reconstruct a model a person wrote by hand, it is copying rather than inventing.
"""
import copy
import json
import subprocess
import sys

import pytest
from conftest import FIXTURE_NAMES, FIXTURES, SCRIPTS

import build_model
import classify
import parse_diff


def pre(name):
    return classify.classify(
        parse_diff.parse_diff(parse_diff.read_diff(str(FIXTURES / f"{name}.diff"))))


def hollow(model):
    """The analysis file: the same model with judgement-only hunk entries.

    A fixture hunk that was written truncated is an analyst saying "quote this
    lockfile in part", so the hollowed form has to say it too.
    """
    thin = copy.deepcopy(model)
    thin["hunks"] = {}
    for key, hunk in model["hunks"].items():
        stub = {"change_kind": hunk["change_kind"], "significance": hunk["significance"]}
        if hunk["truncated"] and hunk["lines"]:
            stub["quote_lines"] = len(hunk["lines"])
        thin["hunks"][key] = stub
    return thin


def norm(node):
    """Drop null-valued optionals, which the contract treats as absent."""
    if isinstance(node, dict):
        return {k: norm(v) for k, v in node.items() if v is not None}
    if isinstance(node, list):
        return [norm(i) for i in node]
    return node


@pytest.fixture(scope="module")
def pre_models():
    return {name: pre(name) for name in FIXTURE_NAMES}


# --------------------------------------------------------------- round trip

@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_a_hollowed_fixture_rebuilds_into_itself(name, fixtures, pre_models):
    original = fixtures[name]
    built, problems = build_model.assemble(
        hollow(original), pre_models[name],
        generated_at=original["source"]["generated_at"])
    assert problems == []
    assert norm(built) == norm(original)


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_every_rebuilt_hunk_quotes_the_diff_line_for_line(name, fixtures, pre_models):
    """The point of the script, stated without the rest of the model in the way.

    A quoted hunk is a prefix of the parsed one: shortened where the analysis
    asked for that and marked truncated when it is, never reworded.
    """
    built, _ = build_model.assemble(hollow(fixtures[name]), pre_models[name])
    source = pre_models[name]["hunks"]
    assert set(built["hunks"]) == set(source)
    for hid, hunk in built["hunks"].items():
        theirs = source[hid]["lines"]
        assert hunk["lines"] == theirs[:len(hunk["lines"])]
        assert hunk["truncated"] == (len(hunk["lines"]) < len(theirs))
        assert hunk["header"] == source[hid]["header"]
        assert (hunk["old_start"], hunk["new_start"]) == (
            source[hid]["old_start"], source[hid]["new_start"])


# --------------------------------------------------------- what it refuses

def test_a_referenced_hunk_the_analysis_never_classified_is_named(fixtures, pre_models):
    thin = hollow(fixtures["small"])
    del thin["hunks"]["h3"]                     # still referenced by step 2
    _, problems = build_model.assemble(thin, pre_models["small"])
    assert any("h3" in p and "does not classify" in p for p in problems)
    assert any("review_pass" in p for p in problems)


def test_a_hunk_id_the_parser_never_produced_is_refused(fixtures, pre_models):
    thin = hollow(fixtures["small"])
    thin["hunks"]["h99"] = {"change_kind": "new_logic", "significance": "core"}
    _, problems = build_model.assemble(thin, pre_models["small"])
    assert any("h99" in p and "not in the pre-model" in p for p in problems)


@pytest.mark.parametrize("field", ["change_kind", "significance"])
def test_judgement_fields_are_not_optional(field, fixtures, pre_models):
    thin = hollow(fixtures["small"])
    del thin["hunks"]["h1"][field]
    _, problems = build_model.assemble(thin, pre_models["small"])
    assert any(field in p and "h1" in p for p in problems)


def test_the_analysis_may_not_smuggle_diff_text_into_the_stub(fixtures, pre_models):
    """If `lines` were accepted here, a retyped diff would render as fact."""
    thin = hollow(fixtures["small"])
    thin["hunks"]["h1"]["lines"] = [{"t": "+", "c": "not what the file says",
                                     "old": None, "new": 1}]
    _, problems = build_model.assemble(thin, pre_models["small"])
    assert any("lines" in p and "copied" in p for p in problems)


@pytest.mark.parametrize("bad", [0, -3, "8", 2.5, True])
def test_quote_lines_must_be_a_positive_count(bad, fixtures, pre_models):
    thin = hollow(fixtures["small"])
    thin["hunks"]["h1"]["quote_lines"] = bad
    _, problems = build_model.assemble(thin, pre_models["small"])
    assert any("quote_lines" in p for p in problems)


def test_quoting_part_of_a_hunk_says_so_on_the_page(fixtures, pre_models):
    thin = hollow(fixtures["small"])
    thin["hunks"]["h1"]["quote_lines"] = 5
    built, problems = build_model.assemble(thin, pre_models["small"])
    assert problems == []
    hunk = built["hunks"]["h1"]
    assert len(hunk["lines"]) == 5
    assert hunk["truncated"] is True
    assert hunk["lines"] == pre_models["small"]["hunks"]["h1"]["lines"][:5]
    # The counts still describe the whole hunk, not the quoted part.
    assert hunk["new_lines"] == pre_models["small"]["hunks"]["h1"]["new_lines"]


def test_a_stated_count_that_contradicts_the_pre_model_is_an_error(fixtures, pre_models):
    thin = hollow(fixtures["small"])
    thin["stats"]["additions"] = 999
    _, problems = build_model.assemble(thin, pre_models["small"])
    assert any("stats.additions" in p and "999" in p for p in problems)


# ------------------------------------------------------------ what it fills

def test_the_deterministic_counts_come_from_the_pre_model(fixtures, pre_models):
    thin = hollow(fixtures["small"])
    thin["stats"] = {"signal_ratio": 0.71,
                     "changed_lines_by_kind": fixtures["small"]["stats"]["changed_lines_by_kind"]}
    built, problems = build_model.assemble(thin, pre_models["small"])
    assert problems == []
    stats, counted = built["stats"], pre_models["small"]["stats"]
    for field in ("files_changed", "additions", "deletions", "hunks"):
        assert stats[field] == counted[field]
    assert stats["signal_ratio"] == 0.71         # judgement is left alone


def test_coverage_inherits_the_tier_the_budget_set(fixtures, pre_models):
    thin = hollow(fixtures["monster"])
    thin["coverage"].pop("tier")
    thin["coverage"].pop("hunks_total")
    built, _ = build_model.assemble(thin, pre_models["monster"])
    assert built["coverage"]["tier"] == pre_models["monster"]["budget"]["tier"]
    assert built["coverage"]["hunks_total"] == pre_models["monster"]["budget"]["hunks_total"]


def test_an_elided_hunk_arrives_marked_truncated(fixtures):
    """The budget dropping a body and the parser cutting one read the same on
    the page: this hunk is not quoted in full."""
    squeezed = classify.classify(
        parse_diff.parse_diff(parse_diff.read_diff(str(FIXTURES / "monster.diff"))),
        max_bytes=12000)
    thin = hollow(fixtures["monster"])
    built, _ = build_model.assemble(thin, squeezed)
    elided = [h for h in squeezed["hunks"].values() if h["elided"]]
    assert elided, "the budget was supposed to bite at 12k"
    for hunk in elided:
        assert built["hunks"][hunk["id"]]["truncated"] is True
        assert built["hunks"][hunk["id"]]["lines"] == []


def test_the_stamp_is_fixed_when_asked_and_current_when_not(fixtures, pre_models):
    thin = hollow(fixtures["small"])
    thin["source"].pop("generated_at")
    thin["source"].pop("generated_by")
    built, _ = build_model.assemble(thin, pre_models["small"], generated_at="2020-01-01T00:00:00Z")
    assert built["source"]["generated_at"] == "2020-01-01T00:00:00Z"
    assert built["source"]["generated_by"] == "precis %s" % build_model.VERSION

    thin2 = hollow(fixtures["small"])
    thin2["source"].pop("generated_at")
    built2, _ = build_model.assemble(thin2, pre_models["small"])
    assert built2["source"]["generated_at"].endswith("Z")


def test_the_analysis_file_is_not_modified(fixtures, pre_models):
    thin = hollow(fixtures["small"])
    before = json.dumps(thin, sort_keys=True)
    build_model.assemble(thin, pre_models["small"])
    assert json.dumps(thin, sort_keys=True) == before


def test_new_analysis_need_not_author_review_choreography(fixtures, pre_models):
    thin = hollow(fixtures["small"])
    del thin["review_pass"]
    built, problems = build_model.assemble(thin, pre_models["small"])
    assert problems == []
    assert built["review_pass"]["steps"]
    assert built["review_pass"]["checks"] == []
    assert build_model.validate(built) == []


# -------------------------------------------------------------------- CLI

def run(*args, **kwargs):
    return subprocess.run([sys.executable, str(SCRIPTS / "build_model.py"), *args],
                          capture_output=True, text=True, **kwargs)


def test_the_cli_writes_a_model_the_renderer_accepts(tmp_path, fixtures, pre_models):
    analysis = tmp_path / "analysis.json"
    analysis.write_text(json.dumps(hollow(fixtures["medium"])), encoding="utf-8")
    pre_path = tmp_path / "pre.json"
    pre_path.write_text(json.dumps(pre_models["medium"]), encoding="utf-8")
    out = tmp_path / "model.json"

    done = run(str(analysis), "--pre", str(pre_path), "-o", str(out))
    assert done.returncode == 0, done.stderr

    rendered = subprocess.run(
        [sys.executable, str(SCRIPTS / "render_report.py"), str(out),
         "-o", str(tmp_path / "report.html")], capture_output=True, text=True)
    assert rendered.returncode == 0, rendered.stderr
    assert (tmp_path / "report.html").stat().st_size > 10000


def test_a_failing_build_leaves_no_file_behind(tmp_path, fixtures, pre_models):
    thin = hollow(fixtures["small"])
    thin["hunks"]["h1"].pop("significance")
    analysis = tmp_path / "analysis.json"
    analysis.write_text(json.dumps(thin), encoding="utf-8")
    pre_path = tmp_path / "pre.json"
    pre_path.write_text(json.dumps(pre_models["small"]), encoding="utf-8")
    out = tmp_path / "model.json"

    done = run(str(analysis), "--pre", str(pre_path), "-o", str(out))
    assert done.returncode == 1
    assert "significance" in done.stderr
    assert not out.exists(), "a refused build must not leave half a model on disk"


def test_the_contract_is_checked_before_anything_is_written(tmp_path, fixtures, pre_models):
    """A model that assembles cleanly can still violate the contract."""
    thin = hollow(fixtures["small"])
    thin["story"]["headline"] = "This refactor should have used a queue instead."
    analysis = tmp_path / "analysis.json"
    analysis.write_text(json.dumps(thin), encoding="utf-8")
    pre_path = tmp_path / "pre.json"
    pre_path.write_text(json.dumps(pre_models["small"]), encoding="utf-8")
    out = tmp_path / "model.json"

    done = run(str(analysis), "--pre", str(pre_path), "-o", str(out))
    assert done.returncode == 1
    assert not out.exists()
