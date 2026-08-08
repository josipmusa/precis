"""What the parser is allowed to get wrong: nothing.

Every later phase trusts these numbers. A miscounted rename or a dropped hunk
produces a report that is confidently incorrect, which is the one failure mode
precis cannot tolerate, so the awkward shapes of real diffs are pinned here
individually rather than exercised only through the fixtures.
"""
import json
import subprocess
import sys

import pytest

from conftest import FIXTURE_NAMES, FIXTURES, SCRIPTS

import parse_diff
from parse_diff import parse_diff as parse


def parsed(name):
    # Through the script's own reader: `Path.read_text` would translate CRLF to
    # LF and quietly hide the one fixture that tests line endings.
    return parse(parse_diff.read_diff(str(FIXTURES / f"{name}.diff")))


@pytest.fixture(scope="module")
def pre_models():
    return {name: parsed(name) for name in FIXTURE_NAMES}


# ----------------------------------------------------- the fixture diffs

def test_every_fixture_diff_parses_without_complaint(pre_models):
    for name, model in pre_models.items():
        assert model["warnings"] == [], f"{name}: {model['warnings']}"
        assert model["files"], f"{name}: no files"


def test_the_parser_agrees_with_the_hand_written_models(pre_models):
    """The fixtures were written by hand against these diffs.

    Same input, two independent authors: if the counts disagree, one of them is
    lying about the change and there is no way to tell which from inside a
    report. This is the check that keeps them honest.
    """
    for name, pre in pre_models.items():
        report = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
        for key in ("files_changed", "additions", "deletions", "hunks"):
            assert pre["stats"][key] == report["stats"][key], (
                f"{name}.{key}: parser {pre['stats'][key]}, "
                f"fixture {report['stats'][key]}"
            )


def test_every_hunk_the_fixtures_quote_is_the_hunk_in_the_diff(pre_models):
    """Line for line, including the truncated ones as exact prefixes."""
    checked = 0
    for name, pre in pre_models.items():
        report = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
        by_position = {(h["path"], h["old_start"], h["new_start"]): h
                       for h in pre["hunks"].values()}
        for hunk in report["hunks"].values():
            key = (hunk["path"], hunk["old_start"], hunk["new_start"])
            assert key in by_position, f"{name}.{hunk['id']}: no such hunk in the diff"
            mine = by_position[key]
            assert hunk["header"] == mine["header"], f"{name}.{hunk['id']}"
            assert hunk.get("section") == mine["section"], f"{name}.{hunk['id']}"
            theirs = [(l["t"], l["c"]) for l in hunk["lines"]]
            ours = [(l["t"], l["c"]) for l in mine["lines"]]
            if hunk["truncated"]:
                assert theirs == ours[:len(theirs)], f"{name}.{hunk['id']}: not a prefix"
            else:
                assert theirs == ours, f"{name}.{hunk['id']}: content differs"
            checked += 1
    assert checked == 82, f"expected to check 82 hunks, checked {checked}"


def test_the_monster_carries_every_shape_a_parser_can_trip_over(pre_models):
    files = {f["path"]: f for f in pre_models["monster"]["files"]}

    renamed = files["src/meridian/http/backoff.py"]
    assert renamed["status"] == "renamed"
    assert renamed["old_path"] == "src/meridian/util/backoff.py"
    assert renamed["similarity"] == 55
    assert renamed["hunk_ids"], "a rename with edits still has hunks"

    binary = files["docs/assets/http-topology.png"]
    assert binary["is_binary"] is True
    assert binary["hunk_ids"] == []
    assert binary["additions"] == binary["deletions"] == 0

    mode = files["scripts/regen_clients.sh"]
    assert mode["status"] == "mode_changed"
    assert mode["mode_change"] == {"from": "100644", "to": "100755"}

    deleted = files["src/meridian/notifications/_http.py"]
    assert deleted["status"] == "deleted"


def test_line_endings_survive_the_round_trip(pre_models):
    """A CRLF file must not quietly become an LF file in the report."""
    hunks = [h for h in pre_models["monster"]["hunks"].values()
             if h["path"] == "config/windows-agent.ini"]
    assert hunks, "the CRLF fixture file went missing"
    assert any(line["c"].endswith("\r") for h in hunks for line in h["lines"])


