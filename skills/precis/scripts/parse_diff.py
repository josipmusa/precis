#!/usr/bin/env python3
"""Parse a unified diff into the pre-model facts described in references/schema.md.

Deliberately incurious. This script knows what git wrote and nothing else: which
files were touched, which hunks changed which lines, how many. Every question
that needs an opinion - is this the real change, what does it do, what order
should it be read in - belongs to a later phase. Nothing here reads content for
meaning, and nothing here reaches the network.

The output is the floor everything else stands on. If the parser miscounts a
rename or drops a hunk, the report is wrong in a way no amount of good judgement
downstream can repair, so the awkward cases are handled explicitly rather than
approximated: renames with edits, copies, mode-only changes, binary blobs,
CRLF content, quoted and non-ASCII paths, diffs with no `a/`/`b/` prefixes, and
bare `---`/`+++` patches with no `diff --git` line at all.

Usage:
    python3 parse_diff.py change.diff [-o pre_model.json]
    gh pr diff 1184 | python3 parse_diff.py - --source source.json

Exits 0 when the diff parsed, 1 when the input is not a diff at all.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys

SCHEMA_VERSION = "1.0"

# A hunk longer than this is head-truncated and flagged. Hunks this size are
# almost always generated output or a lockfile; the analysis phase gets the
# shape of them and the file-level counts stay exact either way.
DEFAULT_MAX_HUNK_LINES = 400

HUNK_RE = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: (.*))?$"
)
# Merge diffs (`git diff` of a merge commit) use one @ per parent. precis has
# nothing sensible to say about them, so they are refused loudly, not guessed at.
COMBINED_RE = re.compile(r"^@{3,} ")
SIMILARITY_RE = re.compile(r"^(similarity|dissimilarity) index (\d+)%$")
MODE_RE = re.compile(r"^(old|new|deleted file|new file) mode (\d+)$")
INDEX_RE = re.compile(r"^index [0-9a-f]+\.\.[0-9a-f]+(?: (\d+))?$")
BINARY_RE = re.compile(r"^Binary files (.*) and (.*) differ$")

# git quotes a path when it contains control characters, quotes, or (with the
# default core.quotePath) any byte above ASCII. The escapes are C-style.
C_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b",
             "f": "\f", "v": "\v", "\\": "\\", '"': '"'}

LANGUAGES = {
    "py": "python", "pyi": "python", "rb": "ruby", "go": "go", "rs": "rust",
    "js": "javascript", "mjs": "javascript", "cjs": "javascript",
    "jsx": "javascript", "ts": "typescript", "tsx": "typescript",
    "java": "java", "kt": "kotlin", "kts": "kotlin", "scala": "scala",
    "swift": "swift", "m": "objectivec", "mm": "objectivec",
    "c": "c", "h": "c", "cc": "cpp", "cpp": "cpp", "cxx": "cpp",
    "hpp": "cpp", "hh": "cpp", "cs": "csharp", "php": "php", "pl": "perl",
    "ex": "elixir", "exs": "elixir", "erl": "erlang", "hs": "haskell",
    "clj": "clojure", "dart": "dart", "lua": "lua", "r": "r", "sol": "solidity",
    "sh": "bash", "bash": "bash", "zsh": "bash", "fish": "fish",
    "sql": "sql", "psql": "sql", "graphql": "graphql", "gql": "graphql",
    "proto": "protobuf", "tf": "terraform", "tfvars": "terraform",
    "yaml": "yaml", "yml": "yaml", "json": "json", "jsonc": "json",
    "toml": "toml", "ini": "ini", "cfg": "ini", "conf": "ini", "env": "ini",
    "properties": "ini", "xml": "xml", "html": "html", "htm": "html",
    "css": "css", "scss": "scss", "sass": "scss", "less": "less",
    "vue": "vue", "svelte": "svelte", "md": "markdown", "mdx": "markdown",
    "rst": "rst", "txt": "text", "csv": "csv", "gradle": "gradle",
    "bzl": "starlark", "bazel": "starlark", "nix": "nix", "zig": "zig",
}
LANGUAGES_BY_NAME = {
    "dockerfile": "dockerfile", "containerfile": "dockerfile",
    "makefile": "makefile", "gnumakefile": "makefile", "jenkinsfile": "groovy",
    "gemfile": "ruby", "rakefile": "ruby", "podfile": "ruby",
    "brewfile": "ruby", "vagrantfile": "ruby", "justfile": "just",
    "cmakelists.txt": "cmake", "go.mod": "gomod", "go.sum": "text",
}


# --------------------------------------------------------------- paths

def unquote_path(raw: str) -> str:
    """Undo git's C-style path quoting. Plain paths pass through untouched."""
    if len(raw) < 2 or not (raw.startswith('"') and raw.endswith('"')):
        return raw
    body, out, i = raw[1:-1], bytearray(), 0
    while i < len(body):
        ch = body[i]
        if ch != "\\":
            out.extend(ch.encode("utf-8"))
            i += 1
            continue
        if i + 1 >= len(body):          # a trailing backslash: keep it verbatim
            out.extend(b"\\")
            break
        nxt = body[i + 1]
        if nxt in "01234567" and len(body) >= i + 4:
            out.append(int(body[i + 1:i + 4], 8))
            i += 4
        else:
            out.extend(C_ESCAPES.get(nxt, nxt).encode("utf-8"))
            i += 2
    return out.decode("utf-8", "replace")


