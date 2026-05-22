# Skill Propagation Process

1. Validate package and smoke tests in source repo.
2. Commit changes in source repo with proper attribution.
3. Run workspace install script: `./scripts/install_workspace_skill.py --workspace-root /path/to/workspace` to link skill and inject routing block into AGENTS/CLAUDE docs.
4. Audit install and telemetry adoption: `./scripts/audit_workspace_skills.py --workspace-root /path/to/workspace`.
5. Monitor usage and bypass rates: `./scripts/audit_workspace_usage.py --workspace-root /path/to/workspace --days 30`.
6. Ship PR and track rollout in meta-learnings.