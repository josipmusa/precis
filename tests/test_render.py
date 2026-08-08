"""The renderer is a pipe, and the template is the only thing that draws.

These tests hold three lines: the model reaches the page intact and inert, the
page reaches for nothing outside itself, and the template's vocabulary stays in
step with the schema's enumerations.
"""
import json
import re
import subprocess
import sys

import pytest
from conftest import FIXTURES, SCRIPTS, SKILL

import render_report
import validate_model

TEMPLATE = SKILL / "assets" / "template.html"


@pytest.fixture(scope="session")
def template_text():
    return TEMPLATE.read_text(encoding="utf-8")


def rendered(model, template_text):
    return render_report.render(model, template_text)


def embedded_json(html):
    match = re.search(
        r'<script id="precis-model" type="application/json">(.*?)</script>', html, re.S
    )
    assert match, "rendered page has no model blob"
    return match.group(1)


# ------------------------------------------------------------------ the pipe

def test_the_model_survives_the_round_trip(fixture_model, template_text):
    name, model = fixture_model
    assert json.loads(embedded_json(rendered(model, template_text))) == model


def test_no_raw_angle_bracket_reaches_the_blob(fixture_model, template_text):
    """A `</script>` inside a string would end the element and start markup."""
    name, model = fixture_model
    assert "<" not in embedded_json(rendered(model, template_text))


def test_a_hostile_string_cannot_break_out(template_text):
    model = json.loads((FIXTURES / "small.json").read_text(encoding="utf-8"))
    model["source"]["title"] = '</script><img src=x onerror=alert(1)>'
    model["story"]["headline"] = 'Closing </script> in prose stays prose.'
    html = rendered(model, template_text)
    assert "<img src=x" not in html
    assert "</script><img" not in html
    assert json.loads(embedded_json(html))["source"]["title"] == model["source"]["title"]
    # The title also lands in <title>, which is escaped separately.
    assert "<title>&lt;/script&gt;" in html


def test_line_separators_are_escaped(template_text):
    model = json.loads((FIXTURES / "small.json").read_text(encoding="utf-8"))
    model["story"]["headline"] = "line separator here"
    blob = embedded_json(rendered(model, template_text))
    assert " " not in blob and " " not in blob
    assert json.loads(blob)["story"]["headline"] == model["story"]["headline"]


def test_placeholders_are_both_consumed(fixture_model, template_text):
    name, model = fixture_model
    html = rendered(model, template_text)
    assert render_report.MODEL_TOKEN not in html
    assert render_report.TITLE_TOKEN not in html


def test_a_template_without_the_token_is_refused():
    with pytest.raises(ValueError):
        render_report.render({"source": {}}, "<html>no placeholder</html>")


# ------------------------------------------------------------ self-contained

def test_the_page_reaches_for_nothing(template_text):
    """No CDN, no font host, no telemetry. A report must open on a plane."""
    forbidden = [
        r"https?://",
        r"src\s*=\s*[\"']//",
        r"<link\b",
        r"<img\b",
        r"@import",
        r"\bfetch\s*\(",
        r"XMLHttpRequest",
        r"WebSocket",
        r"navigator\.sendBeacon",
        r"new\s+Worker",
        r"@font-face",
    ]
    # The SVG namespace is an identifier, not a request.
    text = template_text.replace("http://www.w3.org/2000/svg", "svg-namespace")
    for pattern in forbidden:
        hit = re.search(pattern, text)
        assert hit is None, f"template contains {pattern!r}: {text[hit.start():hit.start() + 70]!r}"


def test_storage_access_is_guarded(template_text):
    """file:// denies localStorage in some browsers; the page must still open."""
    for match in re.finditer(r"localStorage", template_text):
        window = template_text[max(0, match.start() - 400):match.start() + 200]
        assert "try {" in window, "localStorage used outside a try block"


def test_the_rendered_page_is_one_file(fixture_model, template_text):
    name, model = fixture_model
    html = rendered(model, template_text)
    assert html.count("<script") == 2, "expected exactly the model blob and the renderer"
    assert html.lstrip().startswith("<!doctype html>")


# -------------------------------------------------------- vocabulary in step

def js_object_keys(template_text, name):
    match = re.search(name + r"\s*=\s*\{(.*?)\};", template_text, re.S)
    assert match, f"template has no {name} map"
    return set(re.findall(r"(\w+)\s*:", match.group(1)))


