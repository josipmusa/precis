"""Discovery is a script so that `coverage.rules_read` is a record, not a claim.

A grep composed fresh on each run gives a different answer on each run, and a
report that says it read the house rules has to be right about that. These tests
hold the two properties that makes true: the same input finds the same documents,
and every document it returns says why it was picked.
"""
import json
import subprocess
import sys

import pytest
from conftest import SCRIPTS

import find_rules


def pre(*files, hunks=None):
    """The smallest pre-model shaped like the real thing."""
    return {
        "schema_version": "1.0",
        "files": [
            {"path": path, "old_path": None, "status": status,
             "additions": 1, "deletions": 0, "is_binary": False,
             "hunk_ids": list(ids)}
            for path, status, ids in files
        ],
        "hunks": hunks or {},
    }


def touched(path, status="modified", ids=()):
    return (path, status, ids)


def write(root, path, text="rule text\n"):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def paths(result):
    return [d["path"] for d in result["docs"]]


# ------------------------------------------------------------------ discovery

def test_the_root_rules_file_is_found(tmp_path):
    write(tmp_path, "CLAUDE.md")
    write(tmp_path, "src/app.py", "x = 1\n")
    result = find_rules.find(pre(touched("src/app.py")), tmp_path)
    assert paths(result) == ["CLAUDE.md"]


@pytest.mark.parametrize("name", [
    "CLAUDE.md", "AGENTS.md", ".cursorrules", "CONTRIBUTING.md",
    "STYLE.md", "CONVENTIONS.md", ".github/copilot-instructions.md",
])
def test_every_conventional_name_is_looked_for(tmp_path, name):
    write(tmp_path, name)
    result = find_rules.find(pre(touched("src/app.py")), tmp_path)
    assert paths(result) == [name]


def test_adr_and_convention_docs_under_docs_are_found(tmp_path):
    write(tmp_path, "docs/adr/0004-errors.md")
    write(tmp_path, "docs/naming-conventions.md")
    write(tmp_path, "docs/style-guide.md")
    write(tmp_path, "docs/architecture.md")  # prose, not a rule document
    result = find_rules.find(pre(touched("src/app.py")), tmp_path)
    assert paths(result) == [
        "docs/adr/0004-errors.md", "docs/naming-conventions.md",
        "docs/style-guide.md",
    ]


def test_the_nearest_rules_file_comes_first(tmp_path):
    """A package's own rules are the ones a reader of that package needs first.
    The root document still governs, so both are read."""
    write(tmp_path, "CLAUDE.md")
    write(tmp_path, "packages/api/CLAUDE.md")
    result = find_rules.find(pre(touched("packages/api/handler.py")), tmp_path)
    assert paths(result) == ["packages/api/CLAUDE.md", "CLAUDE.md"]


def test_an_untouched_package_contributes_nothing(tmp_path):
    """This is what scoping to the diff means: rules that govern code the change
    never touches are not rules this change can depart from."""
    write(tmp_path, "packages/api/CLAUDE.md")
    write(tmp_path, "packages/web/CLAUDE.md")
    result = find_rules.find(pre(touched("packages/api/handler.py")), tmp_path)
    assert paths(result) == ["packages/api/CLAUDE.md"]


def test_a_doc_the_diff_changes_carries_its_hunks(tmp_path):
    """The analysis phase needs those to resolve the rule as it stands at head."""
    write(tmp_path, "CLAUDE.md")
    result = find_rules.find(pre(touched("CLAUDE.md", ids=("h1", "h2"))), tmp_path)
    doc = result["docs"][0]
    assert doc["in_diff"] is True and doc["hunk_ids"] == ["h1", "h2"]


def test_a_doc_added_by_the_diff_is_listed_though_it_is_not_on_disk(tmp_path):
    """A checkout sitting on the base has no copy of a file the change adds."""
    result = find_rules.find(pre(touched("CONVENTIONS.md", status="added",
                                         ids=("h1",))), tmp_path)
    doc = result["docs"][0]
    assert doc["path"] == "CONVENTIONS.md"
    assert doc["in_diff"] is True and doc["bytes"] is None


def test_a_doc_the_diff_deletes_is_not_read(tmp_path):
    """Rules are read as of head, and at head this document does not exist."""
    write(tmp_path, "STYLE.md")
    result = find_rules.find(pre(touched("STYLE.md", status="deleted")), tmp_path)
    assert paths(result) == []
    assert any("deleted" in s for s in result["skipped"])


