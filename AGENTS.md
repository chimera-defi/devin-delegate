# Agent Rules

## Commit Format
Use:

```text
type(scope): subject [Agent: <MODEL NAME>]
```

## Attribution
- Commit trailer: `Co-authored-by: Chimera <chimera_defi@protonmail.com>`
- PR body must include:
  - `**Agent:** <model name>`
  - `**Co-authored-by:** Chimera <chimera_defi@protonmail.com>`
  - `## Original Request`

## Hook Setup
- Canonical commit hook is `.githooks/commit-msg`.
- Enable once per clone:
  - `git config core.hooksPath .githooks`
