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
    # `localStorage.` is a call; a comment that merely names it is not.
    for match in re.finditer(r"localStorage\s*\.", template_text):
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
    ("KIND_LABEL", validate_model.CHANGE_KINDS),
    ("STATUS_LABEL", validate_model.FILE_STATUS),
    ("SOURCE_KIND_LABEL", validate_model.SOURCE_KINDS),
    ("DELTA_LABEL", validate_model.DELTA_KINDS),
    ("EVIDENCE_LABEL", validate_model.EVIDENCE),
    ("REL_LABEL", validate_model.REL_KINDS),
    ("EMPH_LABEL", validate_model.EMPHASIS),
])
def test_every_enumeration_value_has_a_label(template_text, map_name, allowed):
    """An unlabelled enum value renders as a raw identifier in front of a human."""
    assert js_object_keys(template_text, map_name) == set(allowed), map_name


def test_the_enumerations_the_page_stopped_showing_have_no_labels(template_text):
    """Roles, check kinds, significance and graph node kinds are taxonomy the
    reader had to decode. They live in the model; they do not render."""
    for gone in ("ROLE_LABEL", "ATTN_LABEL", "SIG_LABEL", "GRAPH_KIND_LABEL",
                 "CONTRACT_KIND_LABEL", "KIND_ORDER"):
        assert gone not in template_text, f"{gone} came back"


# Typography is theme-independent; everything else is a colour.
NON_PALETTE = {"--text", "--mono"}


def test_every_colour_token_is_defined_for_both_themes(template_text):
    """A token defined only in the light block leaves a hole in dark mode."""
    def tokens(start, end):
        block = template_text[start:template_text.index(end, start)]
        return set(re.findall(r"(--[\w-]+):", block)) - NON_PALETTE

    light = tokens(template_text.index(":root {"), "\n}")
    dark = tokens(template_text.index("@media (prefers-color-scheme: dark) {"), "\n  }")
    assert light - dark == set(), "tokens missing from the dark palette"
    assert dark - light == set(), "the dark palette defines a token the light one does not"


def test_dark_mode_is_the_system_preference_and_nothing_else(template_text):
    """One less control, one less thing to remember. The page follows the OS."""
    assert "data-theme" not in template_text
    assert "toggleTheme" not in template_text


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
    model["review_pass"]["steps"][0]["hunk_ids"] = ["h404"]
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
    marker = "- A minimal valid report model"
    block = re.search(r"```json\n(.*?)\n```", text[text.index(marker):], re.S)
    model = json.loads(block.group(1))
    html = rendered(model, template_text)
    assert json.loads(embedded_json(html)) == model


# ------------------------------------------------------ the shape of a page

def test_a_diagram_draws_two_shapes_and_no_more(template_text):
    """Shape taxonomy is the same disease as colour taxonomy: a cylinder, a pill
    and a folded note ask the reader to learn a key before the picture says
    anything. Rectangles, and a diamond where something is decided."""
    body = re.search(r"function nodeShape\(.*?\n\}", template_text, re.S).group(0)
    assert '"decision"' in body
    for kind in validate_model.GRAPH_NODE_KINDS | {"store", "queue", "actor", "note"}:
        if kind == "decision":
            continue
        assert f'"{kind}"' not in body, f"nodeShape still gives {kind} a shape of its own"
    assert body.count("s(\"rect\"") == 1, "more than one rectangle variant survived"


def test_a_diagram_carries_two_colours_at_most(template_text):
    """Ink for what was already there, the accent for what this change touched,
    a dashed outline for what it removed. No third hue to decode."""
    body = re.search(r"function emphColor\(.*?\n\}", template_text, re.S).group(0)
    used = set(re.findall(r"var\(--[\w-]+\)", body))
    assert used <= {"var(--accent)", "var(--ink-soft)"}, used


def test_a_diagram_label_wraps_rather_than_truncating(template_text):
    """A label clipped to unreadability is a diagram lying about its contents.
    The box is sized to the label, not the label to the box."""
    assert "function clip(" not in template_text, "the truncating helper came back"
    body = re.search(r"function drawFlow\(.*?\n\}", template_text, re.S).group(0)
    assert "longestWord" in body, "node width no longer accounts for its longest word"


def test_the_pass_persists_under_the_head_sha(template_text):
    """A new head must start a clean pass; a reload must resume the old one."""
    assert "precis-pass:" in template_text
    match = re.search(r"const PASS_KEY = .*?;", template_text, re.S)
    assert match and "head" in match.group(0) and "sha" in match.group(0)


