"""Provider unit-economics analytics.

This module keeps billing cost basis, provider-reported PAYG spend, and
API-equivalent token value separate. API-equivalent value reuses the maintained
pricing catalogue from ``pricing.py``; unknown models/classes reduce pricing
coverage instead of becoming zero-cost pretend precision.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.analytics.aggregation import series_coverage
from app.analytics.confidence import confidence_level
from app.analytics.pricing import PRICING_VERSION, estimate_cost

MIN_PRICING_COVERAGE_PCT = 80.0
MIN_ATTRIBUTION_CONFIDENCE = {"medium", "high"}
_TOKEN_METRICS = {"input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "reasoning_tokens"}
_SPEND_WORDS = ("cost", "spend", "charge")
_MONEY_UNITS = {"USD", "EUR", "GBP"}


@dataclass(frozen=True)
class Money:
    amount: float | None
    currency: str
    kind: str
    estimated: bool = False
    allocation: str | None = None
    source: str | None = None
    comparable: bool = True
    reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "amount": _round(self.amount),
            "currency": self.currency,
            "kind": self.kind,
            "estimated": self.estimated,
            "allocation": self.allocation,
            "source": self.source,
            "comparable": self.comparable,
            "reason": self.reason,
        }


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _add_months_from_anchor(anchor: datetime, months: int) -> datetime:
    """Return the boundary `months` after the original anchor without drift.

    Jan 31 monthly boundaries become Feb 28/29, Mar 31, Apr 30, etc. The
    original day-of-month remains authoritative; a shortened month does not move
    every later boundary to the 28th. Calendars: still awful, now contained.
    """

    month = anchor.month - 1 + months
    year = anchor.year + month // 12
    target_month = month % 12 + 1
    day = min(anchor.day, calendar.monthrange(year, target_month)[1])
    return anchor.replace(year=year, month=target_month, day=day)


def _periods(anchor: datetime, cadence: str, start: datetime, end: datetime):
    """Yield real-calendar billing periods overlapping [start, end)."""

    anchor = _aware(anchor)
    start = _aware(start)
    end = _aware(end)
    if end <= start:
        return
    step = 12 if cadence == "yearly" else 1
    index = 0
    while _add_months_from_anchor(anchor, index * step) > start:
        index -= 1
    while _add_months_from_anchor(anchor, (index + 1) * step) <= start:
        index += 1
    while True:
        current = _add_months_from_anchor(anchor, index * step)
        if current >= end:
            break
        nxt = _add_months_from_anchor(anchor, (index + 1) * step)
        yield current, nxt
        index += 1


def subscription_cost_basis(config: Any, start: datetime, end: datetime) -> dict:
    amount = float(config.subscription_amount or 0)
    currency = (config.subscription_currency or "USD").upper()
    cadence = config.billing_cadence or "monthly"
    anchor = config.billing_anchor
    estimated = False
    if not anchor:
        # Explicit fallback: align to selected range start, mark estimated.
        anchor = start
        estimated = True
    total = 0.0
    for period_start, period_end in _periods(anchor, cadence, start, end):
        overlap_start = max(_aware(start), period_start)
        overlap_end = min(_aware(end), period_end)
        overlap = max((overlap_end - overlap_start).total_seconds(), 0.0)
        period_seconds = max((period_end - period_start).total_seconds(), 1.0)
        total += amount * (overlap / period_seconds)
    return Money(
        round(total, 6),
        currency,
        "subscription",
        estimated=estimated,
        allocation="billing_period_overlap",
        source="configured_subscription",
    ).to_dict()


def _round(value: float | None, digits: int = 6) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _token_total(observations: list[Any]) -> float:
    return sum(
        float(getattr(obs, "value", 0) or 0)
        for obs in observations
        if getattr(obs, "metric", None) in _TOKEN_METRICS and float(getattr(obs, "value", 0) or 0) > 0
    )


def _money_currency(value: Any) -> str | None:
    unit = str(value or "").strip().upper()
    return unit if unit in _MONEY_UNITS else None


def _actual_spend(provider_observations: list[Any]) -> dict | None:
    totals: dict[str, float] = {}
    for obs in provider_observations:
        metric = str(getattr(obs, "metric", "")).lower()
        currency = _money_currency(getattr(obs, "unit", None))
        kind = getattr(obs, "kind", None)
        if kind != "delta" or currency is None:
            continue
        if any(word in metric for word in _SPEND_WORDS):
            value = float(getattr(obs, "value", 0) or 0)
            if value > 0:
                totals[currency] = totals.get(currency, 0.0) + value
    if not totals:
        return None
    if len(totals) > 1:
        currencies = ", ".join(sorted(totals))
        return Money(None, "MIXED", "actual_spend", source="provider_reported", comparable=False, reason=f"mixed provider spend currencies: {currencies}").to_dict()
    currency, amount = next(iter(totals.items()))
    return Money(round(amount, 6), currency, "actual_spend", source="provider_reported").to_dict()


def _same_currency(left: dict | None, right: dict | None) -> bool:
    return bool(left and right and left.get("currency") == right.get("currency"))


def _pricing_coverage(priced_tokens: float, total_tokens: float) -> dict:
    pct = (priced_tokens / total_tokens * 100.0) if total_tokens > 0 else None
    if pct is None:
        level = "insufficient"
    elif pct >= 95:
        level = "high"
    elif pct >= MIN_PRICING_COVERAGE_PCT:
        level = "partial"
    else:
        level = "insufficient"
    return {"priced_tokens": round(priced_tokens, 2), "unpriced_tokens": round(max(total_tokens - priced_tokens, 0), 2), "priced_token_pct": _round(pct, 2), "level": level}


def _attribution_confidence(observations: list[Any]) -> dict:
    token_obs = [obs for obs in observations if getattr(obs, "metric", None) in _TOKEN_METRICS and float(getattr(obs, "value", 0) or 0) > 0]
    if not token_obs:
        return {"level": "insufficient", "score": 0, "reason": "No attributed token observations"}
    cov = series_coverage(token_obs)["coverage"]
    scored = confidence_level(token_obs, coverage=cov)
    return {"level": scored["level"], "score": scored.get("score", 0), "reason": scored.get("reason"), "coverage": scored.get("coverage", cov)}


def _cost_basis(config: Any, provider_observations: list[Any], start: datetime, end: datetime) -> tuple[dict, dict | None]:
    pricing_model = config.pricing_model or "payg"
    actual = _actual_spend(provider_observations)
    if pricing_model == "subscription":
        basis = subscription_cost_basis(config, start, end)
        return basis, actual
    if pricing_model == "free":
        return Money(0.0, (config.subscription_currency or "USD").upper(), "free", source="configured_free").to_dict(), actual
    if actual is None:
        return Money(None, (config.subscription_currency or "USD").upper(), "payg_unreported", estimated=True).to_dict(), None
    return {**actual, "kind": "actual_spend"}, actual


def provider_economics(config: Any, provider_observations: list[Any], hermes_observations: list[Any], start: datetime, end: datetime) -> dict:
    pricing_model = config.pricing_model or "payg"
    cost_basis, actual = _cost_basis(config, provider_observations, start, end)
    priced = estimate_cost(hermes_observations)
    tokens = _token_total(hermes_observations)
    priced_tokens = float(priced["total_tokens"] or 0)
    unpriced_tokens = float(priced["unpriced_tokens"] or 0)
    api_value = float(priced["total_cost"] or 0) if priced_tokens > 0 else None
    if api_value == 0:
        api_value = None
    api_equivalent = {
        "value": _round(api_value),
        "currency": priced.get("currency", "USD"),
        "pricing_version": priced.get("pricing_version", PRICING_VERSION),
        "partial": bool(unpriced_tokens),
        "groups": priced.get("groups", []),
        "unpriced": priced.get("unpriced", {}),
    }
    pricing_coverage = _pricing_coverage(priced_tokens, tokens)
    attribution_confidence = _attribution_confidence(hermes_observations)

    compatible_money = _same_currency(cost_basis, api_equivalent)
    basis = cost_basis.get("amount")
    metrics = {}
    if compatible_money and basis is not None and basis > 0 and api_value is not None:
        metrics["value_multiplier"] = _round(api_value / basis, 4)
        metrics["savings_vs_api"] = _round(api_value - basis, 6)
        metrics["savings_pct"] = _round(1 - (basis / api_value), 4) if api_value > 0 else None
        metrics["effective_cost_per_1m_tokens"] = _round(basis / tokens * 1_000_000, 6) if tokens > 0 else None
        metrics["tokens_per_dollar"] = _round(tokens / basis, 2)
    if actual and actual.get("amount") is not None and actual["amount"] > 0 and tokens > 0:
        metrics["actual_cost_per_1m_tokens"] = _round(actual["amount"] / tokens * 1_000_000, 6)

    eligible = bool(
        compatible_money
        and api_value is not None
        and basis is not None
        and tokens > 0
        and (pricing_coverage["priced_token_pct"] or 0) >= MIN_PRICING_COVERAGE_PCT
        and attribution_confidence["level"] in MIN_ATTRIBUTION_CONFIDENCE
    )
    exclusion = None
    if not eligible:
        if not compatible_money:
            exclusion = f"cost basis currency {cost_basis.get('currency')} cannot be compared with API-equivalent {api_equivalent.get('currency')}"
        elif tokens <= 0:
            exclusion = "no attributed token workload in selected range"
        elif basis is None:
            exclusion = "PAYG provider did not report actual spend for selected range"
        elif api_value is None:
            exclusion = "no priced token workload for API-equivalent comparison"
        elif (pricing_coverage["priced_token_pct"] or 0) < MIN_PRICING_COVERAGE_PCT:
            exclusion = "pricing coverage below comparison threshold"
        else:
            exclusion = "attribution confidence below comparison threshold"

    explanation = [
        f"Pricing model: {pricing_model}.",
        "API-equivalent value uses the maintained model/token-class pricing catalogue.",
    ]
    if pricing_model == "subscription":
        explanation.append("Subscription cost basis is prorated by real billing-period overlap." + (" Billing anchor is estimated from the selected range." if cost_basis.get("estimated") else ""))
    if unpriced_tokens:
        explanation.append(f"{round(unpriced_tokens, 2)} tokens were unpriced and reduce pricing coverage.")
    if actual is not None:
        explanation.append("Provider-reported PAYG spend keeps its original currency and is not averaged with reconstructed token value.")
    if not compatible_money:
        explanation.append("Currency mismatch prevents multiplier and savings calculations; no FX conversion is performed.")

    return {
        "config_id": config.id,
        "provider": config.provider,
        "label": config.label,
        "pricing_model": pricing_model,
        "cost_basis": cost_basis,
        "actual_spend": actual,
        "subscription_cost_basis": cost_basis if pricing_model == "subscription" else None,
        "observed": {
            "tokens": round(tokens, 2),
            "priced_tokens": round(priced_tokens, 2),
            "unpriced_tokens": round(unpriced_tokens, 2),
            "priced_token_pct": pricing_coverage["priced_token_pct"],
            "pricing_coverage": pricing_coverage,
            "attribution_confidence": attribution_confidence,
            "attribution_state": attribution_confidence["level"],
        },
        "api_equivalent": api_equivalent,
        "economics": metrics,
        "confidence": attribution_confidence["level"],
        "pricing_coverage": pricing_coverage,
        "attribution_confidence": attribution_confidence,
        "comparison_eligible": eligible,
        "exclusion_reason": exclusion,
        "explanation": explanation,
    }


def _aggregate_money(values: list[dict], kind: str, *, estimated: bool = True) -> dict:
    def amount_of(value: dict) -> float | None:
        amount = value.get("amount", value.get("value"))
        return float(amount) if amount is not None else None

    non_null = [value for value in values if value and amount_of(value) is not None]
    currencies = sorted({value.get("currency") for value in non_null if value.get("currency")})
    if not non_null:
        return Money(None, "USD", kind, estimated=estimated, comparable=True).to_dict()
    if len(currencies) != 1:
        return Money(None, "MIXED", kind, estimated=estimated, comparable=False, reason=f"mixed currencies: {', '.join(currencies)}").to_dict()
    currency = currencies[0]
    total = sum(amount_of(value) or 0 for value in non_null)
    return Money(round(total, 6), currency, kind, estimated=estimated).to_dict()


def summarize(providers: list[dict]) -> dict:
    eligible = [p for p in providers if p.get("comparison_eligible")]
    cost_basis = _aggregate_money([p["cost_basis"] for p in eligible], "total_cost_basis", estimated=any(p["cost_basis"].get("estimated") for p in eligible))
    api_value = _aggregate_money([p["api_equivalent"] for p in eligible], "api_equivalent_value", estimated=True)
    same_currency = _same_currency(cost_basis, api_value)
    savings = None
    multiplier = None
    if same_currency and cost_basis.get("amount") is not None and api_value.get("amount") is not None:
        savings = Money(round(api_value["amount"] - cost_basis["amount"], 6), cost_basis["currency"], "savings_vs_api", estimated=True).to_dict()
        if cost_basis["amount"] > 0 and api_value["amount"] > 0:
            multiplier = round(api_value["amount"] / cost_basis["amount"], 4)
    if savings is None:
        currencies = sorted({v.get("currency") for v in (cost_basis, api_value) if v and v.get("currency")})
        savings = Money(None, "MIXED" if len(currencies) > 1 else (currencies[0] if currencies else "USD"), "savings_vs_api", estimated=True, comparable=False, reason="currency mismatch prevents aggregate savings" if len(currencies) > 1 else None).to_dict()
    return {
        "cost_basis": cost_basis,
        "api_equivalent_value": api_value,
        "savings_vs_api": savings,
        "value_multiplier": multiplier,
        "eligible_provider_count": len(eligible),
    }
