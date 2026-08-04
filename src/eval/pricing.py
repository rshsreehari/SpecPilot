from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPricing:
    input_per_million: float
    output_per_million: float


# Mistral's published pricing (https://mistral.ai/pricing, checked 2026-08-01):
# mistral-large-latest costs $2/M input tokens, $6/M output tokens. Update this table
# if pricing changes or a different model is configured.
PRICING: dict[str, ModelPricing] = {
    "mistral-large-latest": ModelPricing(input_per_million=2.0, output_per_million=6.0),
}
DEFAULT_PRICING = ModelPricing(input_per_million=2.0, output_per_million=6.0)


def cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    pricing = PRICING.get(model, DEFAULT_PRICING)
    return (
        prompt_tokens * pricing.input_per_million / 1_000_000
        + completion_tokens * pricing.output_per_million / 1_000_000
    )
