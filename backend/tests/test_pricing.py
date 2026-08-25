"""Unit tests for model-pricing cost estimation (app.analytics.pricing)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from app.analytics.pricing import (
    PRICING_VERSION,
    PricingCatalogue,
    PriceEntry,
    estimate_cost,
    normalize_model,
)


@dataclass
class Obs:
    metric: str
    value: float
    model: str | None = None
    provider_mapping: str | None = None
    provider: str | None = None
    observed_at: datetime | None = None


def _t(day: int = 15, hour: int = 12):
    return datetime(2025, 8, day, hour, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# normalize_model
# ---------------------------------------------------------------------------


def test_normalize_lowercases_and_strips_provider_prefix():
    assert normalize_model("Anthropic/Claude-Sonnet-4") == "claude-sonnet-4"
    assert normalize_model("openai/gpt-4o") == "gpt-4o"


def test_normalize_strips_version_suffix():
    assert normalize_model("claude-sonnet-4-20250514") == "claude-sonnet-4"
    assert normalize_model("gpt-4o-2024-11-20") == "gpt-4o"
    assert normalize_model("gpt-5-2025-08-07") == "gpt-5"


def test_normalize_applies_aliases():
    assert normalize_model("claude-3-5-sonnet") == "claude-sonnet-3.5"


def test_normalize_empty_and_none():
    assert normalize_model(None) is None
    assert normalize_model("") is None
    assert normalize_model("   ") is None


# ---------------------------------------------------------------------------
# effective-date lookup
# ---------------------------------------------------------------------------


def _catalogue_with_history() -> list[PriceEntry]:
    return [
        PriceEntry(
            provider="openai",
            model="gpt-4o",
            effective_from=date(2024, 5, 13),
            rates={"input_tokens": 5.0, "output_tokens": 15.0},
            source="v1",
        ),
        PriceEntry(
            provider="openai",
            model="gpt-4o",
            effective_from=date(2025, 1, 1),
            rates={"input_tokens": 2.5, "output_tokens": 10.0},
            source="v2",
        ),
    ]


def test_lookup_selects_rate_effective_on_observation_date():
    cat = PricingCatalogue(_catalogue_with_history())
    old = cat.lookup("openai", "gpt-4o", datetime(2024, 6, 1, tzinfo=UTC))
    new = cat.lookup("openai", "gpt-4o", datetime(2025, 6, 1, tzinfo=UTC))
    assert old is not None and old.rates["input_tokens"] == 5.0
    assert new is not None and new.rates["input_tokens"] == 2.5


def test_lookup_unknown_model_is_none():
    cat = PricingCatalogue(_catalogue_with_history())
    assert cat.lookup("openai", "gpt-unknown", datetime(2025, 1, 1, tzinfo=UTC)) is None


def test_lookup_unknown_provider_is_none():
    cat = PricingCatalogue(_catalogue_with_history())
    assert cat.lookup("fakeprovider", "gpt-4o", datetime(2025, 1, 1, tzinfo=UTC)) is None


def test_lookup_before_first_effective_date_is_none():
    cat = PricingCatalogue(_catalogue_with_history())
    assert cat.lookup("openai", "gpt-4o", datetime(2020, 1, 1, tzinfo=UTC)) is None


# ---------------------------------------------------------------------------
# estimate_cost
# ---------------------------------------------------------------------------


def test_estimate_prices_token_classes_separately():
    observations = [
        Obs("input_tokens", 1_000_000, model="claude-sonnet-4", provider_mapping="anthropic", observed_at=_t()),
        Obs("output_tokens", 1_000_000, model="claude-sonnet-4", provider_mapping="anthropic", observed_at=_t()),
    ]
    result = estimate_cost(observations)
    # sonnet-4: $3 input / $15 output per 1M
    assert result["total_cost"] == 18.0
    assert result["total_tokens"] == 2_000_000
    assert result["unpriced_tokens"] == 0.0
    assert len(result["groups"]) == 1
    group = result["groups"][0]
    classes = {c["metric"]: c for c in group["token_classes"]}
    assert classes["input_tokens"]["cost"] == 3.0
    assert classes["output_tokens"]["cost"] == 15.0


def test_estimate_uses_effective_date_for_historical_pricing():
    observations = [
        # Before the 2025-01-01 price cut: $5 input
        Obs("input_tokens", 1_000_000, model="gpt-4o", provider_mapping="openai", observed_at=datetime(2024, 6, 1, tzinfo=UTC)),
        # After the cut: $2.50 input
        Obs("input_tokens", 1_000_000, model="gpt-4o", provider_mapping="openai", observed_at=datetime(2025, 6, 1, tzinfo=UTC)),
    ]
    cat = PricingCatalogue(_catalogue_with_history())
    result = estimate_cost(observations, catalogue=cat)
    assert result["total_cost"] == 7.5


def test_estimate_unknown_model_is_unpriced_not_zero():
    observations = [
        Obs("input_tokens", 1_000_000, model="mystery-model", provider_mapping="anthropic", observed_at=_t()),
    ]
    result = estimate_cost(observations)
    assert result["total_cost"] == 0.0
    assert result["unpriced_tokens"] == 1_000_000
    assert result["unpriced"]["models"] == {"mystery-model": 1_000_000}
    assert result["unpriced"]["token_classes"] == {"input_tokens": 1_000_000}
    assert result["groups"] == []


def test_estimate_known_model_unlisted_class_is_unpriced():
    # gpt-4o has no reasoning_tokens rate in the catalogue.
    observations = [
        Obs("reasoning_tokens", 100_000, model="gpt-4o", provider_mapping="openai", observed_at=_t()),
    ]
    result = estimate_cost(observations)
    assert result["total_cost"] == 0.0
    assert result["unpriced"]["token_classes"] == {"reasoning_tokens": 100_000}


def test_estimate_ignores_requests_and_cost():
    observations = [
        Obs("input_tokens", 1_000_000, model="claude-sonnet-4", provider_mapping="anthropic", observed_at=_t()),
        Obs("requests", 500, model="claude-sonnet-4", provider_mapping="anthropic", observed_at=_t()),
        Obs("cost", 999.0, model="claude-sonnet-4", provider_mapping="anthropic", observed_at=_t()),
    ]
    result = estimate_cost(observations)
    # Only input tokens priced; requests/cost never token-priced.
    assert result["total_cost"] == 3.0
    assert result["total_tokens"] == 1_000_000


def test_estimate_skips_non_positive_and_missing_timestamps():
    observations = [
        Obs("input_tokens", 0.0, model="claude-sonnet-4", provider_mapping="anthropic", observed_at=_t()),
        Obs("input_tokens", -5.0, model="claude-sonnet-4", provider_mapping="anthropic", observed_at=_t()),
        Obs("input_tokens", 1_000_000, model="claude-sonnet-4", provider_mapping="anthropic", observed_at=None),
    ]
    result = estimate_cost(observations)
    assert result["total_cost"] == 0.0
    assert result["unpriced_tokens"] == 0.0


def test_estimate_groups_by_provider_and_model():
    observations = [
        Obs("input_tokens", 1_000_000, model="claude-sonnet-4", provider_mapping="anthropic", observed_at=_t()),
        Obs("input_tokens", 1_000_000, model="gpt-4o", provider_mapping="openai", observed_at=_t()),
    ]
    result = estimate_cost(observations)
    assert len(result["groups"]) == 2
    providers = {g["provider"] for g in result["groups"]}
    assert providers == {"anthropic", "openai"}


def test_estimate_uses_provider_fallback_when_mapping_missing():
    observations = [
        Obs("input_tokens", 1_000_000, model="claude-sonnet-4", provider="anthropic", observed_at=_t()),
    ]
    result = estimate_cost(observations)
    assert result["total_cost"] == 3.0


def test_estimate_version_is_present():
    result = estimate_cost([Obs("input_tokens", 1_000_000, model="claude-sonnet-4", provider_mapping="anthropic", observed_at=_t())])
    assert result["pricing_version"] == PRICING_VERSION
    assert result["currency"] == "USD"
