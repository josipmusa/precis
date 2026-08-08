"""Classification is a hint, but a wrong hint costs a reviewer their attention.

The rules that matter are the demotions: once something is called mechanical it
is summarised rather than quoted, and a real change that lands in that bucket
becomes invisible. So the tests here lean on the boundary cases - a lockfile
against a config file, a generated client against a hand-written one, a
formatter run against an edit that happens to be small.
"""
import json
import subprocess
import sys

import pytest
from conftest import FIXTURES, SCRIPTS

import classify
import parse_diff
from classify import classify as run_classify


def pre(name):
    return parse_diff.parse_diff(parse_diff.read_diff(str(FIXTURES / f"{name}.diff")))


def classified(name, **kwargs):
    return run_classify(pre(name), **kwargs)


def from_diff(diff, **kwargs):
    return run_classify(parse_diff.parse_diff(diff), **kwargs)


def only_file(diff, **kwargs):
    model = from_diff(diff, **kwargs)
    assert len(model["files"]) == 1, model["files"]
    return model["files"][0]["classification"]


def edit(path, added=("new line",), removed=("old line",), header="@@ -1,2 +1,2 @@"):
    """The smallest diff that touches one file."""
    body = "".join("-%s\n" % l for l in removed) + "".join("+%s\n" % l for l in added)
    return ("diff --git a/%s b/%s\n--- a/%s\n+++ b/%s\n%s\n%s"
            % (path, path, path, path, header, body))


@pytest.fixture(scope="module")
def models():
    return {name: classified(name) for name in ("small", "medium", "monster")}


# ------------------------------------------------------------ the fixtures

def test_every_file_is_classified(models):
    for name, model in models.items():
        for f in model["files"]:
            c = f["classification"]
            assert c["role"] in classify.ROLES, f"{name}: {f['path']} -> {c['role']}"
            assert c["significance_hint"] in {"core", "supporting", "mechanical"}


def test_nothing_is_dismissed_without_a_reason(models):
    """The contract: a file called mechanical says why, in words a human reads."""
    for name, model in models.items():
        for f in model["files"]:
            c = f["classification"]
            if c["significance_hint"] == "mechanical":
                assert c["reasons"], f"{name}: {f['path']} was dismissed silently"


def test_the_monster_is_mostly_noise_and_says_which(models):
    files = {f["path"]: f["classification"] for f in models["monster"]["files"]}

    assert files["poetry.lock"]["lockfile"] is True
    assert files["poetry.lock"]["significance_hint"] == "mechanical"
    assert files["clients/ts/pnpm-lock.yaml"]["lockfile"] is True

    for path in ("clients/ts/src/api/generated/orders.ts",
                 "clients/ts/src/api/generated/payments.ts",
                 "gen/pb/shipping_pb2.py"):
        assert files[path]["generated"] is True, path
        assert files[path]["significance_hint"] == "mechanical", path

    vendored = files["third_party/httpstub/__init__.py"]
    assert vendored["vendored"] is True
    assert vendored["significance_hint"] == "mechanical"

    # The hand-written client that the generated ones sit next to is not noise.
    assert files["src/meridian/http/client.py"]["significance_hint"] == "core"
    assert files["src/meridian/http/client.py"]["generated"] is False


def test_tests_are_supporting_not_core_and_not_noise(models):
    for name, model in models.items():
        for f in model["files"]:
            c = f["classification"]
            if c["test"] and not (c["generated"] or f["status"] == "renamed"):
                assert c["role"] == "tests", f"{name}: {f['path']}"
                assert c["significance_hint"] == "supporting", f"{name}: {f['path']}"


def test_changed_lines_by_role_covers_every_changed_line(models):
    for name, model in models.items():
        counted = sum(model["stats"]["changed_lines_by_role"].values())
        total = model["stats"]["additions"] + model["stats"]["deletions"]
        assert counted == total, name


# ------------------------------------------------------------ what is noise

@pytest.mark.parametrize("path", [
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "Cargo.lock", "Gemfile.lock", "go.sum", "composer.lock", "uv.lock",
    "src/frontend/package-lock.json",
])
def test_lockfiles_are_recognised_wherever_they_sit(path):
    c = only_file(edit(path))
    assert c["lockfile"] is True, path
    assert c["significance_hint"] == "mechanical", path


@pytest.mark.parametrize("path", [
    "clients/ts/src/api/generated/orders.ts", "gen/pb/shipping_pb2.py",
    "internal/pb/user.pb.go", "lib/model.g.dart", "web/static/app.min.js",
    "src/__generated__/schema.ts", "dist/bundle.js",
])
def test_generated_paths_are_recognised(path):
    c = only_file(edit(path))
    assert c["generated"] is True, path
    assert c["role"] == "generated", path


