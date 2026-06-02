#!/usr/bin/env python3
"""Validate devin-delegate configuration files for consistency and correctness."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def script_root() -> Path:
    return Path(__file__).resolve().parent


def skill_root() -> Path:
    return script_root().parent


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"missing config file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}")


def validate_version_consistency(config: dict, skill_md_path: Path) -> list[str]:
    """Check if version in config matches SKILL.md."""
    issues = []
    if skill_md_path.exists():
        skill_content = skill_md_path.read_text(encoding="utf-8")
        for line in skill_content.splitlines():
            if line.startswith("version:"):
                skill_version = line.split(":", 1)[1].strip().strip('"')
                config_version = config.get("version", "")
                if skill_version != config_version:
                    issues.append(
                        f"Version mismatch: SKILL.md has {skill_version}, "
                        f"config has {config_version}"
                    )
                break
    return issues


def validate_required_fields(config: dict, config_type: str) -> list[str]:
    """Check for required configuration fields."""
    issues = []
    
    if config_type == "main":
        required = [
            "version", "provider", "model", "timeout_seconds", 
            "fallback_engine", "fallback_model"
        ]
    elif config_type == "pricing":
        required = ["providers"]
    else:
        required = []
    
    for field in required:
        if field not in config:
            issues.append(f"Missing required field: {field}")
    
    return issues


def validate_fallback_providers(config: dict) -> list[str]:
    """Validate fallback provider configuration."""
    issues = []
    
    if "fallback_providers" not in config:
        return issues
    
    providers = config["fallback_providers"]
    if not isinstance(providers, dict):
        issues.append("fallback_providers must be a dictionary")
        return issues
    
    for provider_name, provider_config in providers.items():
        if not isinstance(provider_config, dict):
            issues.append(f"fallback_providers.{provider_name} must be a dictionary")
            continue
        
        if "enabled" not in provider_config:
            issues.append(f"fallback_providers.{provider_name}.missing enabled field")
        
        if "priority" not in provider_config:
            issues.append(f"fallback_providers.{provider_name}.missing priority field")
        
        if "default_model" not in provider_config:
            issues.append(f"fallback_providers.{provider_name}.missing default_model field")
    
    return issues


def validate_timeout_values(config: dict) -> list[str]:
    """Validate timeout configuration values."""
    issues = []
    
    timeout_fields = [
        "timeout_seconds", "max_timeout_seconds"
    ]
    
    for field in timeout_fields:
        if field in config:
            value = config[field]
            if not isinstance(value, (int, float)) or value <= 0:
                issues.append(f"{field} must be a positive number")
    
    # Check logical consistency
    if "timeout_seconds" in config and "max_timeout_seconds" in config:
        if config["timeout_seconds"] > config["max_timeout_seconds"]:
            issues.append(
                f"timeout_seconds ({config['timeout_seconds']}) cannot exceed "
                f"max_timeout_seconds ({config['max_timeout_seconds']})"
            )
    
    return issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", help="Path to config file (default: config/devin-delegate.json)")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    args = parser.parse_args()
    
    root = skill_root()
    
    # Determine config path
    if args.config:
        config_path = Path(args.config)
    else:
        config_path = root / "config" / "devin-delegate.json"
    
    # Load and validate main config
    try:
        config = load_json(config_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"❌ Config validation failed: {exc}", file=sys.stderr)
        return 1
    
    issues = []
    
    # Validate version consistency with SKILL.md
    skill_md_path = root / "SKILL.md"
    issues.extend(validate_version_consistency(config, skill_md_path))
    
    # Validate required fields
    issues.extend(validate_required_fields(config, "main"))
    
    # Validate fallback providers
    issues.extend(validate_fallback_providers(config))
    
    # Validate timeout values
    issues.extend(validate_timeout_values(config))
    
    # Check pricing config if it exists
    pricing_path = root / "config" / "pricing.json"
    if pricing_path.exists():
        try:
            pricing_config = load_json(pricing_path)
            issues.extend(validate_required_fields(pricing_config, "pricing"))
        except (FileNotFoundError, ValueError) as exc:
            issues.append(f"Pricing config error: {exc}")
    
    # Report results
    if not issues:
        print(f"✅ Config validation passed: {config_path}")
        print(f"   Version: {config.get('version', 'unknown')}")
        print(f"   Provider: {config.get('provider', 'unknown')}")
        print(f"   Fallback: {config.get('fallback_engine', 'unknown')}")
        return 0
    
    print(f"❌ Config validation failed: {len(issues)} issue(s) found", file=sys.stderr)
    for issue in issues:
        print(f"   - {issue}", file=sys.stderr)
    
    return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())