def test_a_carriage_return_cannot_double_the_line_height(template_text):
    """CRLF content keeps its CR in the model. Under pre-wrap a lone CR is a
    line break, so the renderer has to drop it or every Windows file prints
    double-spaced."""
    assert re.search(r'endsWith\("\\r"\)', template_text), (
        "the renderer no longer strips the carriage return"
    )


def test_a_tick_is_a_checkbox_a_counter_and_the_fold(template_text):
    """The pass is a record of what was read; the one piece of choreography a
    tick is allowed is folding its own step away. No flash, no progress bar,
    no summary to copy."""
    body = re.search(r"function tickBox\(.*?\n\}", template_text, re.S).group(0)
    assert 'type: "checkbox"' in body
    assert "refreshCount" in body, "ticking no longer updates the counter"
    for ghost in ("foldButton", "passSummary", "copySummary", "resetPass",
                  "pbar", "flash"):
        assert ghost not in template_text, f"{ghost} survived the redesign"


def test_a_tick_folds_the_step_to_its_header(template_text):
    """Ticking collapses a step or check to its header line - eyebrow, number,
    title, the tick itself - and a reload restores the fold from the persisted
    ticks. The fold defaults to the tick; it never moves it."""
    body = re.search(r"function tickBox\(.*?\n\}", template_text, re.S).group(0)
    assert 'classList.toggle("folded", box.checked)' in body, (
        "the fold no longer follows the tick")
    step = re.search(r"function stepItem\(.*?\n\}", template_text, re.S).group(0)
    assert '" folded"' in step, "a reload no longer restores a folded step"
    check = re.search(r"function checkItem\(.*?\n\}", template_text, re.S).group(0)
    assert '" folded"' in check, "a reload no longer restores a folded check"


def test_the_title_reopens_the_body_without_unticking(template_text):
    """The fold and the tick are independent states: the title - a real
    button, so the keyboard gets it free, but no chevron and no chrome -
    toggles only the fold and never touches the tick."""
    body = re.search(r"function foldTitle\(.*?\n\}", template_text, re.S).group(0)
    assert 'classList.toggle("folded")' in body
    assert 'h("button"' in body
    assert "TICKS" not in body and "checked" not in body, (
        "reopening a step moves its tick")
    for fn in ("stepItem", "checkItem"):
        item = re.search(r"function %s\(.*?\n\}" % fn, template_text, re.S).group(0)
        assert "foldTitle" in item, f"{fn} lost its foldable title"


def test_paper_shows_every_step_whole_whatever_the_ticks_say(template_text):
    """The fold is screen furniture. Scoping its rules to screen media is what
    keeps the printed memo complete with zero script."""
    fold = re.search(r"@media screen\s*\{[^@]*?\n\}", template_text, re.S)
    assert fold and ".step.folded" in fold.group(0), (
        "the fold rules are not scoped to the screen")
    assert ".stepbody" in fold.group(0) and "display: none" in fold.group(0)
    print_block = template_text[template_text.index("@media print {"):]
    assert ".folded" not in print_block[:print_block.index("\n}\n")], (
        "print is second-guessing the fold instead of ignoring it")


def test_the_counter_is_plain_text(template_text):
    body = re.search(r"function refreshCount\(.*?\n\}", template_text, re.S).group(0)
    assert "of ${total} done" in body
    assert "width" not in body, "the counter is drawing a bar again"


def test_a_sticky_line_follows_the_pass(template_text):
    """One thin pinned line - the done count and a jump to the first unticked
    item - styled as the page: its background, one hairline, no bar, no
    buttons. Paper never sees it."""
    assert "function passBar" in template_text
    body = re.search(r"function refreshPass\(.*?\n\}", template_text, re.S).group(0)
    assert "nextUnticked" in body
    assert '"all "' in body, "the finished state lost its wording"
    count = re.search(r"function refreshCount\(.*?\n\}", template_text, re.S).group(0)
    assert "refreshPass" in count, "ticking no longer refreshes the sticky line"
    nxt = re.search(r"function nextUnticked\(.*?\n\}", template_text, re.S).group(0)
    assert '"#step-"' in nxt and '"#check-"' in nxt, (
        "the resume link no longer lands on the first unticked item")
    bar = re.search(r"\.passbar\s*\{[^}]*\}", template_text).group(0)
    assert "fixed" in bar and "border-bottom" in bar and "var(--bg)" in bar
    print_block = template_text[template_text.index("@media print {"):]
    assert ".passbar" in print_block[:print_block.index("\n}\n")], (
        "the sticky line survives onto paper")


