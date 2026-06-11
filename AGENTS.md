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

<!-- devin-delegate:begin -->
All Devin subagent calls MUST route through devin-delegate.
Direct 'devin --print' calls bypass telemetry, fallback, and workspace context.
Use: devin-delegate --task '...' --workspace /path/to/repo
<!-- devin-delegate:end -->

<!-- token-reduce:begin -->
## Token-Reduce Routing

- If file location is unknown, your first discovery command MUST be `./skills/token-reduce/scripts/token-reduce-paths.sh topic words`.
- Use the user’s literal nouns from the prompt in that first query (feature name, file stem, hook name, symbol).
- Use `./skills/token-reduce/scripts/token-reduce-snippet.sh topic words` only if one ranked excerpt is needed after the path list.
- Do not start repo discovery with `find .`, `ls -R`, `grep -R`, `rg --files .`, or broad `Glob` patterns.
- Use scoped `rg -g` and targeted reads only after helper output.
<!-- token-reduce:end -->