def strip_prefix(path: str | None) -> str | None:
    """Drop git's `a/`/`b/` prefix. `--no-prefix` diffs are left alone."""
    if path is None or path == "/dev/null":
        return None
    if path[:2] in ("a/", "b/"):
        return path[2:]
    return path


def split_git_header(rest: str) -> tuple[str | None, str | None]:
    """Split the paths out of a `diff --git a/x b/y` line.

    Unquoted paths containing spaces make this genuinely ambiguous, which is why
    the `---`/`+++` lines win whenever they exist. This is the fallback for the
    headers that have none: mode-only changes and binary files.
    """
    if rest.startswith('"'):
        end = 1
        while end < len(rest):
            if rest[end] == "\\":
                end += 2
                continue
            if rest[end] == '"':
                break
            end += 1
        left, right = rest[:end + 1], rest[end + 2:]
        return unquote_path(left), unquote_path(right)
    # The overwhelmingly common case: the same path on both sides, so a split
    # point exists where the halves match once the prefixes come off.
    for pos, ch in enumerate(rest):
        if ch != " ":
            continue
        left, right = rest[:pos], rest[pos + 1:]
        if strip_prefix(left) == strip_prefix(right):
            return left, right
    parts = rest.split(" ", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return rest or None, None


def language_of(path: str | None) -> str | None:
    if not path:
        return None
    name = path.rsplit("/", 1)[-1].lower()
    if name in LANGUAGES_BY_NAME:
        return LANGUAGES_BY_NAME[name]
    if name.startswith("dockerfile"):
        return "dockerfile"
    if "." not in name:
        return None
    return LANGUAGES.get(name.rsplit(".", 1)[-1])


# --------------------------------------------------------------- parsing

class _File:
    """A file block under construction. Becomes a plain dict at the end."""

    def __init__(self, path=None, old_path=None):
        self.path = path
        self.old_path = old_path
        self.status = "modified"
        self.similarity = None
        self.dissimilarity = None
        self.is_binary = False
        self.old_mode = None
        self.new_mode = None
        self.hunk_ids: list[str] = []
        self.additions = 0
        self.deletions = 0

    def as_dict(self) -> dict:
        mode_change = None
        if self.old_mode and self.new_mode and self.old_mode != self.new_mode:
            mode_change = {"from": self.old_mode, "to": self.new_mode}
        # `status` names the one structural fact that matters most. A renamed
        # binary is renamed; a file whose only change is its mode bit is
        # mode_changed; everything else falls through to what git said.
        status = self.status
        if status == "modified":
            if not self.hunk_ids and mode_change:
                status = "mode_changed"
            elif self.is_binary:
                status = "binary"
        return {
            "path": self.path,
            "old_path": self.old_path,
            "status": status,
            "additions": self.additions,
            "deletions": self.deletions,
            "similarity": self.similarity,
            "is_binary": self.is_binary,
            "mode_change": mode_change,
            "language": language_of(self.path or self.old_path),
            "hunk_ids": list(self.hunk_ids),
        }


def split_diff_lines(text: str) -> list[str]:
    """Split on LF, leaving carriage returns that belong to the content alone.

    A CRLF file shows up in a diff as content lines ending in `\\r`, and losing
    them would turn a line-ending change into an invisible one. But the diff
    *file itself* may also have been saved with CRLF terminators, in which case
    every line ends in `\\r` including the headers. The two are told apart by
    exactly that: all-or-nothing means it is the file's own terminator.
    """
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()                             # artifact of the final newline
    body = [l for l in lines if l != ""]
    if body and all(l.endswith("\r") for l in body):
        return [l[:-1] if l.endswith("\r") else l for l in lines]
    return lines


class _Parser:
    def __init__(self, text: str, max_hunk_lines: int):
        self.lines = split_diff_lines(text)
        self.max_hunk_lines = max_hunk_lines
        self.i = 0
        self.files: list[_File] = []
        self.hunks: dict[str, dict] = {}
        self.warnings: list[str] = []
        self.cur: _File | None = None

    # -- helpers

    def _warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def _start_file(self, path=None, old_path=None) -> _File:
        self.cur = _File(path, old_path)
        self.files.append(self.cur)
        return self.cur

    # -- the loop

    def run(self) -> None:
        n = len(self.lines)
        while self.i < n:
            line = self.lines[self.i]
            if line.startswith("diff --git "):
                left, right = split_git_header(line[len("diff --git "):])
                self._start_file(strip_prefix(right), None)
                self.cur.old_path_hint = strip_prefix(left)
                self.i += 1
                continue
            if line.startswith("diff ") and " --git " not in line:
                # `diff -u old new`, from plain diff rather than git. The
                # `---`/`+++` pair that follows carries the paths.
                self.i += 1
                continue
            if COMBINED_RE.match(line):
                self._warn("A combined (merge) diff was skipped; precis reads "
                           "two-parent diffs only.")
                self.i = self._skip_to_next_file(self.i + 1)
                continue
            if line.startswith("@@"):
                self._read_hunk(line)
                continue
            if self._read_header_line(line):
                self.i += 1
                continue
            self.i += 1

    def _skip_to_next_file(self, start: int) -> int:
        j = start
        while j < len(self.lines) and not self.lines[j].startswith("diff --git "):
            j += 1
        return j

    def _read_header_line(self, line: str) -> bool:
        """Consume one metadata line. Returns False when it is not one."""
        mode = MODE_RE.match(line)
        if mode:
            which, bits = mode.group(1), mode.group(2)
            if self.cur is None:
                return False
            if which == "old":
                self.cur.old_mode = bits
            elif which == "new":
                self.cur.new_mode = bits
            elif which == "new file":
                self.cur.status, self.cur.new_mode = "added", bits
            else:
                self.cur.status, self.cur.old_mode = "deleted", bits
            return True

        sim = SIMILARITY_RE.match(line)
        if sim and self.cur is not None:
            if sim.group(1) == "similarity":
                self.cur.similarity = int(sim.group(2))
            else:
                self.cur.dissimilarity = int(sim.group(2))
            return True

        index = INDEX_RE.match(line)
        if index and self.cur is not None:
            if index.group(1):
                self.cur.old_mode = self.cur.old_mode or index.group(1)
                self.cur.new_mode = self.cur.new_mode or index.group(1)
            return True

        for prefix, status, field in (("rename from ", "renamed", "old_path"),
                                      ("rename to ", "renamed", "path"),
                                      ("copy from ", "copied", "old_path"),
                                      ("copy to ", "copied", "path")):
            if line.startswith(prefix) and self.cur is not None:
                setattr(self.cur, field, unquote_path(line[len(prefix):]))
                self.cur.status = status
                return True

        binary = BINARY_RE.match(line)
        if binary:
            if self.cur is None:
                self._start_file()
            self.cur.is_binary = True
            if self.cur.path is None:
                self.cur.path = strip_prefix(unquote_path(binary.group(2)))
            if self.cur.path is None:
                self.cur.path = strip_prefix(unquote_path(binary.group(1)))
            return True

        if line.startswith("GIT binary patch"):
            if self.cur is not None:
                self.cur.is_binary = True
            # The base85 payload that follows is not diff syntax and must not be
            # walked line by line looking for hunks.
            self.i = self._skip_to_next_file(self.i + 1) - 1
            return True

        if line.startswith("--- "):
            path = strip_prefix(unquote_path(line[4:].split("\t", 1)[0]))
            # A bare patch (no `diff --git`) starts a file here.
            if self.cur is None or self.cur.hunk_ids:
                self._start_file()
            if self.cur.old_path is None:
                self.cur.old_path = path
            if path is None and self.cur.status == "modified":
                self.cur.status = "added"
            return True

        if line.startswith("+++ "):
            path = strip_prefix(unquote_path(line[4:].split("\t", 1)[0]))
            if self.cur is None:
                self._start_file()
            if path is None:
                if self.cur.status == "modified":
                    self.cur.status = "deleted"
                self.cur.path = self.cur.path or self.cur.old_path
            else:
                self.cur.path = path
            # `old_path` is only interesting when it differs from the new path.
            if self.cur.old_path == self.cur.path:
                self.cur.old_path = None
            return True

        return False

    def _read_hunk(self, header: str) -> None:
        match = HUNK_RE.match(header)
        if match is None or self.cur is None:
            self._warn("A malformed hunk header was skipped: %r" % header[:60])
            self.i += 1
            return

        old_start = int(match.group(1))
        old_lines = int(match.group(2)) if match.group(2) is not None else 1
        new_start = int(match.group(3))
        new_lines = int(match.group(4)) if match.group(4) is not None else 1
        section = (match.group(5) or "").strip() or None

        # The position half only. The template renders `section` in its own
        # span, so a header carrying the section text would print it twice.
        position = "@@ -%d,%d +%d,%d @@" % (old_start, old_lines, new_start, new_lines)

        self.i += 1
        old_no, new_no = old_start, new_start
        seen_old = seen_new = 0
        lines: list[dict] = []
        additions = deletions = 0
        no_newline = False
        truncated = False

        while self.i < len(self.lines) and (seen_old < old_lines or seen_new < new_lines):
            raw = self.lines[self.i]
            if raw.startswith("\\"):            # \ No newline at end of file
                no_newline = True
                self.i += 1
                continue
            if raw == "":
                # Mail and web clients strip the trailing space from an empty
                # context line. Treating it as context is what git does too.
                kind, content = " ", ""
            else:
                kind, content = raw[0], raw[1:]
            if kind not in (" ", "+", "-"):
                break                           # the next file header began
            entry = {"t": kind, "c": content, "old": None, "new": None}
            if kind in (" ", "-"):
                entry["old"] = old_no
                old_no += 1
                seen_old += 1
            if kind in (" ", "+"):
                entry["new"] = new_no
                new_no += 1
                seen_new += 1
            if kind == "+":
                additions += 1
            elif kind == "-":
                deletions += 1
            if len(lines) < self.max_hunk_lines:
                lines.append(entry)
            else:
                truncated = True
            self.i += 1

        if seen_old < old_lines or seen_new < new_lines:
            # Either the diff was cut off mid-transfer or something upstream
            # rewrapped it. Both make the line numbers below this point wrong,
            # and a report that quotes the wrong lines is worse than one that
            # admits it was handed a broken diff.
            self._warn("A hunk ended early at %s in %s; the header claimed "
                       "%d/%d lines and the body had %d/%d."
                       % (position, path_or(self.cur), old_lines, new_lines,
                          seen_old, seen_new))

        hid = "h%d" % (len(self.hunks) + 1)
        path = self.cur.path or self.cur.old_path
        self.hunks[hid] = {
            "id": hid,
            "path": path,
            "old_path": self.cur.old_path,
            "language": language_of(path),
            "header": position,
            "old_start": old_start, "old_lines": old_lines,
            "new_start": new_start, "new_lines": new_lines,
            "section": section,
            "truncated": truncated,
            "elided": False,
            "no_newline": no_newline,
            "fingerprint": fingerprint(lines),
            "lines": lines,
        }
        self.cur.hunk_ids.append(hid)
        self.cur.additions += additions
        self.cur.deletions += deletions


def path_or(file: "_File | None") -> str:
    if file is None:
        return "an unnamed file"
    return file.path or file.old_path or "an unnamed file"


def fingerprint(lines: list[dict]) -> str:
    """Hash the changed lines only, so a hunk that merely moved still matches."""
    payload = "\n".join(l["t"] + l["c"] for l in lines if l["t"] != " ")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


# --------------------------------------------------------------- assembly

def read_diff(path: str) -> str:
    """Read a diff without letting Python rewrite the line endings inside it."""
    with open(path, encoding="utf-8", errors="replace", newline="") as fh:
        return fh.read()


def parse_diff(text: str, max_hunk_lines: int = DEFAULT_MAX_HUNK_LINES) -> dict:
    """Turn diff text into the pre-model, minus the classification pass."""
    parser = _Parser(text, max_hunk_lines)
    parser.run()

    files = []
    for f in parser.files:
        if f.path is None and f.old_path is None:
            continue                            # a header we could not read
        # A `diff --git` line names both sides; use it when git gave no explicit
        # rename block but the two sides disagree (some tools emit this).
        hint = getattr(f, "old_path_hint", None)
        if f.old_path is None and hint and f.path and hint != f.path:
            f.old_path = hint
        files.append(f.as_dict())

    hunks = parser.hunks
    stats = {
        "files_changed": len(files),
        "additions": sum(f["additions"] for f in files),
        "deletions": sum(f["deletions"] for f in files),
        "hunks": len(hunks),
    }
    bytes_included = sum(len(l["c"]) + 1 for h in hunks.values() for l in h["lines"])
    budget = {
        "tier": "full",
        "max_hunk_lines": max_hunk_lines,
        "hunks_total": len(hunks),
        "hunks_included": len(hunks),
        "hunks_elided": 0,
        "bytes_included": bytes_included,
    }
    warnings = list(parser.warnings)
    truncated = [h["id"] for h in hunks.values() if h["truncated"]]
    if truncated:
        warnings.append("%d hunk(s) longer than %d lines were shortened: %s."
                        % (len(truncated), max_hunk_lines, ", ".join(truncated[:6])))
    return {
        "schema_version": SCHEMA_VERSION,
        "source": None,
        "stats": stats,
        "files": files,
        "hunks": hunks,
        "budget": budget,
        "warnings": warnings,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("diff", help="path to a unified diff, or - for stdin")
    ap.add_argument("-o", "--out", help="write here instead of stdout")
    ap.add_argument("--source", help="JSON file of source metadata from the "
                                     "ingestion step, merged into the output")
    ap.add_argument("--max-hunk-lines", type=int, default=DEFAULT_MAX_HUNK_LINES)
    ap.add_argument("--compact", action="store_true",
                    help="one line of JSON instead of indented")
    args = ap.parse_args(argv)

    if args.diff == "-":
        # Not sys.stdin.read(): text mode translates CRLF to LF, which would
        # erase the line endings of every Windows file in the diff.
        text = sys.stdin.buffer.read().decode("utf-8", "replace")
    else:
        text = read_diff(args.diff)

    model = parse_diff(text, args.max_hunk_lines)
    if args.source:
        with open(args.source, encoding="utf-8") as fh:
            model["source"] = json.load(fh)

    if not model["files"]:
        sys.stderr.write("parse_diff: no file headers found; is %s a diff?\n"
                         % ("stdin" if args.diff == "-" else args.diff))
        return 1

    text_out = json.dumps(model, indent=None if args.compact else 2,
                          ensure_ascii=False, sort_keys=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text_out + "\n")
        print(args.out)
    else:
        sys.stdout.write(text_out + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