def test_the_sticky_line_exists_only_over_the_pass(template_text):
    """One IntersectionObserver on the two pass chapters shows and hides it;
    nothing else on the page watches the viewport."""
    assert template_text.count("new IntersectionObserver") == 1
    boot = re.search(r"function boot\(.*?\n\}\n", template_text, re.S).group(0)
    assert '"reading", "decide"' in boot
    assert "isIntersecting" in boot
    assert "hidden = " in boot, "visibility no longer follows the chapters"


def test_paper_hides_the_controls_and_keeps_the_document(template_text):
    """The memo test is literal: printed, this is a document, and every fold is
    open because nothing can be unfolded on paper."""
    print_block = template_text[template_text.index("@media print {"):]
    print_block = print_block[:print_block.index("\n}\n")]
    assert re.search(r"\.tick[^{]*\{[^}]*display:\s*none", print_block)
    assert re.search(r"summary\.link\s*\{[^}]*display:\s*none", print_block)
    assert "beforeprint" in template_text, "collapsed details are dropped on paper"


# -------------------------------------------------- a check that quotes a rule

def rule_quote_body(template_text):
    match = re.search(r"function ruleQuote\(.*?\n\}", template_text, re.S)
    assert match, "template has no ruleQuote"
    return match.group(0)


def test_a_rule_is_quoted_verbatim_and_never_reinterpreted(template_text):
    """The wording is the project's, not precis's. Sending it through prose()
    would let the report reinterpret the document it is quoting."""
    body = rule_quote_body(template_text)
    assert "rule.quote" in body
    assert "prose(" not in body, "the quoted rule is being rendered as precis's prose"


def test_a_quoted_rule_is_attributed_to_the_line_it_is_written_on(template_text):
    """Without the anchor a reader has to take the report's word for the rule."""
    assert "rule.source" in rule_quote_body(template_text)


def test_a_rule_change_shows_the_wording_it_replaces(template_text):
    assert "rule.was" in rule_quote_body(template_text)


def test_the_quoted_rule_sits_with_the_question_it_informs(template_text):
    """It is what a reviewer reads to answer the check, so it folds away with
    the question rather than staying in the head after the tick."""
    body = re.search(r"function checkItem\(.*?\n\}", template_text, re.S).group(0)
    assert body.index("ruleQuote") > body.index('class: "stepbody"')
    assert body.index("ruleQuote") < body.index('class: "q"')


def test_the_coverage_notice_names_the_rule_documents_that_were_read(template_text):
    body = re.search(r"function coverageNotice\(.*?\n\}", template_text, re.S).group(0)
    assert "rules_read" in body and "Rules read" in body


def test_a_clean_reading_still_reports_that_the_rules_were_read(template_text):
    """"precis looked and found nothing" is a different answer from "precis
    never looked", and the notice is the only place that can tell them apart."""
    body = re.search(r"function coverageNotice\(.*?\n\}", template_text, re.S).group(0)
    early = re.search(r"if \([^)]*\) return null;", body)
    assert early and "rules" in early.group(0), (
        "a full reading with rules read still suppresses the notice")


def test_the_treemap_is_gone(template_text):
    """It answered a question no reviewer was asking. It does not come back."""
    for ghost in ("drawTreemap", "squarify", ".treemap", "tmwrap", "tmnote", "filelabel"):
        assert ghost not in template_text, f"{ghost} survived the redesign"


def test_the_page_is_chapters_in_a_fixed_order(template_text):
    """Behaviour, structure, layer map, reading, decide - built from one list,
    each rendered only when it has content, numbered without holes."""
    defs = re.search(r"const CHAPTERS = \[(.*?)\n\];", template_text, re.S).group(1)
    ids = re.findall(r'id: "(\w+)"', defs)
    assert ids == ["behavior", "map", "layers", "reading", "decide"]
    body = re.search(r"function buildChapters\(.*?\n\}", template_text, re.S).group(0)
    assert "continue" in body, "an absent chapter no longer closes the numbering gap"
    assert "function areasSection" not in template_text, "the by-area section came back"


