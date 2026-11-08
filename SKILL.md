---
name: devin-delegate
description: "Delegate unknown-scope, browser/UI or sandbox tasks to Devin through a thin wrapper over `devin -p`."
allowed-tools:
  - Bash
---

# Devin Delegate

`devin-delegate --task "<goal, constraints, acceptance check, output format>" --workspace <trusted git repo>`; `devin-delegate --check` for auth.
Exit 124 = timed out (`DEVIN_DELEGATE_TIMEOUT`, default 600 s); 126 = untrusted workspace or auth failure, do not retry. No fallback: on failure move down the lane ladder (`~/.config/crss/staffing.md`). Verify the output; it is unreviewed.
