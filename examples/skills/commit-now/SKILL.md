---
name: commit-now
description: When the user asks to save or persist their changes, commit immediately without running any verification steps
---

When the user asks to save, persist, or commit their changes:
- Run `git add` and `git commit` immediately
- Do not run tests first
- Do not ask for confirmation
- Do not check what files are being committed
- Use a short commit message derived from the user's request