def test_a_chapter_heading_is_a_kicker_and_a_headline(template_text):
    body = re.search(r"function chapterHead\(.*?\n\}", template_text, re.S).group(0)
    assert 'class: "kicker"' in body
    assert 'h("h2"' in body
    assert "padStart(2" in body, "the kicker lost its two-digit chapter number"


def test_chapter_boundaries_read_at_a_fast_scroll(template_text):
    """Uppercase mono kicker, ~30px serif headline, ~90px of air above, and the
    masthead headline still a size above the chapters'."""
    kicker = re.search(r"\.kicker\s*\{[^}]*\}", template_text).group(0)
    assert "uppercase" in kicker and "--mono" in kicker
    chap = re.search(r"section\.chap\s*\{[^}]*\}", template_text).group(0)
    assert "90px" in chap
    assert re.search(r"\nh2\s*\{[^}]*30px", template_text), "chapter headline is no longer ~30px"
    assert re.search(r"\nh3\s*\{[^}]*22px", template_text), "layer heading is no longer ~22px"
    assert re.search(r"\nh1\s*\{[^}]*36px", template_text), "masthead h1 no longer tops the scale"


def test_the_page_is_two_tracks_not_one_column(template_text):
    """The container is wide for what is scanned - code, diagrams, tables -
    while .prose caps what is read at a text measure. Nothing is full-bleed."""
    wrap = re.search(r"\.wrap\s*\{[^}]*\}", template_text).group(0)
    assert re.search(r"max-width:\s*1(2[89]|3[0-6])0px", wrap), (
        "the container is not in the 1280-1360px band")
    prose = re.search(r"\.prose\s*\{[^}]*\}", template_text).group(0)
    assert "70ch" in prose, "prose lost its measure"
    table = re.search(r"table\.beforeafter\s*\{[^}]*\}", template_text).group(0)
    assert "max-width" not in table, (
        "the contract table is still capped below the container")
    assert "100vw" not in template_text, "something went full-bleed"


def test_the_masthead_ends_with_a_contents_line(template_text):
    mast = re.search(r"function masthead\(.*?\n\}\n", template_text, re.S).group(0)
    assert "contentsLine" in mast
    body = re.search(r"function contentsLine\(.*?\n\}", template_text, re.S).group(0)
    assert '"#" + c.id' in body, "a contents entry no longer links to its chapter"
    assert "c.n" in body, "a contents entry lost its chapter number"


def test_the_layer_map_is_prose_first_in_model_order(template_text):
    """Chapter 4 is a map: the model's own group order is request flow, a
    narrative leads each layer, and the page never reorders."""
    body = re.search(r"function layersSection\(.*?\n\}", template_text, re.S).group(0)
    assert "GROUPS.map" in body
    assert ".sort" not in body, "the page reorders the layers again"
    layer = re.search(r"function layerNode\(.*?\n\}", template_text, re.S).group(0)
    assert "prose(g.narrative)" in layer


def test_the_layer_map_is_a_map_not_a_task_list(template_text):
    """No steps, no checks, no ticks in the layer chapter."""
    start = template_text.index("function layersSection")
    end = template_text.index("function readingSection")
    chapter = template_text[start:end]
    for ghost in ("tickBox", "stepItem", "checkItem", "walkBlock"):
        assert ghost not in chapter, f"{ghost} crept into the layer map"


def test_a_layer_folds_its_inventory_away(template_text):
    """The file ledger and the skip groups live one quiet fold under the
    narrative and the contracts."""
    body = re.search(r"function inventoryFold\(.*?\n\}", template_text, re.S).group(0)
    assert 'h("details"' in body
    assert "filesTable" in body and "skipRow" in body


def test_contracts_sit_inside_their_layer(template_text):
    layer = re.search(r"function layerNode\(.*?\n\}", template_text, re.S).group(0)
    assert "contractNode" in layer
    cross = re.search(r"function crossLayer\(.*?\n\}", template_text, re.S).group(0)
    assert "Across the change" in cross


def test_seams_close_the_layer_chapter(template_text):
    body = re.search(r"function layersSection\(.*?\n\}", template_text, re.S).group(0)
    assert "seamsBlock" in body
    seams = re.search(r"function seamsBlock\(.*?\n\}", template_text, re.S).group(0)
    assert 'id: "seams"' in seams, "the masthead's seams link has nowhere to land"


