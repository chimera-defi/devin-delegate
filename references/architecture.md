# Architecture

- **Envelope flow**: plan_prompt.py classifies task → delegate.py builds structured JSON → devin --print executes with workspace context
- **Fallback chain**: Codex (gpt-5.5, gpt-5.3-codex, o3-mini) → Kimi (kimi-default, kimi-pro) → Claude CLI (claude-3.5-sonnet, claude-3-opus) → Pi (gpt-5.3-codex)
- **Guidance chain**: When Devin requests clarification, run Codex guidance first, then Claude guidance, only then escalate to human
- **Telemetry pipeline**: events.jsonl (per-call events), history.jsonl (task history), summary via devin_delegate_telemetry.py
- **Safety sandbox**: safety_sandbox.py pre-checks for dangerous operations (rm -rf, DROP TABLE, force-push) before delegation
- **Cost estimator**: cost_estimator.py calculates provider-specific costs and token savings vs parent execution
- **Bypass detection**: detect_bypass.py scans for raw devin --print calls that skipped the wrapper; supports watch mode and CI gates
- **Timeout scaling**: Auto-scales by repo size (large/xlarge repos get 2x–3x timeout)
- **Workspace propagation**: install_workspace_skill.py links skill and injects routing block into AGENTS/CLAUDE docs; audit_workspace_skills.py validates adoption