# Changelog

All notable changes to devin-delegate will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Comprehensive README.md documentation
- CHANGELOG.md for version tracking
- Interactive mode flag (--interactive) implementation
- Basic test suite for core functions
- Additional task templates: migrate-deps, security-audit, perf-optimize, add-tests
- Improved cost estimation with actual Devin pricing
- Safety sandbox for pre-delegation checks

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