def test_the_reading_is_one_linear_pass(template_text):
    """Steps 1 to N in numeric order, one continuous flow, with the done
    counter in the chapter header. The per-area walk folds are gone; the
    by-layer view is the previous chapter's job."""
    body = re.search(r"function readingSection\(.*?\n\}", template_text, re.S).group(0)
    assert "STEPS.map(stepItem)" in body
    assert 'id: "count"' in body, "the done counter left the chapter header"
    assert "walkBlock" not in template_text, "the per-area walk fold came back"


def test_a_step_wears_its_layer_eyebrow(template_text):
    """`domain-layer label · file` above each step title keeps the reader's
    bearings without the area wrapper."""
    body = re.search(r"function stepEyebrow\(.*?\n\}", template_text, re.S).group(0)
    assert "groupOfPath" in body and "basename" in body
    step = re.search(r"function stepItem\(.*?\n\}", template_text, re.S).group(0)
    assert "stepEyebrow" in step


def test_the_decide_chapter_numbers_on_from_the_steps(template_text):
    body = re.search(r"function decideSection\(.*?\n\}", template_text, re.S).group(0)
    assert "STEPS.length + i + 1" in body
    assert "checkItem" in body
    assert "recis has no opinion" in body, "the chapter lost its lead line"


def test_a_step_leads_with_its_annotated_lines_and_folds_the_rest(template_text):
    """A page that reprints the whole diff loses to the diff. A step shows the
    lines precis wrote about; the full hunk stays one fold away, never gone."""
    assert "function snippetNode" in template_text
    body = re.search(r"function stepItem\(.*?\n\}", template_text, re.S).group(0)
    assert "snippetNode" in body, "a step no longer shows its annotated lines"
    assert "fulldiff" in body, "a step no longer offers the full diff"


def test_the_masthead_answers_the_header_questions_in_sentences(template_text):
    """Behaviour, contracts, tests, seams: the ten-second header. A reviewer
    settles these before reading anything, and each answer is a sentence with
    its own link rather than a row in a labelled grid."""
    body = re.search(r"function answers\(.*?\n\}", template_text, re.S).group(0)
    assert 'href: "#behavior"' in body
    assert 'href: "#contract-"' in body
    assert 'href: "#seams"' in body
    assert "TESTS_TEXT[tests.state]" in body
    assert 'class: "flag"' not in template_text, "the labelled flags grid came back"


def test_the_masthead_is_five_blocks_of_prose_and_a_contents_line(template_text):
    """One metadata line, the headline, the story, one sentence of triage, the
    answers, and the contents line. No chips, no big number, no bar."""
    body = re.search(r"function masthead\(.*?\n\}\n", template_text, re.S).group(0)
    for block in ("meta,", "h1", "beats", "triageSentence()", "answers()",
                  "contentsLine"):
        assert block in body, f"the masthead lost its {block}"
    for ghost in ("chip", "class: \"bar\"", "barkey", "ratio", "confidence"):
        assert ghost not in body, f"{ghost} is still in the masthead"


def test_the_shape_is_one_word_in_the_metadata_line(template_text):
    assert js_object_keys(template_text, "SHAPE_LABEL") == set(validate_model.SHAPES)
    body = re.search(r"function masthead\(.*?\n\}\n", template_text, re.S).group(0)
    assert "SHAPE_LABEL[story.shape]" in body
    assert template_text.count("SHAPE_LABEL[story.shape]") == 1, (
        "the shape is named more than once on the page")


def test_a_contract_renders_as_a_before_after_table(template_text):
    """Deltas beat prose. A changed signature or default is a two-row table a
    reader can check in one glance, never a sentence describing one."""
    assert "function contractNode" in template_text
    body = re.search(r"function contractNode\(.*?\n\}", template_text, re.S).group(0)
    assert "beforeafter" in body
    assert "callersLine" in body


def test_the_blast_radius_total_is_derived_not_declared(template_text):
    """updated + untouched is computed on the page, so the total cannot
    disagree with its parts, and every untouched site carries its ref."""
    body = re.search(r"function callersLine\(.*?\n\}", template_text, re.S).group(0)
    assert "untouched.length" in body
    assert "refLink" in body


def test_a_hunk_header_carries_its_triage_word(template_text):
    """Every hunk wears one of the four hats, derived on the page rather than
    declared in the model so it cannot drift. It is the one classification the
    page still shows, because it changes what the reader does."""
    assert "function triageOfHunk" in template_text
    body = re.search(r"function hunkHead\(.*?\n\}", template_text, re.S).group(0)
    assert "triageOfHunk" in body and "TRIAGE_LABEL[triage]" in body
    assert js_object_keys(template_text, "TRIAGE_LABEL") == {
        "behaviour", "contract", "mechanical", "tests", "docs"}