def test_a_changed_doc_is_read_even_when_it_matches_no_convention(tmp_path):
    """A document the change edits is relevant to the change by construction."""
    write(tmp_path, "docs/house-rules.md")
    result = find_rules.find(pre(touched("docs/house-rules.md", ids=("h1",))), tmp_path)
    assert paths(result) == ["docs/house-rules.md"]


def test_a_changed_source_file_is_not_mistaken_for_a_document(tmp_path):
    write(tmp_path, "src/app.py", "x = 1\n")
    result = find_rules.find(pre(touched("src/app.py")), tmp_path)
    assert paths(result) == []


def test_a_document_is_listed_once_however_many_ways_it_was_found(tmp_path):
    write(tmp_path, "CONTRIBUTING.md")
    result = find_rules.find(pre(touched("CONTRIBUTING.md", ids=("h1",)),
                                 touched("src/app.py")), tmp_path)
    assert paths(result) == ["CONTRIBUTING.md"]
    assert len(result["docs"][0]["reasons"]) >= 2


# -------------------------------------------------------------------- honesty

def test_every_document_says_why_it_was_picked(tmp_path):
    write(tmp_path, "CLAUDE.md")
    write(tmp_path, "docs/adr/0001-x.md")
    result = find_rules.find(pre(touched("src/app.py")), tmp_path)
    assert result["docs"]
    for doc in result["docs"]:
        assert doc["reasons"], doc["path"]


def test_the_document_cap_reports_what_it_dropped(tmp_path):
    for i in range(find_rules.MAX_DOCS + 3):
        write(tmp_path, "docs/adr/%04d-decision.md" % i)
    result = find_rules.find(pre(touched("src/app.py")), tmp_path)
    assert len(result["docs"]) == find_rules.MAX_DOCS
    assert len(result["skipped"]) == 3
    assert all("cap" in s for s in result["skipped"])


def test_the_byte_cap_reports_what_it_dropped(tmp_path):
    write(tmp_path, "CLAUDE.md", "x" * (find_rules.MAX_BYTES + 1))
    write(tmp_path, "CONTRIBUTING.md")
    result = find_rules.find(pre(touched("src/app.py")), tmp_path)
    assert paths(result) == ["CLAUDE.md"]
    assert any("CONTRIBUTING.md" in s for s in result["skipped"])


def test_the_same_input_gives_byte_identical_output(tmp_path):
    write(tmp_path, "CLAUDE.md")
    write(tmp_path, "packages/api/CONTRIBUTING.md")
    write(tmp_path, "docs/adr/0002-y.md")
    model = pre(touched("packages/api/handler.py"), touched("src/app.py"))
    first = json.dumps(find_rules.find(model, tmp_path), sort_keys=False)
    second = json.dumps(find_rules.find(model, tmp_path), sort_keys=False)
    assert first == second


def test_discovery_does_not_wander_outside_the_root(tmp_path):
    """A path that climbs out of the checkout is not a document in it."""
    write(tmp_path, "outside/CLAUDE.md")
    root = tmp_path / "repo"
    write(root, "src/app.py", "x = 1\n")
    result = find_rules.find(pre(touched("../outside/CLAUDE.md")), root)
    assert paths(result) == []


# ------------------------------------------------------------------- the CLI

def run_cli(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "find_rules.py"), *args],
        capture_output=True, text=True,
    )


def test_the_cli_writes_where_it_is_told(tmp_path):
    write(tmp_path, "CLAUDE.md")
    model = tmp_path / "pre.json"
    model.write_text(json.dumps(pre(touched("src/app.py"))), encoding="utf-8")
    out = tmp_path / "rules.json"

    result = run_cli(str(model), "--root", str(tmp_path), "-o", str(out))
    assert result.returncode == 0, result.stderr
    assert json.loads(out.read_text(encoding="utf-8"))["docs"][0]["path"] == "CLAUDE.md"


def test_the_cli_refuses_something_that_is_not_a_pre_model(tmp_path):
    model = tmp_path / "pre.json"
    model.write_text('{"nope": true}', encoding="utf-8")
    result = run_cli(str(model), "--root", str(tmp_path))
    assert result.returncode == 1
    assert "pre-model" in result.stderr


def test_the_cli_reads_stdin(tmp_path):
    write(tmp_path, "AGENTS.md")
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "find_rules.py"), "-", "--root", str(tmp_path)],
        input=json.dumps(pre(touched("src/app.py"))),
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["docs"][0]["path"] == "AGENTS.md"