@pytest.mark.parametrize("map_name,allowed", [
    ("ROLE_LABEL", validate_model.ROLES),
    ("KIND_LABEL", validate_model.CHANGE_KINDS),
    ("ATTN_LABEL", validate_model.ATTENTION_KINDS),
    ("STATUS_LABEL", validate_model.FILE_STATUS),
    ("SOURCE_KIND_LABEL", validate_model.SOURCE_KINDS),
    ("DELTA_LABEL", validate_model.DELTA_KINDS),
    ("EVIDENCE_LABEL", validate_model.EVIDENCE),
])
def test_every_enumeration_value_has_a_label(template_text, map_name, allowed):
    """An unlabelled enum value renders as a raw identifier in front of a human."""
    assert js_object_keys(template_text, map_name) == set(allowed), map_name


def test_significance_labels_are_complete(template_text):
    assert js_object_keys(template_text, "SIG_LABEL") == set(validate_model.SIGNIFICANCE)


def test_kind_order_covers_every_change_kind(template_text):
    match = re.search(r"KIND_ORDER\s*=\s*\[(.*?)\];", template_text, re.S)
    assert match
    listed = set(re.findall(r'"(\w+)"', match.group(1)))
    assert listed == validate_model.CHANGE_KINDS


def test_every_change_kind_has_a_colour(template_text):
    for kind in validate_model.CHANGE_KINDS:
        assert f"--k-{kind}:" in template_text, f"no colour token for change_kind {kind}"


def test_every_significance_has_a_colour(template_text):
    for value in validate_model.SIGNIFICANCE:
        assert f"--sig-{value}:" in template_text


# Typography and geometry are theme-independent; everything else is a colour.
NON_PALETTE = {"--sans", "--serif", "--mono", "--radius"}


def test_every_colour_token_is_defined_for_both_themes(template_text):
    """A token defined only in the light block leaves a hole in dark mode."""
    def tokens(start):
        block = template_text[start:template_text.index("\n}", start)]
        return set(re.findall(r"(--[\w-]+):", block)) - NON_PALETTE

    light = tokens(template_text.index(":root {"))
    dark = tokens(template_text.index(':root[data-theme="dark"] {'))
    media = tokens(template_text.index(':root:not([data-theme="light"]) {'))
    assert light - dark == set(), "tokens missing from the explicit dark palette"
    assert light - media == set(), "tokens missing from the prefers-color-scheme palette"
    assert dark == media, "the two dark palettes have drifted apart"


# ------------------------------------------------------------------- the CLI

def run_cli(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "render_report.py"), *args],
        capture_output=True, text=True,
    )


@pytest.mark.parametrize("name", ["small", "medium", "monster"])
def test_cli_renders_each_fixture(name, tmp_path):
    out = tmp_path / f"{name}.html"
    result = run_cli(str(FIXTURES / f"{name}.json"), "-o", str(out))
    assert result.returncode == 0, result.stderr
    assert out.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_cli_refuses_an_invalid_model(tmp_path):
    """render_report.py fails loudly rather than producing a report that lies."""
    model = json.loads((FIXTURES / "small.json").read_text(encoding="utf-8"))
    model["reading_order"]["steps"][0]["hunk_ids"] = ["h404"]
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps(model), encoding="utf-8")
    out = tmp_path / "broken.html"

    result = run_cli(str(broken), "-o", str(out))
    assert result.returncode == 1
    assert "h404" in result.stderr
    assert not out.exists(), "a rejected model must not leave a half-written report"


def test_cli_reports_a_missing_file(tmp_path):
    result = run_cli(str(tmp_path / "absent.json"))
    assert result.returncode == 2
    assert "cannot read model" in result.stderr


def test_cli_defaults_the_output_beside_the_model(tmp_path):
    source = tmp_path / "report.json"
    source.write_text((FIXTURES / "small.json").read_text(encoding="utf-8"), encoding="utf-8")
    result = run_cli(str(source))
    assert result.returncode == 0
    assert (tmp_path / "report.html").exists()


def test_the_schema_minimal_example_renders(tmp_path, template_text):
    """The floor case: a degraded run still produces a whole page."""
    from test_fixtures import REFERENCES
    text = (REFERENCES / "schema.md").read_text(encoding="utf-8")
    marker = "# Part 3 - A minimal valid report model"
    block = re.search(r"```json\n(.*?)\n```", text[text.index(marker):], re.S)
    model = json.loads(block.group(1))
    html = rendered(model, template_text)
    assert json.loads(embedded_json(html)) == model


# --------------------------------------------------------------- house style

def test_no_em_dashes_anywhere_in_the_skill():
    offenders = []
    for path in sorted(SKILL.rglob("*")):
        if not path.is_file() or path.suffix not in {".html", ".py", ".md", ".json"}:
            continue
        if "—" in path.read_text(encoding="utf-8", errors="replace"):
            offenders.append(str(path.relative_to(SKILL)))
    assert offenders == []