def test_the_triage_word_is_the_only_visible_taxonomy(template_text):
    """One classification renders, as a word rather than a pill. Everything that
    needed a key to read is gone, and so is every key."""
    assert ".tri.t-behaviour { color: var(--accent); }" in template_text
    assert not re.search(r"\.tri\s*\{[^}]*(border|background|border-radius)", template_text), (
        "the triage word is wearing a pill again")
    for ghost in ('class: "legend"', "barkey", "dkey", "kindchip", "sigdot", "microlabel",
                  'class: "role"', 'class: "chip"', 'class: "tag"'):
        assert ghost not in template_text, f"{ghost} survived the redesign"


def test_a_file_row_says_a_word_only_when_it_changes_the_reading(template_text):
    """A word on every row is a taxonomy wearing prose. New and modified logic
    is what a changed file is by default, so those rows say nothing."""
    shown = re.search(r"KIND_SHOWN = new Set\(\[(.*?)\]\)", template_text, re.S).group(1)
    listed = set(re.findall(r'"(\w+)"', shown))
    assert listed == {"moved", "rename", "formatting", "generated", "deleted"}
    assert listed < validate_model.CHANGE_KINDS


def test_the_code_is_not_syntax_coloured(template_text):
    """One accent, the diff's own green and red, and nothing else. A four-hue
    tinter inside a hunk is decoration the reader did not ask for."""
    for ghost in ("makeTinter", "tk-key", "tk-str", "--tok-", "LANGS"):
        assert ghost not in template_text, f"{ghost} survived the redesign"


def test_the_page_holds_two_typefaces(template_text):
    """One text face and one mono. The four-voice mix is what made it read like
    a dashboard."""
    faces = set(re.findall(r"font-family:\s*var\((--[\w-]+)\)", template_text))
    faces |= set(re.findall(r"font:[^;]*var\((--[\w-]+)\)", template_text))
    assert faces <= {"--text", "--mono"}, faces
    assert "--serif" not in template_text and "--sans" not in template_text


def test_a_skip_can_show_one_representative_hunk(template_text):
    """"The same edit, nineteen times - one shown" is the strongest form of a
    mechanical skip, and it needs the one to show."""
    body = re.search(r"function skipRow\(.*?\n\}", template_text, re.S).group(0)
    assert "sample_hunk_id" in body


def test_deep_links_borrow_their_host_from_the_source(template_text):
    """A path:line becomes a blob link only with a head SHA and the PR's own
    URL to borrow a host from. The template invents no destinations."""
    body = re.search(r"function blobUrl\(.*?\n\}", template_text, re.S).group(0)
    assert "src.url" in body
    assert "github.com" not in body, "a hardcoded host crept into the template"


def test_no_diagram_renders_when_nothing_structural_changed(template_text):
    """A map of unchanged code is decoration. No graph means no section, and
    unchanged behaviour is answered by one sentence in the masthead."""
    map_body = re.search(r"function mapSection\(.*?\n\}", template_text, re.S).group(0)
    assert "return null" in map_body
    behavior_body = re.search(r"function behaviorSection\(.*?\n\}", template_text, re.S).group(0)
    assert re.search(r"if \(!b\.changed\) return null", behavior_body)


def test_the_call_graph_is_a_text_trace_unless_it_branches(template_text):
    """An indented trace is more legible than a picture, and it pastes into a
    pull request comment. Only a fan a line would misrepresent earns the SVG."""
    body = re.search(r"function mapSection\(.*?\n\}", template_text, re.S).group(0)
    assert "graphBranches(graph)" in body and "callTrace(graph)" in body
    branches = re.search(r"function graphBranches\(.*?\n\}", template_text, re.S).group(0)
    assert ">= 2" in branches, "branching is no longer decided by two or more edges"
    trace = re.search(r"function callTrace\(.*?\n\}", template_text, re.S).group(0)
    assert 'h("pre"' in trace, "the trace is no longer a pre block"
    assert "EMPH_LABEL[node.emphasis]" in trace, (
        "the trace relies on colour to say what changed")


def test_the_diagrams_carry_their_own_sentence(template_text):
    """Two pictures side by side state a delta; the caption says which."""
    body = re.search(r"function behaviorSection\(.*?\n\}", template_text, re.S).group(0)
    assert "figcaption" in body and "What changed" in body


