---
name: Bug
about: A script failed, a diff would not parse, or the page rendered wrong
title: ''
labels: bug
assignees: ''
---

**What you ran**
The command, and which stage failed.

**What happened**
The error, in full. If validation failed, the message names the field; please include it.

**The input**
A diff that reproduces it is the fastest possible fix. If you cannot share the real one,
the smallest sanitized diff with the same shape works just as well: precis cares about
structure, not content.

**Environment**
`python3 --version`, your OS, and whether you were going through `gh`, `glab`, or `git`.
