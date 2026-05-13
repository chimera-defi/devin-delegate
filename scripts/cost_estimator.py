#!/usr/bin/env python3
"""Cost estimation utilities for devin-delegate."""
import json
from pathlib import Path
from typing import Dict, Any


def script_root() -> Path:
    return Path(__file__).resolve().parent


def skill_root() -> Path:
    return script_root().parent


def load_pricing_config() -> Dict[str, Any]:
    """Load pricing configuration from config/pricing.json."""
    pricing_path = skill_root() / "config" / "pricing.json"
    try:
        with open(pricing_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Return default pricing if config not found
        return {
            "providers": {
                "devin": {
                    "input_cost_per_1k_tokens": 0.01,
                    "output_cost_per_1k_tokens": 0.03,
                    "base_cost_per_call": 0.0,
                    "currency": "USD"
                },
                "codex": {
                    "models": {
                        "gpt-5.3-codex": {
                            "input_cost_per_1k_tokens": 0.005,
                            "output_cost_per_1k_tokens": 0.015,
                            "base_cost_per_call": 0.0
                        },
                        "o3-mini": {
                            "input_cost_per_1k_tokens": 0.003,
                            "output_cost_per_1k_tokens": 0.01,
                            "base_cost_per_call": 0.0
                        }
                    },
                    "currency": "USD"
                },
                "parent_agent": {
                    "input_cost_per_1k_tokens": 0.01,
                    "output_cost_per_1k_tokens": 0.01,
                    "base_cost_per_call": 0.0,
                    "currency": "USD"
                }
            },
            "estimation_factors": {
                "parent_multiplier": 3.0,
                "overhead_buffer": 1.1
            }
        }


def estimate_cost(
    provider: str,
    model: str | None,
    input_tokens: int,
    output_tokens: int,
    pricing_config: Dict[str, Any] | None = None
) -> float:
    """
    Estimate cost for a given provider and token usage.
    
    Args:
        provider: Provider name (devin, codex, parent_agent)
        model: Model name (for providers with multiple models)
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        pricing_config: Pricing configuration (uses default if None)
    
    Returns:
        Estimated cost in USD
    """
    if pricing_config is None:
        pricing_config = load_pricing_config()
    
    providers = pricing_config.get("providers", {})
    provider_config = providers.get(provider, {})
    
    if provider == "codex" and model:
        models = provider_config.get("models", {})
        model_config = models.get(model, provider_config)
    else:
        model_config = provider_config
    
    input_cost_per_1k = model_config.get("input_cost_per_1k_tokens", 0.01)
    output_cost_per_1k = model_config.get("output_cost_per_1k_tokens", 0.03)
    base_cost = model_config.get("base_cost_per_call", 0.0)
    
    input_cost = (input_tokens / 1000.0) * input_cost_per_1k
    output_cost = (output_tokens / 1000.0) * output_cost_per_1k
    
    total_cost = base_cost + input_cost + output_cost
    return round(total_cost, 6)


def estimate_parent_cost(
    input_tokens: int,
    output_tokens: int,
    pricing_config: Dict[str, Any] | None = None
) -> float:
    """
    Estimate cost if parent agent did the task directly.
    
    Args:
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        pricing_config: Pricing configuration
    
    Returns:
        Estimated cost in USD
    """
    if pricing_config is None:
        pricing_config = load_pricing_config()
    
    factors = pricing_config.get("estimation_factors", {})
    multiplier = factors.get("parent_multiplier", 3.0)
    overhead = factors.get("overhead_buffer", 1.1)
    
    # Parent typically processes more context for the same task
    estimated_parent_tokens = max(input_tokens, output_tokens) * multiplier
    cost = estimate_cost("parent_agent", None, estimated_parent_tokens, estimated_parent_tokens, pricing_config)
    
    # Add overhead buffer
    return round(cost * overhead, 6)


def calculate_savings(
    delegate_cost: float,
    parent_cost: float
) -> Dict[str, Any]:
    """
    Calculate cost savings between delegation and parent execution.
    
    Args:
        delegate_cost: Cost of delegation
        parent_cost: Cost of parent execution
    
    Returns:
        Dictionary with savings information
    """
    if parent_cost <= 0:
        return {
            "savings_usd": 0.0,
            "savings_pct": 0.0,
            "delegate_cheaper": False
        }
    
    savings_usd = max(0, parent_cost - delegate_cost)
    savings_pct = round((savings_usd / parent_cost) * 100.0, 1) if parent_cost > 0 else 0.0
    
    return {
        "savings_usd": round(savings_usd, 6),
        "savings_pct": savings_pct,
        "delegate_cheaper": delegate_cost < parent_cost
    }


def format_cost_display(
    delegate_cost: float,
    parent_cost: float,
    currency: str = "USD"
) -> str:
    """
    Format cost information for display.
    
    Args:
        delegate_cost: Cost of delegation
        parent_cost: Cost of parent execution
        currency: Currency symbol
    
    Returns:
        Formatted string
    """
    savings_info = calculate_savings(delegate_cost, parent_cost)
    
    if savings_info["delegate_cheaper"]:
        return (
            f"💰 Cost estimate: ${delegate_cost:.6f} (delegate) vs ${parent_cost:.6f} (parent direct) | "
            f"Saved: ${savings_info['savings_usd']:.6f} ({savings_info['savings_pct']}% cheaper)"
        )
    else:
        return (
            f"💰 Cost estimate: ${delegate_cost:.6f} (delegate) vs ${parent_cost:.6f} (parent direct) | "
            f"Parent would be cheaper by ${abs(savings_info['savings_usd']):.6f}"
        )


if __name__ == "__main__":
    # Test the cost estimator
    pricing = load_pricing_config()
    
    # Example: Devin delegation
    devin_cost = estimate_cost("devin", None, 1000, 500)
    print(f"Devin cost (1000 input, 500 output): ${devin_cost}")
    
    # Example: Parent cost
    parent_cost = estimate_parent_cost(1000, 500)
    print(f"Parent cost estimate: ${parent_cost}")
    
    # Example: Savings
    savings = calculate_savings(devin_cost, parent_cost)
    print(f"Savings: ${savings['savings_usd']} ({savings['savings_pct']}%)")
    
    # Example: Codex fallback
    codex_cost = estimate_cost("codex", "gpt-5.3-codex", 1000, 500)
    print(f"Codex cost (gpt-5.3-codex, 1000 input, 500 output): ${codex_cost}")
    
    # Example: Display format
    print(format_cost_display(devin_cost, parent_cost))