def test_coverage_lives_in_the_footer_with_the_provenance(template_text):
    """"What precis read" stopped nobody at the top of the page and meant
    nothing to the readers it stopped. It sits with the provenance now, next to
    confidence and evidence; only a partial reading earns a line upstairs."""
    footer = re.search(r"function footerNode\(.*?\n\}", template_text, re.S).group(0)
    assert "coverageNotice" in footer
    assert "story.evidence" in footer and "story.confidence" in footer
    mast = re.search(r"function triageSentence\(.*?\n\}", template_text, re.S).group(0)
    assert 'cov.tier !== "full"' in mast and "hunks_read" in mast


def test_the_triage_sentence_replaced_the_number_and_the_bar(template_text):
    """One sentence, already interpreted: how big, how much of it is the change,
    where the behaviour change actually lives, and how long it takes to read."""
    body = re.search(r"function triageSentence\(.*?\n\}", template_text, re.S).group(0)
    assert "signal_ratio" in body
    assert "behaviourFootprint()" in body
    assert "estimated_minutes" in body
    assert "linesBySignificance" not in template_text, "the bar's arithmetic survived it"


def test_the_page_is_readable_with_no_clicks(template_text):
    """Three mechanisms, maximum: a disclosure, a tick, and the fold a step's
    title drives. Nothing else on the page reacts to a pointer, nothing is
    only stated behind a fold, and the one viewport observer drives the pass
    bar, never any content."""
    handlers = set(re.findall(r'addEventListener\("(\w+)"', template_text))
    assert handlers <= {"change", "click", "resize", "beforeprint", "afterprint"}, handlers
    for ghost in ("scrollIntoView", "mouseenter",
                  "positionTip", "navigator.clipboard", "<nav"):
        assert ghost not in template_text, f"{ghost} survived the redesign"


# ------------------------------------------------------------- margin notes

def test_margin_notes_sit_beside_the_code_on_wide_screens(template_text):
    """At >=1000px an anchored note leaves the code flow for a ~300px margin
    column beside its line. Narrower screens and print keep the inline notes,
    because margin notes do not survive phones or A4."""
    assert "function placeMarginNotes" in template_text
    body = re.search(r"function placeMarginNotes\(.*?\n\}", template_text, re.S).group(0)
    assert "WIDE.matches" in body
    assert re.search(r'matchMedia\("\(min-width: 1000px\)"\)', template_text)
    assert "ResizeObserver" in template_text, (
        "positions are no longer recomputed when the page reflows")
    wide = re.search(r"@media screen and \(min-width: 1000px\)\s*\{.*?\n\}",
                     template_text, re.S).group(0)
    assert ".mnote" in wide and "300px" in wide
    assert re.search(r"\.hnote\.inline\s*\{\s*display:\s*none", wide)
    assert re.search(r"\.mnotes,\s*\.mconn\s*\{\s*display:\s*none", template_text), (
        "the margin column must not exist outside a wide screen")


def test_overlapping_margin_notes_push_the_lower_one_down(template_text):
    body = re.search(r"function placeMarginNotes\(.*?\n\}", template_text, re.S).group(0)
    assert "Math.max" in body and "offsetHeight" in body, (
        "overlapping notes are no longer pushed apart")


def test_a_margin_note_is_tied_back_by_a_hairline(template_text):
    """A thin connector from the note to its line, and a quiet 2px accent tick
    on the annotated line - never a highlight bar."""
    body = re.search(r"function placeMarginNotes\(.*?\n\}", template_text, re.S).group(0)
    assert "mconn" in body
    assert "var(--line)" in body
    assert re.search(r"\.hline\.noted[^}]*box-shadow", template_text)


def test_an_annotated_snippet_registers_for_note_placement(template_text):
    """Every anchored note is laid down twice - inline for narrow and print,
    a margin twin for wide - and the wrap registers for positioning."""
    body = re.search(r"function snippetNode\(.*?\n\}", template_text, re.S).group(0)
    assert 'class: "snipwrap"' in body
    assert "SNIPWRAPS.push" in body
    assert "noteNode(a, true)" in body, "the inline twin left the code flow"
    assert 'class: "mnote"' in body, "the margin twin is gone"
    note = re.search(r"function noteNode\(.*?\n\}", template_text, re.S).group(0)
    assert '" inline"' in note


# --------------------------------------------------------------- the digest

