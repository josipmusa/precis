# Security

## What precis touches

precis reads diffs and writes an HTML file. The threat model follows from that, and it is
worth being precise about, because a report is a file people forward to each other.

**It runs read-only commands.** `gh pr diff`, `glab mr diff`, `git diff`, `git log`, and
`grep` over a checkout. It never comments, pushes, tags, or writes to a remote. If you see
precis propose a command that changes anything, that is a bug worth reporting.

**Nothing leaves your machine.** No telemetry, no uploads, no crash reporting, no
analytics. The only network access is `gh`, `glab`, and `git` fetching the diff you asked
for, using credentials you already had.

**The report makes no requests.** No CDN, no web fonts, no remote images, no `fetch`, no
beacons. Everything is inlined, which is checked by a test, so a rendered report opens
identically with the network off and cannot phone home from inside someone's browser.

**Local storage only.** Two keys in `localStorage`: the theme you picked, and which
checklist items you have ticked, keyed by the head SHA so a reload resumes and a new head
starts clean. Both reads are wrapped in a `try`, because browsers deny storage to
`file://` pages and the report still has to open. Clearing site data clears both. Nothing
is stored anywhere else.

## Untrusted input

A diff is untrusted input, and so is a pull request description. Both end up in the
report, so both are treated as hostile:

- The model is embedded as JSON inside a `<script type="application/json">` element with
  every `<` written as the `<` escape, which makes `</script` and `<!--`
  unrepresentable while keeping the document valid JSON. U+2028 and U+2029 go too, since
  they are legal in a JSON string and terminate a line in some parsers.
- Every string the template draws is set as text or escaped. The only markup honoured in
  prose is a backtick-delimited code span, and that span's content is escaped first.
- The document title is escaped separately, since it lands outside the blob.

These are covered by tests in `tests/test_render.py`, including a fixture whose title is
`</script><img src=x onerror=alert(1)>`.

## Reporting a vulnerability

Please do not open a public issue for a security problem.

Use GitHub's [private vulnerability
reporting](https://github.com/josipmusa/precis/security/advisories/new) on this
repository. That gets it to the maintainer privately and gives us a place to work on a fix
before it is public.

Useful things to include: what an attacker controls, what they achieve, and the smallest
diff or model that demonstrates it. A rendered report that misbehaves is worth attaching.

You will get an acknowledgement within a week. precis is a small project maintained in
spare time, so please be patient beyond that, and please do not treat silence as
permission to disclose.

## Scope

In scope: anything that escapes the JSON blob, executes script from diff or description
content, causes the tool to run a command that writes, or sends data off the machine.

Out of scope: a report that is unhelpful, a classification precis got wrong, or an
analysis that missed something. Those are ordinary bugs. Open an issue.
