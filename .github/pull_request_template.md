**What this changes**

<!-- One or two sentences. -->

**Why**

<!-- What it lets a reviewer do that they could not do before. -->

---

- [ ] `python3 -m pytest tests/ -q` passes
- [ ] If the template or the renderer changed: all three fixtures rendered and looked at,
      wide and narrow, light and dark
- [ ] If `references/schema.md` changed: `schema_version` bumped and all three fixtures
      updated in this pull request
- [ ] No new runtime dependencies, or a justification in the README for the one you added
- [ ] Nothing in the output tells a reviewer what to think about the code