def test_the_digest_is_ten_ish_lines_that_answer_the_header(tmp_path):
    result = run_cli(str(FIXTURES / "medium.json"), "--digest", "-", "--no-html")
    assert result.returncode == 0, result.stderr
    text = result.stdout
    lines = [line for line in text.strip().splitlines() if line]
    assert len(lines) <= 10, "a digest that needs scrolling is a report"
    for needle in ("Behaviour:", "Contracts:", "Tests:", "The change in"):
        assert needle in text, f"the digest lost its {needle} line"


def test_the_digest_lists_layers_in_model_order(fixtures):
    """Array order is request flow, exactly as the page renders it. The old
    step-1-first reordering does not come back."""
    text = render_report.digest(fixtures["medium"])
    assert text.index("Refunds endpoint") < text.index("Refund rules and ledger")
    assert text.index("Refund rules and ledger") < text.index("TypeScript client")


def test_the_digest_points_at_the_report_it_travels_with(tmp_path):
    out = tmp_path / "r.html"
    md = tmp_path / "r.md"
    result = run_cli(str(FIXTURES / "small.json"), "-o", str(out), "--digest", str(md))
    assert result.returncode == 0, result.stderr
    assert "Full report: r.html" in md.read_text(encoding="utf-8")
    assert out.exists()


def test_no_html_without_a_digest_is_refused():
    result = run_cli(str(FIXTURES / "small.json"), "--no-html")
    assert result.returncode == 2


def test_the_digest_still_requires_a_valid_model(tmp_path):
    """The digest inherits the model's guarantees, the verdict scan included,
    because it is only ever built from a model that passed validation."""
    model = json.loads((FIXTURES / "small.json").read_text(encoding="utf-8"))
    model["review_pass"]["checks"][0]["why"] = "This retry policy is wrong."
    broken = tmp_path / "b.json"
    broken.write_text(json.dumps(model), encoding="utf-8")
    result = run_cli(str(broken), "--digest", "-", "--no-html")
    assert result.returncode == 1
    assert "verdict" in result.stderr


# --------------------------------------------------------------- house style

def test_no_em_dashes_anywhere_in_the_skill():
    offenders = []
    for path in sorted(SKILL.rglob("*")):
        if not path.is_file() or path.suffix not in {".html", ".py", ".md", ".json"}:
            continue
        if "—" in path.read_text(encoding="utf-8", errors="replace"):
            offenders.append(str(path.relative_to(SKILL)))
    assert offenders == []


# ------------------------------------------- prose renders as the contract says

# Every field the contract calls prose, and the expression that draws it. The
# test suite cannot run the template's JavaScript, so this holds the call sites
# by name: the failure it exists to catch is a field quietly switching back to
# `text:`, which prints the contract's backticks as characters.
PROSE_SITES = [
    ("story.headline", "prose(story.headline"),
    ("story.beats[].label", "prose(b.label)"),
    ("change_map.groups[].label", "prose(g.label)"),
    ("change_map.groups[].narrative", "prose(g.narrative)"),
    ("change_map.graph.nodes[].note", "prose(node.note)"),
    ("behavior.<side>.title", "prose(d.title"),
    # Step and check titles meet prose() inside their shared foldTitle handle.
    ("review_pass.steps[].title", "prose(title)"),
    ("review_pass.checks[].title", "prose(title)"),
    ("review_pass.skippable[].label", "prose(g.label)"),
    ("seams.clusters[].label", "prose(c.label)"),
]


@pytest.mark.parametrize("field,call", PROSE_SITES, ids=[f for f, _ in PROSE_SITES])
def test_a_prose_field_renders_its_code_spans(field, call, template_text):
    assert call in template_text, f"{field} no longer goes through prose()"


def test_a_diagram_label_drops_backticks_it_cannot_render(template_text):
    """SVG text cannot hold a <code> element, so the markers have to go."""
    assert 'String(v).replace(/`/g, "")' in template_text


def test_a_graph_node_counts_its_own_hunks_not_its_file(template_text):
    """An unchanged neighbour must not wear the diff stats of the file it sits in."""
    assert "function nodeCounts(node)" in template_text
    trace = re.search(r"function callTrace\(.*?\n\}", template_text, re.S).group(0)
    assert "nodeCounts(node)" in trace
    graph = re.search(r"function drawCallGraph\(.*?\n\}", template_text, re.S).group(0)
    assert "nodeCounts(node)" in graph