def test_a_generated_file_that_only_says_so_in_its_header_is_caught():
    """The path looks ordinary; the banner does not."""
    diff = edit("src/api/client.ts",
                removed=("// Code generated by orval. DO NOT EDIT.", "const a = 1;"),
                added=("// Code generated by orval. DO NOT EDIT.", "const a = 2;"),
                header="@@ -1,2 +1,2 @@")
    c = only_file(diff)
    assert c["generated"] is True
    assert any("header says" in r for r in c["reasons"])


def test_a_file_that_merely_mentions_generation_is_not_generated():
    """The marker has to be in the file's own first lines, not anywhere in it."""
    filler = ["line %d" % i for i in range(20)]
    diff = edit("src/docs_writer.py",
                removed=filler + ["print('DO NOT EDIT')"],
                added=filler + ["print('DO NOT EDIT!')"],
                header="@@ -1,21 +1,21 @@")
    c = only_file(diff)
    assert c["generated"] is False


def test_a_vendored_tree_is_noise_even_when_it_is_source():
    c = only_file(edit("vendor/github.com/pkg/errors/errors.go"))
    assert c["vendored"] is True
    assert c["significance_hint"] == "mechanical"


def test_a_reindent_is_formatting_only():
    c = only_file(edit("src/app.py",
                       removed=("def f():", "  return 1"),
                       added=("def f():", "    return 1"),
                       header="@@ -1,2 +1,2 @@"))
    assert c["whitespace_only"] is True
    assert c["formatting_only"] is True
    assert c["significance_hint"] == "mechanical"


def test_a_rewrap_is_formatting_only_but_not_whitespace_only():
    """A formatter that splits a call across lines changes the line count."""
    c = only_file(edit("src/app.py",
                       removed=("foo(a, b, c)",),
                       added=("foo(a,", "    b,", "    c)"),
                       header="@@ -1,1 +1,3 @@"))
    assert c["whitespace_only"] is False
    assert c["formatting_only"] is True
    assert c["significance_hint"] == "mechanical"


def test_a_trailing_comma_is_not_treated_as_formatting():
    """A magic trailing comma is semantically nothing, but proving that needs a
    parser per language. The rule stays conservative: unequal text is a change,
    and a change that turns out to be noise costs a reader far less than noise
    that was quietly filed as nothing."""
    c = only_file(edit("src/app.py",
                       removed=("foo(a, b, c)",),
                       added=("foo(", "    a,", "    b,", "    c,", ")"),
                       header="@@ -1,1 +1,5 @@"))
    assert c["formatting_only"] is False
    assert c["significance_hint"] == "core"


def test_a_line_ending_change_is_named_as_one():
    c = only_file(edit("config/app.ini",
                       removed=("key=value\r", "other=1\r"),
                       added=("key=value", "other=1"),
                       header="@@ -1,2 +1,2 @@"))
    assert c["whitespace_only"] is True
    assert any("line endings" in r for r in c["reasons"])


def test_a_real_edit_hiding_among_reformatted_lines_is_not_formatting():
    c = only_file(edit("src/app.py",
                       removed=("def f():", "  return 1"),
                       added=("def f():", "    return 2"),
                       header="@@ -1,2 +1,2 @@"))
    assert c["formatting_only"] is False
    assert c["significance_hint"] == "core"


def test_an_addition_with_nothing_removed_is_not_formatting():
    """`formatting_only` compares two sides. A pure addition has only one."""
    c = only_file("diff --git a/a.py b/a.py\n--- /dev/null\n+++ b/a.py\n"
                  "@@ -0,0 +1,2 @@\n+def f():\n+    return 1\n")
    assert c["formatting_only"] is False
    assert c["whitespace_only"] is False


def test_a_mode_change_alone_is_noise_but_an_edited_script_is_not():
    mode_only = only_file("diff --git a/run.sh b/run.sh\n"
                          "old mode 100644\nnew mode 100755\n")
    assert mode_only["significance_hint"] == "mechanical"
    edited = only_file("diff --git a/run.sh b/run.sh\n"
                       "old mode 100644\nnew mode 100755\n"
                       "--- a/run.sh\n+++ b/run.sh\n"
                       "@@ -1,2 +1,2 @@\n #!/bin/sh\n-echo old\n+echo new\n")
    assert edited["significance_hint"] == "supporting"


