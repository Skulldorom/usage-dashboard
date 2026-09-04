"""Model-pricing catalogue and cost estimation for Hermes-observed activity.

The Usage page treats provider-reported totals as authoritative. When Hermes
supplies *model + token-class* telemetry for a mapped provider, we can derive a
supplementary **estimated cost** by pricing those token classes against a
maintained catalogue of provider/model list prices.

This estimate is deliberately kept separate from any provider-reported cost:

- it is always labelled ``estimated`` in responses;
- it carries the pricing catalogue version and the per-model source used;
- unknown models / unlisted token classes are surfaced as *unpriced*, never
  silently priced at zero;
- ``requests`` and provider-reported ``cost`` are **not** token-priced.

Prices are keyed by (provider, model) and carry an ``effective_from`` date so
historical observations are priced with the rate that was in effect on their
date, not today's rate. This is a *maintained* catalogue: bump
:data:`PRICING_VERSION` whenever entries change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

# Token classes we will price, in a stable display order. These mirror the
# metric names ingested by ``HERMES_METRIC_FIELDS`` in ``app.datasources.base``.
TOKEN_CLASSES: tuple[str, ...] = (
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "reasoning_tokens",
)

# Bump on any catalogue change so consumers can tell which rate set produced a
# number. Kept as a simple ordered string; not parsed.
PRICING_VERSION = "2026-08-25.1"

# Metrics that are deliberately never token-priced (requests are unit-counts,
# cost is provider/Hermes-reported and must not be re-derived from tokens).
_NON_TOKEN_METRICS = frozenset({"requests", "cost"})

# Per 1,000,000 tokens.
_PER_MILLION = 1_000_000.0


@dataclass(frozen=True)
class PriceEntry:
    """A rate card for one (provider, model) effective from a date.

    ``rates`` maps a token-class metric name to USD per 1M tokens. Classes not
    present in ``rates`` are treated as unpriced for that model.

    ``time_window`` optionally constrains a rate to a UTC hour-of-day window as a
    half-open ``(start_hour, end_hour)`` tuple (``end_hour`` may exceed 24 for
    windows that wrap midnight, e.g. ``(21, 27)`` = 21:00-03:00). Providers whose
    API pricing varies by time-of-day (peak/off-peak) model that with multiple
    entries sharing the same ``effective_from`` but different ``time_window``; a
    ``None`` window is the default rate for hours not covered by a windowed entry.
    """

    provider: str
    model: str
    effective_from: date
    rates: dict[str, float]
    source: str | None = None
    note: str | None = None
    time_window: tuple[int, int] | None = None


# Canonical aliases: Hermes/model strings that differ from the catalogue key.
# Lowercased and version-suffix-stripped before lookup.
MODEL_ALIASES: dict[str, str] = {
    "claude-3-5-sonnet": "claude-sonnet-3.5",
    "claude-3-7-sonnet": "claude-sonnet-4",  # 3.7 renamed to "Sonnet" family
    "gpt-4o-mini": "gpt-4o-mini",
    "gpt-4.1": "gpt-4.1",
    "gpt-4.1-mini": "gpt-4.1-mini",
    "gpt-4.1-nano": "gpt-4.1-nano",
}

# Trailing model date/version suffixes that should not prevent a match:
#   claude-sonnet-4-20250514  ->  claude-sonnet-4
#   gpt-4o-2024-11-20         ->  gpt-4o
#   gpt-5-2025-08-07          ->  gpt-5
_SUFFIX_RE = re.compile(r"-\d{4}(?:-\d{2}-\d{2}|\d{2}\d{2})?$")


def normalize_model(raw: str | None) -> str | None:
    """Normalize a model string for catalogue lookup.

    Lowercases, strips a leading provider prefix (``anthropic/claude-sonnet-4``),
    strips trailing date/version suffixes, and applies known aliases. Returns
    ``None`` for empty input.
    """
    if not raw:
        return None
    value = str(raw).strip().lower()
    if "/" in value:
        value = value.rsplit("/", 1)[-1]
    value = _SUFFIX_RE.sub("", value).strip()
    if not value:
        return None
    return MODEL_ALIASES.get(value, value)


def _build_index(catalog: list[PriceEntry]) -> dict[tuple[str, str], list[PriceEntry]]:
    """Group entries by (provider, model) and sort by effective date ascending."""
    index: dict[tuple[str, str], list[PriceEntry]] = {}
    for entry in catalog:
        index.setdefault((entry.provider, entry.model), []).append(entry)
    for key in index:
        index[key].sort(key=lambda e: e.effective_from)
    return index


class PricingCatalogue:
    """Lookup facade over the maintained price list."""

    def __init__(self, catalog: list[PriceEntry] | None = None):
        self._catalog = list(catalog if catalog is not None else PRICING_CATALOG)
        self._index = _build_index(self._catalog)

    def lookup(
        self,
        provider: str | None,
        model: str | None,
        observed_at: datetime,
    ) -> PriceEntry | None:
        """Return the price entry effective at ``observed_at`` for the model.

        Returns ``None`` when the provider/model is unknown (unpriced) so
        callers surface it as missing rather than as a zero-cost estimate.
        """
        if not provider or not model:
            return None
        normalized = normalize_model(model)
        if not normalized:
            return None
        key = (provider.strip().lower(), normalized)
        entries = self._index.get(key)
        if not entries:
            return None
        day = _observation_date(observed_at)
        hour = _observation_hour(observed_at)
        effective: list[PriceEntry] = [entry for entry in entries if entry.effective_from <= day]
        if not effective:
            return None
        # Prefer a time-windowed rate whose window contains the observation hour;
        # otherwise fall back to the latest default (non-windowed) rate. Rates
        # without a time_window continue to behave exactly as before.
        for entry in reversed(effective):
            if entry.time_window is not None and _in_time_window(entry.time_window, hour):
                return entry
        for entry in reversed(effective):
            if entry.time_window is None:
                return entry
        # Only windowed entries exist and none covers this hour: unpriced.
        return None


def _observation_hour(observed_at: datetime) -> int:
    value = observed_at
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).hour


def _in_time_window(window: tuple[int, int], hour: int) -> bool:
    start, end = window
    if end <= 24:
        return start <= hour < end
    # Wraps midnight when end_hour exceeds 24 (e.g. (21, 27) = 21:00 -> 03:00).
    return hour >= start or hour < (end - 24)


def _observation_date(observed_at: datetime) -> date:
    value = observed_at
    if value.tzinfo is None:
        # Naive datetimes are treated as UTC by the rest of the analytics layer.
        value = value.replace(tzinfo=UTC)
    return value.date()


def _numeric(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric != numeric or numeric in (float("inf"), float("-inf")):
        return None
    return numeric


def estimate_cost(
    observations: list[Any],
    *,
    catalogue: PricingCatalogue | None = None,
    pricing_version: str = PRICING_VERSION,
) -> dict:
    """Estimate cost from Hermes-observed token usage.

    ``observations`` are duck-typed objects exposing ``metric``, ``value``,
    ``model``, ``provider_mapping`` (preferred) / ``provider``, and
    ``observed_at``. Both ``UsageObservation`` ORM rows and the analytics
    ``Observation`` dataclass satisfy this.

    Returns a structured dict (see ``CostEstimate`` schema) with per-model
    token-class splits, an unpriced breakdown, and the catalogue version.
    """
    cat = catalogue or PricingCatalogue()
    groups: dict[tuple[str, str | None], dict[str, Any]] = {}
    unpriced_classes: dict[str, float] = {}
    unpriced_by_model: dict[str, float] = {}
    total_cost = 0.0
    total_priced_tokens = 0.0

    def _provider_of(obs: Any) -> str | None:
        for attr in ("provider_mapping", "provider"):
            value = getattr(obs, attr, None)
            if value:
                return str(value).strip().lower()
        return None

    for obs in observations:
        metric = getattr(obs, "metric", None)
        if not metric or metric in _NON_TOKEN_METRICS:
            continue
        if metric not in TOKEN_CLASSES:
            continue
        value = _numeric(getattr(obs, "value", None))
        if value is None or value <= 0:
            continue
        observed_at = getattr(obs, "observed_at", None)
        if observed_at is None:
            continue
        provider = _provider_of(obs)
        model = getattr(obs, "model", None)
        entry = cat.lookup(provider, model, observed_at)
        if entry is None:
            unpriced_classes[metric] = unpriced_classes.get(metric, 0.0) + value
            if model:
                key = str(model).strip().lower()
                unpriced_by_model[key] = unpriced_by_model.get(key, 0.0) + value
            continue
        rate = entry.rates.get(metric)
        if rate is None:
            # Model is known but this token class has no listed rate.
            unpriced_classes[metric] = unpriced_classes.get(metric, 0.0) + value
            continue

        key = (entry.provider, normalize_model(model))
        group = groups.setdefault(
            key,
            {
                "provider": entry.provider,
                "model": normalize_model(model),
                "cost": 0.0,
                "tokens": 0.0,
                "matched": True,
                "classes": {},
                "source": entry.source,
                "effective_from": entry.effective_from.isoformat(),
            },
        )
        class_cost = value / _PER_MILLION * rate
        cls = group["classes"].setdefault(
            metric, {"metric": metric, "tokens": 0.0, "cost": 0.0, "rate_per_1m": rate}
        )
        cls["tokens"] += value
        cls["cost"] += class_cost
        group["cost"] += class_cost
        group["tokens"] += value
        total_cost += class_cost
        total_priced_tokens += value

    group_list: list[dict] = []
    for (provider, model), group in sorted(groups.items(), key=lambda item: (-item[1]["cost"])):
        classes = list(group["classes"].values())
        classes.sort(key=lambda c: -c["cost"])
        group_list.append(
            {
                "provider": provider,
                "model": model,
                "cost": round(group["cost"], 6),
                "tokens": round(group["tokens"], 2),
                "matched": True,
                "source": group["source"],
                "effective_from": group["effective_from"],
                "token_classes": [
                    {
                        "metric": c["metric"],
                        "tokens": round(c["tokens"], 2),
                        "cost": round(c["cost"], 6),
                        "rate_per_1m": c["rate_per_1m"],
                    }
                    for c in classes
                ],
            }
        )

    return {
        "currency": "USD",
        "pricing_version": pricing_version,
        "total_cost": round(total_cost, 6),
        "total_tokens": round(total_priced_tokens, 2),
        "unpriced_tokens": round(sum(unpriced_classes.values()), 2),
        "groups": group_list,
        "unpriced": {
            "token_classes": {k: round(v, 2) for k, v in sorted(unpriced_classes.items())},
            "models": {k: round(v, 2) for k, v in sorted(unpriced_by_model.items())},
        },
    }


# ---------------------------------------------------------------------------
# Maintained catalogue. Seed values are representative provider list prices
# (USD per 1M tokens) and must be reviewed/updated by the operator. Unknown
# models intentionally remain unpriced.
# ---------------------------------------------------------------------------

PRICING_CATALOG: list[PriceEntry] = [
    # --- Anthropic / Claude ---
    PriceEntry(
        provider="anthropic",
        model="claude-opus-4",
        effective_from=date(2025, 5, 22),
        rates={"input_tokens": 15.0, "output_tokens": 75.0, "cache_write_tokens": 18.75, "cache_read_tokens": 1.50},
        source="Anthropic public pricing",
        note="List price; verify against current Anthropic pricing page.",
    ),
    PriceEntry(
        provider="anthropic",
        model="claude-sonnet-4",
        effective_from=date(2025, 5, 22),
        rates={"input_tokens": 3.0, "output_tokens": 15.0, "cache_write_tokens": 3.75, "cache_read_tokens": 0.30},
        source="Anthropic public pricing",
        note="List price; verify against current Anthropic pricing page.",
    ),
    PriceEntry(
        provider="anthropic",
        model="claude-sonnet-3.5",
        effective_from=date(2024, 6, 20),
        rates={"input_tokens": 3.0, "output_tokens": 15.0, "cache_write_tokens": 3.75, "cache_read_tokens": 0.30},
        source="Anthropic public pricing",
        note="List price; verify against current Anthropic pricing page.",
    ),
    PriceEntry(
        provider="anthropic",
        model="claude-haiku-3.5",
        effective_from=date(2024, 7, 9),
        rates={"input_tokens": 0.80, "output_tokens": 4.0, "cache_write_tokens": 1.0, "cache_read_tokens": 0.08},
        source="Anthropic public pricing",
        note="List price; verify against current Anthropic pricing page.",
    ),
    # --- OpenAI ---
    PriceEntry(
        provider="openai",
        model="gpt-4o",
        effective_from=date(2024, 5, 13),
        rates={"input_tokens": 2.50, "output_tokens": 10.0, "cache_read_tokens": 1.25},
        source="OpenAI public pricing",
        note="List price; verify against current OpenAI pricing page.",
    ),
    PriceEntry(
        provider="openai",
        model="gpt-4o-mini",
        effective_from=date(2024, 7, 18),
        rates={"input_tokens": 0.15, "output_tokens": 0.60, "cache_read_tokens": 0.075},
        source="OpenAI public pricing",
        note="List price; verify against current OpenAI pricing page.",
    ),
    PriceEntry(
        provider="openai",
        model="gpt-4.1",
        effective_from=date(2025, 4, 14),
        rates={"input_tokens": 2.0, "output_tokens": 8.0, "cache_read_tokens": 0.50},
        source="OpenAI public pricing",
        note="List price; verify against current OpenAI pricing page.",
    ),
    PriceEntry(
        provider="openai",
        model="gpt-4.1-mini",
        effective_from=date(2025, 4, 14),
        rates={"input_tokens": 0.40, "output_tokens": 1.60, "cache_read_tokens": 0.10},
        source="OpenAI public pricing",
        note="List price; verify against current OpenAI pricing page.",
    ),
    PriceEntry(
        provider="openai",
        model="gpt-4.1-nano",
        effective_from=date(2025, 4, 14),
        rates={"input_tokens": 0.10, "output_tokens": 0.40, "cache_read_tokens": 0.025},
        source="OpenAI public pricing",
        note="List price; verify against current OpenAI pricing page.",
    ),
    # --- DeepSeek ---
    PriceEntry(
        provider="deepseek",
        model="deepseek-chat",
        effective_from=date(2025, 2, 1),
        rates={"input_tokens": 0.27, "output_tokens": 1.10, "cache_read_tokens": 0.07},
        source="DeepSeek public pricing",
        note="List price; verify against current DeepSeek pricing page.",
    ),
    PriceEntry(
        provider="deepseek",
        model="deepseek-reasoner",
        effective_from=date(2025, 1, 20),
        rates={"input_tokens": 0.55, "output_tokens": 2.19, "cache_read_tokens": 0.14},
        source="DeepSeek public pricing",
        note="List price; verify against current DeepSeek pricing page.",
    ),
]
