"""Documentation that has drifted from the code is worse than none.

SKILL.md is what the model running this skill actually reads, so a stale path or
a command that no longer works is a runtime failure, not a typo. These tests
hold the docs to the filesystem and to the CLI.
"""
import re
import subprocess
import sys

import pytest
from conftest import FIXTURES, REFERENCES, ROOT, SKILL

SKILL_MD = SKILL / "SKILL.md"
DOCS = [SKILL_MD] + sorted(REFERENCES.glob("*.md"))


@pytest.fixture(scope="module")
def skill_text():
    return SKILL_MD.read_text(encoding="utf-8")


def test_the_skill_has_frontmatter_a_loader_can_read(skill_text):
    assert skill_text.startswith("---\n")
    end = skill_text.index("\n---\n", 3)
    front = skill_text[4:end]
    fields = dict(re.findall(r"^([a-z_]+):\s*(.+)$", front, re.M))
    assert fields.get("name") == "precis"
    assert len(fields.get("description", "")) > 80, "the description is the routing signal"
    assert "\n" not in fields["description"]


def test_the_skill_states_the_rule_that_defines_it(skill_text):
    """If this sentence ever goes missing, the skill has become a review tool."""
    assert "precis is not a code review tool" in skill_text
    assert "Never produce a verdict" in skill_text


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_every_path_the_docs_name_exists(doc):
    text = doc.read_text(encoding="utf-8")
    # Only paths to things this repo ships. A backticked `scripts/regen.sh` in
    # an example sentence is describing someone else's repository.
    ours = r"[\w./-]+\.(?:py|md|html|json|diff)"
    referenced = set(re.findall(r"`((?:scripts|references|assets)/%s)`" % ours, text))
    referenced |= set(re.findall(r"(skills/precis/%s)" % ours, text))
    missing = []
    for ref in sorted(referenced):
        target = ROOT / ref if ref.startswith("skills/") else SKILL / ref
        if not target.exists():
            missing.append(ref)
    assert missing == [], f"{doc.name} points at nothing: {missing}"


def test_the_documented_pipeline_runs(tmp_path):
    """The exact two-command pipeline SKILL.md tells the model to run."""
    parse = subprocess.run(
        [sys.executable, "skills/precis/scripts/parse_diff.py",
         str(FIXTURES / "medium.diff")],
        capture_output=True, text=True, cwd=ROOT)
    assert parse.returncode == 0, parse.stderr
    out = tmp_path / "pre.json"
    done = subprocess.run(
        [sys.executable, "skills/precis/scripts/classify.py", "-", "-o", str(out)],
        input=parse.stdout, capture_output=True, text=True, cwd=ROOT)
    assert done.returncode == 0, done.stderr
    assert out.exists() and out.stat().st_size > 1000


def test_the_docs_do_not_teach_the_model_to_review():
    """The instructions are prose too, and the same drift applies to them.

    Discussing the ban is allowed - the words appear in the rules themselves -
    but an instruction to produce a finding is not.
    """
    banned = re.compile(r"\b(you should (?:recommend|flag|suggest)|"
                        r"report (?:bugs|issues|problems)|"
                        r"identify (?:bugs|issues|risks)|"
                        r"assess the quality)\b", re.I)
    for doc in DOCS:
        hit = banned.search(doc.read_text(encoding="utf-8"))
        assert hit is None, f"{doc.name}: {hit.group(0)!r}"


def test_the_reference_set_is_complete(skill_text):
    """Each reference the skill promises exists, and each one that exists is
    reachable from the skill."""
    named = set(re.findall(r"references/(\w+\.md)", skill_text))
    on_disk = {p.name for p in REFERENCES.glob("*.md")}
    assert named == on_disk, f"named {sorted(named)}, on disk {sorted(on_disk)}"


def test_only_git_gh_and_glab_reach_the_network():
    """The privacy promise, checked against every command the docs suggest."""
    allowed = {"gh", "glab", "git", "python3", "grep", "head"}
    for doc in DOCS:
        for block in re.findall(r"```bash\n(.*?)```", doc.read_text(encoding="utf-8"), re.S):
            block = re.sub(r"\\\n\s*", " ", block)      # shell line continuations
            for line in block.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                for command in re.split(r"\|\||&&|\|", line):
                    first = command.strip().split()
                    if first and first[0] in allowed:
                        continue
                    assert not first or first[0].startswith("$") or first[0] in allowed, (
                        f"{doc.name}: {first[0]!r} is not one of {sorted(allowed)}"
                    )


def test_the_scripts_parse_at_the_python_version_the_readme_promises():
    """A skill that runs in someone else's sandbox cannot pick the interpreter.

    This is a syntax check, not a runtime one: `ast` will not catch a stdlib API
    that arrived later. It does catch the common drift, which is new syntax.
    """
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    stated = re.search(r"Python (\d+)\.(\d+) or newer", readme)
    assert stated, "README no longer states a minimum Python version"
    floor = (int(stated.group(1)), int(stated.group(2)))

    import ast
    for script in sorted((SKILL / "scripts").glob("*.py")):
        source = script.read_text(encoding="utf-8")
        try:
            ast.parse(source, filename=str(script), feature_version=floor)
        except SyntaxError as exc:
            raise AssertionError(
                "%s does not parse on Python %d.%d: %s (line %s)"
                % (script.name, floor[0], floor[1], exc.msg, exc.lineno)) from None


def test_the_readme_shows_screenshots_that_exist():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    missing = [src for src in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", readme)
               if not (ROOT / src).exists()]
    assert missing == [], f"README points at missing images: {missing}"


def test_every_shipped_example_is_a_valid_report_model():
    """An example that no longer validates is an example that lies."""
    import json

    from validate_model import validate
    models = sorted((ROOT / "examples").glob("*.json"))
    assert models, "examples/ has no report models"
    for path in models:
        problems = validate(json.loads(path.read_text(encoding="utf-8")), path.name)
        assert problems == [], "\n".join(problems)


def test_every_shipped_example_has_its_rendered_page():
    for model in sorted((ROOT / "examples").glob("*.json")):
        assert model.with_suffix(".html").exists(), (
            f"{model.name} has no rendered .html beside it; an example is a pair")