def test_a_pure_rename_is_noise_and_a_rename_with_edits_is_not():
    pure = only_file("diff --git a/src/a.py b/src/b.py\n"
                     "similarity index 100%\nrename from src/a.py\nrename to src/b.py\n")
    assert pure["significance_hint"] == "mechanical"
    assert any("no edits" in r for r in pure["reasons"])

    with_edits = only_file(
        "diff --git a/src/a.py b/src/b.py\n"
        "similarity index 70%\nrename from src/a.py\nrename to src/b.py\n"
        "--- a/src/a.py\n+++ b/src/b.py\n"
        "@@ -1,2 +1,2 @@\n def f():\n-    return 1\n+    return 2\n")
    assert with_edits["significance_hint"] == "core"
    assert any("with edits" in r for r in with_edits["reasons"])


# ------------------------------------------------------------ roles

@pytest.mark.parametrize("path,role", [
    ("src/meridian/api/refunds.py", "api"),
    ("src/routes/orders.ts", "api"),
    ("proto/billing.proto", "api"),
    ("migrations/0044_partial_refunds.sql", "persistence"),
    ("src/orders/repository.py", "persistence"),
    ("tests/webhooks/test_handler.py", "tests"),
    ("src/components/Button.tsx", "ui"),
    ("docs/architecture/http.md", "docs"),
    ("README.md", "docs"),
    (".github/workflows/ci.yml", "build"),
    ("Dockerfile", "build"),
    ("pyproject.toml", "build"),
    ("terraform/vpc.tf", "infra"),
    ("k8s/deployment.yaml", "infra"),
    ("config/limits.yaml", "config"),
    ("src/meridian/refunds/policy.py", "domain"),
    ("assets/logo.svg", "ui"),
    ("bin/release.sh", "build"),
    ("data/orders.csv", "other"),
])
def test_the_path_decides_the_role(path, role):
    assert only_file(edit(path))["role"] == role, path


def test_a_test_file_is_tests_before_it_is_anything_else():
    """`tests/api/test_refunds.py` is a test, not an api file."""
    assert only_file(edit("tests/api/test_refunds.py"))["role"] == "tests"
    assert only_file(edit("src/api/__tests__/refunds.spec.ts"))["role"] == "tests"


# ------------------------------------------------------------ the budget

def test_a_small_diff_is_handed_over_whole(models):
    for name, model in models.items():
        assert model["budget"]["tier"] == "full", name
        assert model["budget"]["hunks_elided"] == 0, name
        assert all(not h["elided"] for h in model["hunks"].values()), name


def test_the_budget_spends_mechanical_hunks_first():
    model = classified("monster", max_bytes=40_000)
    hint = {h: f["classification"]["significance_hint"]
            for f in model["files"] for h in f["hunk_ids"]}
    elided = [h["id"] for h in model["hunks"].values() if h["elided"]]
    assert elided, "nothing was elided at a budget below the diff size"
    assert all(hint[h] == "mechanical" for h in elided)
    assert model["budget"]["tier"] == "core"
    assert model["budget"]["bytes_included"] <= 40_000


def test_the_tier_drops_to_summary_once_real_code_has_to_go():
    model = classified("monster", max_bytes=12_000)
    assert model["budget"]["tier"] == "summary"
    assert model["budget"]["bytes_included"] <= 12_000


def test_an_elided_hunk_keeps_everything_except_its_lines():
    model = classified("monster", max_bytes=40_000)
    elided = [h for h in model["hunks"].values() if h["elided"]]
    for hunk in elided:
        assert hunk["lines"] == []
        assert hunk["header"] and hunk["path"]
        assert hunk["new_lines"] or hunk["old_lines"], "the counts survive"


def test_the_file_totals_never_shrink_with_the_budget():
    """Eliding changes what can be quoted, never what the diff did."""
    whole = classified("monster")
    tight = classified("monster", max_bytes=3_000)
    assert whole["stats"] == tight["stats"]
    for a, b in zip(whole["files"], tight["files"]):
        assert (a["additions"], a["deletions"]) == (b["additions"], b["deletions"])


def test_eliding_is_said_out_loud():
    model = classified("monster", max_bytes=40_000)
    assert any("summarised rather than quoted" in w for w in model["warnings"])


# ------------------------------------------------------------ the command line

def run_cli(*args, stdin=None):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "classify.py"), *args],
        capture_output=True, text=True, input=stdin,
    )


def test_the_scripts_pipe_into_each_other():
    parse = subprocess.run(
        [sys.executable, str(SCRIPTS / "parse_diff.py"),
         str(FIXTURES / "monster.diff"), "--compact"],
        capture_output=True, text=True)
    assert parse.returncode == 0, parse.stderr
    done = run_cli("-", "--compact", stdin=parse.stdout)
    assert done.returncode == 0, done.stderr
    model = json.loads(done.stdout)
    assert all("classification" in f for f in model["files"])


def test_the_cli_refuses_anything_that_is_not_a_pre_model():
    assert run_cli("-", stdin='{"hello": "world"}').returncode == 1
    assert run_cli("-", stdin="not json").returncode == 1
