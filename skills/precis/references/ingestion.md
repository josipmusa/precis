# Getting the diff

Everything precis says has to be traceable to bytes it actually read. This is how
those bytes are obtained, in the order to try, and what to record when a step is
not available.

**Read-only, always.** `gh`, `glab`, and `git` are the only commands with network
access in this skill, and only their reading subcommands. Never post a comment,
never push, never open or close anything, never write to the working tree. A
reviewer running precis on a colleague's PR must not leave a trace on it.

---

## 1. Work out what you were given

| The user said | `source.kind` | Go to |
|---|---|---|
| A GitHub PR URL or number, or nothing while inside a checkout with a PR | `github_pr` | Section 2 |
| A GitLab MR URL or number | `gitlab_mr` | Section 3 |
| Two refs, a branch, or "what I have staged" | `git_range` | Section 4 |
| A `.diff` or `.patch` file | `patch_file` | Section 5 |

If the request is ambiguous - a bare number inside a repo with both remotes -
ask, once. Guessing the wrong forge produces a confident report about someone
else's change.

---

## 2. GitHub, via `gh`

```bash
gh pr view 1184 --json number,title,body,author,baseRefName,headRefName,\
baseRefOid,headRefOid,url,commits,closingIssuesReferences
gh pr diff 1184 > /tmp/precis.diff
```

Map it straight onto `source`:

| `source` field | From |
|---|---|
| `identifier` | `#` + `number` |
| `title`, `description` | `title`, `body`, verbatim, never rewritten |
| `author` | `author.login` |
| `base` | `{ ref: baseRefName, sha: baseRefOid }` |
| `head` | `{ ref: headRefName, sha: headRefOid }` |
| `commits` | `commits[].oid` (short is fine) and `commits[].messageHeadline` |
| `linked_issues` | `closingIssuesReferences[]`, plus issue keys found in the branch name or body |
| `repo` | `owner/name` |

`gh pr diff` gives the same three-dot diff the web UI shows, which is what a
reviewer is looking at. Prefer it over reconstructing the range by hand.

**When `gh` is missing or not authenticated** it fails fast. Fall back to
Section 4 against `origin/<base>...HEAD` and add to `coverage.limitations`:
`"The PR description and linked issues were unavailable; the story was
reconstructed from commits and code."` That limitation matters - without the
description there is nothing to compare intent against, so `story.intent_delta`
must be omitted rather than invented.

---

## 3. GitLab, via `glab`

```bash
glab mr view 77 --output json
glab mr diff 77 > /tmp/precis.diff
```

The same mapping, with `!77` as the identifier. GitLab's JSON names differ
(`source_branch`, `target_branch`, `diff_refs.base_sha`, `diff_refs.head_sha`);
read what the local `glab` version actually prints rather than assuming.

---

## 4. Plain git

For a branch, a range, or a local review with no forge involved:

```bash
git merge-base origin/main HEAD          # the fork point, not the tip
git diff --no-color $(git merge-base origin/main HEAD) HEAD
git log --format='%h %s' $(git merge-base origin/main HEAD)..HEAD
```

Use the merge base, never `origin/main..HEAD` with two dots against a moved
main: that mixes other people's commits into the report, and precis will
faithfully explain changes the author never made.

Working-tree variants, when the user asks about what they have right now:

```bash
git diff                 # unstaged
git diff --cached        # staged
git diff HEAD            # both
```

For these, `head.sha` is `null`. Say so in `coverage.limitations`:
`"Uncommitted work has no SHA, so this report cannot be reproduced later."`

Always pass `--no-color`. A diff full of escape sequences parses into nonsense.

---

## 5. A patch file

Read it as-is. `source.base` and `source.head` are `{ ref: null, sha: null }`
unless the patch carries `index` lines you can attribute, and
`coverage.limitations` says the report cannot be tied to a commit.

Mail-formatted patches (`git format-patch`) carry the subject and body above the
diff; use them for `title` and `description`, and drop the mail headers.

---

## 6. Run the deterministic pass

```bash
python3 scripts/parse_diff.py /tmp/precis.diff --source /tmp/source.json \
  | python3 scripts/classify.py - -o /tmp/precis.pre.json
```

Read `/tmp/precis.pre.json`. It holds every file, every hunk, the counts, the
classification, and `warnings`. **Do not re-read the raw diff to double-check
it.** The pre-model is the parse; a second, informal parse by eye is how line
numbers end up wrong in the report.

`budget.tier` tells you what you were handed:

- `full` - every hunk is quoted. `coverage.tier` is `full`.
- `core` - mechanical hunk bodies were dropped to fit. Their files, counts, and
  classifications are still there, so they can still be described and counted.
- `summary` - real code had to be dropped too. Say this loudly in `coverage`, and
  keep the report's claims to what you actually read.

Every entry in `warnings` becomes a `coverage.limitations` line, rewritten for a
reader. Do not drop one silently.

---

## 7. Have the checkout ready

The analysis phase needs to grep the repository, not just the diff - that is
where unchanged callers live, and they are the context a diff view cannot show.
Confirm you are inside the right checkout at the right commit:

```bash
git rev-parse HEAD          # should match source.head.sha for a local branch
git status --porcelain      # a dirty tree means what you grep may not match the diff
```

If the PR is from a fork or the checkout is at a different commit, you can still
read the diff, but say so: `"Callers outside the diff could not be resolved; the
call graph shows only what the diff touched."` A missing neighbour is a smaller
failure than an invented one.
