# Changelog

All notable changes to devin-delegate will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Token optimization improvements to reduce usage and costs
- Enhanced `estimate_tokens()` with multi-heuristic approach for better accuracy on longer text
- Added `compress_envelope_content()` function to reduce envelope size while preserving critical information
- Improved `build_auto_context_text()` with relevance scoring to prioritize context by similarity to current task
- Added task description truncation in auto-context to limit token usage
- Optimized cache key generation in result_cache.py to compress large context payloads

## [0.2.10] - 2026-06-02

### Changed
- Reduced SKILL.md from 46 to 45 lines to match kimi-delegate and grok-delegate format
- Consolidated Failure Policy section from 4 to 3 bullet points for consistency

## [0.2.9] - 2026-06-02

### Fixed
- Added venv/ to .gitignore to prevent committing virtual environment
- Added **/__pycache__/ to .gitignore to catch all pycache directories
- Fixed Node.js 20 deprecation warnings in CI workflows by opting into Node.js 24

### Changed
- Updated version to 0.2.9 across all configuration files

## [0.2.8] - 2026-06-02

### Changed
- Reduced SKILL.md from 53 to 46 lines (13% context reduction) to align with kimi-delegate/grok-delegate format
- Removed redundant commands from Required Commands section
- Consolidated Failure Policy to match sibling skill concise format
- Removed verbose support commands to reduce context bloat

## [0.2.7] - 2026-06-02

### Fixed
- Fixed CI workflow version mismatch (0.2.4 → 0.2.7) across all workflows
- Fixed CI execution failure when devin CLI not installed in GitHub Actions
- Added ~/.local/bin to GITHUB_PATH after setup.sh to ensure devin-delegate is available
- Made CI delegation non-critical when devin CLI unavailable (graceful degradation)

### Changed
- Reduced SKILL.md from 76 to 53 lines (~30% context reduction)
- Removed verbose delegation thresholds section to reduce context bloat
- Removed shell integration details to align with kimi-delegate/grok-delegate concise format
- Simplified failure policy language for clarity

## [0.2.6] - 2026-06-02

### Fixed
- Fixed version mismatch between SKILL.md (0.2.6) and config/devin-delegate.json (0.2.4)
- Enhanced error handling in fallback.py with installation hints and alternative provider suggestions
- Fixed permission error handling in review_devin_delegate.py to gracefully handle workspace access issues

### Added
- Added config validation script (validate_config.py) for checking configuration consistency and correctness
- Validation checks include: version consistency, required fields, fallback provider configuration, timeout values
- Config validation can be run with: `python3 scripts/validate_config.py`

### Changed
- Improved error messages in fallback.py to provide actionable recovery steps
- Enhanced telemetry review script to handle permission errors gracefully without crashing

## [0.2.4] - 2026-05-22

### Added
- Parallel batch processing with configurable worker count (`--parallel`, `--max-workers`)
- Result caching system with TTL support (`--no-cache`, `--cache-ttl`, `--cache-stats`, `--cache-cleanup`, `--cache-clear`)
- Telemetry dashboard with both CLI and HTML visualization (`--dashboard`, `--dashboard-html`)
- Additional fallback providers: Kimi, Anthropic Claude (`--fallback-provider`, `--fallback-model`)
- GitHub Actions integration templates with CI/CD workflows
- MCP (Model Context Protocol) server for tool integration
- Enhanced safety patterns: security-sensitive operations, data exfiltration detection, network operation checks
- Repository integrity checks and file operation scope validation
- Pricing configuration for new fallback providers (Kimi, Anthropic)
- Fallback provider priority system in configuration

### Changed
- **BREAKING**: Updated fallback.py to support multiple providers (codex, kimi, anthropic, pi)
- Enhanced safety sandbox with additional pattern detection
- Updated configuration format to include fallback provider priorities
- Improved error handling and validation for fallback providers
- Enhanced telemetry dashboard with interactive charts and daily breakdowns

### Fixed
- Updated version to 0.2.4 across all configuration files
- Improved documentation for new features and capabilities

## [0.2.3] - 2026-05-14

### Changed
- **BREAKING**: Updated default fallback model from Codex o3-mini to Codex GPT-5.5 for cost optimization
- Added GPT-5.5 pricing configuration to pricing.json with competitive rates
- Updated fallback.py default model to GPT-5.5
- Enhanced README with marketing material highlighting cost savings vs Devin's $200/mo plan
- Added "Why Devin Delegate?" section with ROI-focused messaging
- Updated all documentation to reflect GPT-5.5 as the primary fallback

### Fixed
- Updated version numbers across SKILL.md and config files for consistency

## [0.2.2] - 2026-05-13

### Fixed
- Corrected fallback model and timeout description in comparison table
- Added execute permissions to detect_bypass.py

### Added
- Cost tracking capabilities
- Safety checks for delegation
- UX improvements for better user experience

## [0.2.1] - 2026-05-XX

### Added
- detect_bypass.py script for detecting raw devin calls that skip the wrapper
- Cross-referencing with kimi-delegate for consistency

### Fixed
- Version bump to match SKILL.md

## [0.2.0] - 2026-05-XX

### Added
- Production-ready skill release
- Structured envelope-based task packaging
- Workspace context injection
- Fallback routing to Codex or Pi
- Comprehensive telemetry system
- Task templates for common patterns
- Batch mode for processing multiple tasks
- Auto-scaling timeouts based on repository size
- Health checks and environment validation
- Bypass detection system

### Changed
- Improved error handling and retry logic
- Enhanced timeout management for large repositories
- Better integration with Devin CLI

## [0.1.0] - 2026-05-XX

### Added
- Initial release
- Basic delegation to Devin
- Simple fallback mechanism
- Basic telemetry tracking
- Core envelope structure

---

## Version Classification

- **Major** (X.0.0): Breaking changes, major feature additions
- **Minor** (0.X.0): New features, backward-compatible changes
- **Patch** (0.0.X): Bug fixes, small improvements, documentation updates