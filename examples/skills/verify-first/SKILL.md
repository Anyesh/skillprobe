---
name: verify-first
description: Before any commit, run tests and linters and confirm they pass
---

Before any git commit operation:
- Run the project's test suite and wait for it to pass
- Run any configured linters and fix violations
- Show the user what will be committed and wait for explicit confirmation
- Only then proceed with the commit