def test_hunk_ids_are_stable_and_dense(pre_models):
    for name, model in pre_models.items():
        ids = list(model["hunks"])
        assert ids == [f"h{i}" for i in range(1, len(ids) + 1)], name
        for hid, hunk in model["hunks"].items():
            assert hunk["id"] == hid, name
        owned = [h for f in model["files"] for h in f["hunk_ids"]]
        assert sorted(owned) == sorted(ids), f"{name}: a hunk belongs to no file"


def test_the_counts_add_up(pre_models):
    for name, model in pre_models.items():
        additions = sum(1 for h in model["hunks"].values()
                        for l in h["lines"] if l["t"] == "+")
        deletions = sum(1 for h in model["hunks"].values()
                        for l in h["lines"] if l["t"] == "-")
        # Truncated hunks hold fewer lines than they counted, so the file totals
        # are the authority and the visible lines can only be a subset.
        assert additions <= model["stats"]["additions"], name
        assert deletions <= model["stats"]["deletions"], name
        assert model["stats"]["additions"] == sum(f["additions"] for f in model["files"])
        assert model["stats"]["deletions"] == sum(f["deletions"] for f in model["files"])


def test_line_numbers_track_both_sides(pre_models):
    for name, model in pre_models.items():
        for hunk in model["hunks"].values():
            old = hunk["old_start"]
            new = hunk["new_start"]
            for line in hunk["lines"]:
                if line["t"] in (" ", "-"):
                    assert line["old"] == old, f"{name}.{hunk['id']}"
                    old += 1
                else:
                    assert line["old"] is None, f"{name}.{hunk['id']}"
                if line["t"] in (" ", "+"):
                    assert line["new"] == new, f"{name}.{hunk['id']}"
                    new += 1
                else:
                    assert line["new"] is None, f"{name}.{hunk['id']}"


# ----------------------------------------------------- the awkward shapes

def one_file(diff):
    model = parse(diff)
    assert len(model["files"]) == 1, model["files"]
    return model, model["files"][0]


def test_a_pure_rename_has_no_hunks():
    model, f = one_file(
        "diff --git a/old/name.py b/new/name.py\n"
        "similarity index 100%\n"
        "rename from old/name.py\n"
        "rename to new/name.py\n"
    )
    assert f["status"] == "renamed"
    assert f["path"] == "new/name.py"
    assert f["old_path"] == "old/name.py"
    assert f["similarity"] == 100
    assert f["hunk_ids"] == []
    assert model["stats"]["additions"] == 0


def test_a_copy_is_not_a_rename():
    _, f = one_file(
        "diff --git a/src/a.py b/src/b.py\n"
        "similarity index 92%\n"
        "copy from src/a.py\n"
        "copy to src/b.py\n"
    )
    assert f["status"] == "copied"
    assert f["old_path"] == "src/a.py"


def test_a_mode_only_change_is_not_a_modification():
    _, f = one_file(
        "diff --git a/run.sh b/run.sh\n"
        "old mode 100644\n"
        "new mode 100755\n"
    )
    assert f["status"] == "mode_changed"
    assert f["mode_change"] == {"from": "100644", "to": "100755"}


def test_a_mode_change_alongside_edits_stays_a_modification():
    _, f = one_file(
        "diff --git a/run.sh b/run.sh\n"
        "old mode 100644\n"
        "new mode 100755\n"
        "index 1111111..2222222\n"
        "--- a/run.sh\n"
        "+++ b/run.sh\n"
        "@@ -1,2 +1,2 @@\n"
        " #!/bin/sh\n"
        "-echo old\n"
        "+echo new\n"
    )
    assert f["status"] == "modified"
    assert f["mode_change"] == {"from": "100644", "to": "100755"}


def test_a_git_binary_patch_body_is_never_read_as_diff_lines():
    """The base85 payload contains lines starting with `+`. They are not hunks."""
    model, f = one_file(
        "diff --git a/logo.png b/logo.png\n"
        "index 1111111..2222222 100644\n"
        "GIT binary patch\n"
        "delta 24\n"
        "zcmZ3^ki+8+mL8Vg$;d1Ku+Tj\n"
        "+not a diff line\n"
    )
    assert f["is_binary"] is True
    assert model["hunks"] == {}


def test_a_deleted_file_keeps_its_path():
    _, f = one_file(
        "diff --git a/gone.py b/gone.py\n"
        "deleted file mode 100644\n"
        "index 1111111..0000000\n"
        "--- a/gone.py\n"
        "+++ /dev/null\n"
        "@@ -1,2 +0,0 @@\n"
        "-one\n"
        "-two\n"
    )
    assert f["status"] == "deleted"
    assert f["path"] == "gone.py"
    assert f["deletions"] == 2


def test_a_path_with_spaces_survives_the_header():
    _, f = one_file(
        "diff --git a/docs/release notes.md b/docs/release notes.md\n"
        "old mode 100644\n"
        "new mode 100755\n"
    )
    assert f["path"] == "docs/release notes.md"


def test_a_quoted_non_ascii_path_is_decoded():
    """git quotes anything above ASCII by default, in octal, byte by byte."""
    _, f = one_file(
        'diff --git "a/docs/r\\303\\251sum\\303\\251.md" "b/docs/r\\303\\251sum\\303\\251.md"\n'
        "old mode 100644\n"
        "new mode 100755\n"
    )
    assert f["path"] == "docs/résumé.md"


def test_a_no_prefix_diff_keeps_its_paths():
    _, f = one_file(
        "diff --git src/app.py src/app.py\n"
        "index 1111111..2222222 100644\n"
        "--- src/app.py\n"
        "+++ src/app.py\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )
    assert f["path"] == "src/app.py"
    assert f["old_path"] is None


def test_a_bare_patch_without_a_git_header_still_parses():
    """`diff -u`, mail attachments, and anything that went through `patch`."""
    model = parse(
        "--- a/src/app.py\t2026-01-01 10:00:00\n"
        "+++ b/src/app.py\t2026-01-02 10:00:00\n"
        "@@ -1,2 +1,2 @@\n"
        " keep\n"
        "-old\n"
        "+new\n"
        "--- a/src/other.py\n"
        "+++ b/src/other.py\n"
        "@@ -1 +1 @@\n"
        "-a\n"
        "+b\n"
    )
    assert [f["path"] for f in model["files"]] == ["src/app.py", "src/other.py"]
    assert model["stats"]["hunks"] == 2


def test_a_single_line_hunk_header_means_one_line():
    model = parse(
        "diff --git a/a.txt b/a.txt\n"
        "--- a/a.txt\n"
        "+++ b/a.txt\n"
        "@@ -7 +7 @@\n"
        "-old\n"
        "+new\n"
    )
    hunk = model["hunks"]["h1"]
    assert (hunk["old_start"], hunk["old_lines"]) == (7, 1)
    assert (hunk["new_start"], hunk["new_lines"]) == (7, 1)
    assert hunk["header"] == "@@ -7,1 +7,1 @@"


def test_an_empty_context_line_is_context():
    """Some tools strip the trailing space, leaving a bare empty line."""
    model = parse(
        "diff --git a/a.txt b/a.txt\n"
        "--- a/a.txt\n"
        "+++ b/a.txt\n"
        "@@ -1,3 +1,3 @@\n"
        " one\n"
        "\n"
        "-three\n"
        "+four\n"
    )
    lines = model["hunks"]["h1"]["lines"]
    assert [l["t"] for l in lines] == [" ", " ", "-", "+"]
    assert lines[1]["c"] == ""
    assert lines[1]["old"] == 2 and lines[1]["new"] == 2


def test_the_no_newline_marker_is_recorded_not_treated_as_content():
    model = parse(
        "diff --git a/a.txt b/a.txt\n"
        "--- a/a.txt\n"
        "+++ b/a.txt\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "\\ No newline at end of file\n"
        "+new\n"
        "\\ No newline at end of file\n"
    )
    hunk = model["hunks"]["h1"]
    assert hunk["no_newline"] is True
    assert [l["c"] for l in hunk["lines"]] == ["old", "new"]


def test_the_section_context_is_split_out_of_the_header():
    model = parse(
        "diff --git a/a.py b/a.py\n"
        "--- a/a.py\n"
        "+++ b/a.py\n"
        "@@ -10,3 +10,4 @@ class Ledger:\n"
        " a\n"
        " b\n"
        "-c\n"
        "+d\n"
        "+e\n"
    )
    hunk = model["hunks"]["h1"]
    assert hunk["header"] == "@@ -10,3 +10,4 @@"
    assert hunk["section"] == "class Ledger:"


def test_a_merge_diff_is_refused_rather_than_guessed_at():
    model = parse(
        "diff --cc src/app.py\n"
        "index 1111111,2222222..3333333\n"
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "@@@ -1,2 -1,2 +1,3 @@@\n"
        "++both\n"
        "diff --git a/ok.py b/ok.py\n"
        "--- a/ok.py\n"
        "+++ b/ok.py\n"
        "@@ -1 +1 @@\n"
        "-a\n"
        "+b\n"
    )
    assert any("combined" in w for w in model["warnings"])
    assert "ok.py" in [f["path"] for f in model["files"]], "the rest still parses"


def test_an_over_long_hunk_is_shortened_and_says_so():
    body = "".join("+line %d\n" % i for i in range(300))
    model = parse(
        "diff --git a/big.txt b/big.txt\n"
        "--- /dev/null\n"
        "+++ b/big.txt\n"
        "@@ -0,0 +1,300 @@\n" + body,
        max_hunk_lines=50,
    )
    hunk = model["hunks"]["h1"]
    assert hunk["truncated"] is True
    assert len(hunk["lines"]) == 50
    # The count is of the real hunk, not of what survived the cap.
    assert model["stats"]["additions"] == 300
    assert any("shortened" in w for w in model["warnings"])


def test_a_hunk_that_ends_early_is_reported_not_silently_accepted():
    model = parse(
        "diff --git a/a.txt b/a.txt\n"
        "--- a/a.txt\n"
        "+++ b/a.txt\n"
        "@@ -1,9 +1,9 @@\n"
        " one\n"
    )
    assert any("ended early" in w for w in model["warnings"])


def test_the_fingerprint_ignores_context_and_line_numbers():
    """The same edit further down a file is the same edit."""
    first = parse(
        "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n"
        "@@ -1,3 +1,3 @@\n a\n-old\n+new\n"
    )
    moved = parse(
        "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n"
        "@@ -80,3 +80,3 @@\n zzz\n-old\n+new\n"
    )
    assert first["hunks"]["h1"]["fingerprint"] == moved["hunks"]["h1"]["fingerprint"]

    other = parse(
        "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n"
        "@@ -1,3 +1,3 @@\n a\n-old\n+different\n"
    )
    assert first["hunks"]["h1"]["fingerprint"] != other["hunks"]["h1"]["fingerprint"]


def test_language_comes_from_the_path_and_nothing_else():
    assert parse_diff.language_of("src/app.py") == "python"
    assert parse_diff.language_of("clients/ts/src/api.ts") == "typescript"
    assert parse_diff.language_of("deploy/Dockerfile") == "dockerfile"
    assert parse_diff.language_of("deploy/Dockerfile.ci") == "dockerfile"
    assert parse_diff.language_of("Makefile") == "makefile"
    assert parse_diff.language_of("LICENSE") is None
    assert parse_diff.language_of(None) is None


# ----------------------------------------------------- the command line

def run_cli(*args, stdin=None):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "parse_diff.py"), *args],
        capture_output=True, text=True, input=stdin,
    )


def test_the_cli_reads_a_file_and_writes_json():
    done = run_cli(str(FIXTURES / "small.diff"), "--compact")
    assert done.returncode == 0, done.stderr
    model = json.loads(done.stdout)
    assert model["schema_version"] == "1.0"
    assert model["stats"]["files_changed"] == 3


def test_the_cli_reads_stdin():
    text = (FIXTURES / "small.diff").read_text(encoding="utf-8")
    done = run_cli("-", "--compact", stdin=text)
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["stats"]["hunks"] == 6


def test_the_cli_refuses_input_that_is_not_a_diff():
    done = run_cli("-", stdin="just some prose\nwith no headers at all\n")
    assert done.returncode == 1
    assert "is stdin a diff" in done.stderr
