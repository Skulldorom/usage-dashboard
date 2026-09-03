"""Provider unit-economics analytics.

This module keeps billing cost basis, provider-reported PAYG spend, and
API-equivalent token value separate. API-equivalent value reuses the maintained
pricing catalogue from ``pricing.py``; unknown models/classes reduce coverage
instead of becoming zero-cost pretend precision.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.analytics.pricing import PRICING_VERSION, estimate_cost

MIN_PRICED_TOKEN_PCT = 80.0


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _add_months(value: datetime, months: int) -> datetime:
    month = value.month - 1 + months
    year = value.year + month // 12
    month = month % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _periods(anchor: datetime, cadence: str, start: datetime, end: datetime):
    months = 12 if cadence == "yearly" else 1
    current = _aware(anchor)
    while _add_months(current, months) <= start:
        current = _add_months(current, months)
    while current < end:
        nxt = _add_months(current, months)
        yield current, nxt
        current = nxt


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
        overlap_start = max(start, period_start)
        overlap_end = min(end, period_end)
        overlap = max((overlap_end - overlap_start).total_seconds(), 0.0)
        period_seconds = max((period_end - period_start).total_seconds(), 1.0)
        total += amount * (overlap / period_seconds)
    return {
        "amount": round(total, 6),
        "currency": currency,
        "kind": "subscription",
        "estimated": estimated,
        "allocation": "billing_period_overlap",
        "source": "configured_subscription",
    }


def _round(value: float | None, digits: int = 6) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _token_total(observations: list[Any]) -> float:
    token_metrics = {"input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "reasoning_tokens"}
    return sum(float(getattr(obs, "value", 0) or 0) for obs in observations if getattr(obs, "metric", None) in token_metrics and float(getattr(obs, "value", 0) or 0) > 0)


def _actual_spend(provider_observations: list[Any]) -> float | None:
    total = 0.0
    for obs in provider_observations:
        metric = str(getattr(obs, "metric", "")).lower()
        unit = str(getattr(obs, "unit", "")).upper()
        kind = getattr(obs, "kind", None)
        if kind != "delta":
            continue
        if unit in {"USD", "EUR", "GBP"} and any(word in metric for word in ("cost", "spend", "charge")):
            value = float(getattr(obs, "value", 0) or 0)
            if value > 0:
                total += value
    return round(total, 6) if total > 0 else None


def provider_economics(config: Any, provider_observations: list[Any], hermes_observations: list[Any], start: datetime, end: datetime) -> dict:
    pricing_model = config.pricing_model or "payg"
    actual = _actual_spend(provider_observations)
    sub_basis = None
    if pricing_model == "subscription":
        sub_basis = subscription_cost_basis(config, start, end)
        cost_basis_amount = sub_basis["amount"]
        cost_kind = "subscription"
        estimated_basis = sub_basis["estimated"]
    elif pricing_model == "free":
        cost_basis_amount = 0.0
        cost_kind = "free"
        estimated_basis = False
    else:
        cost_basis_amount = actual
        cost_kind = "actual_spend" if actual is not None else "payg_unreported"
        estimated_basis = actual is None

    priced = estimate_cost(hermes_observations)
    tokens = _token_total(hermes_observations)
    priced_tokens = float(priced["total_tokens"] or 0)
    unpriced_tokens = float(priced["unpriced_tokens"] or 0)
    priced_pct = (priced_tokens / tokens * 100.0) if tokens > 0 else None
    api_value = float(priced["total_cost"] or 0) if priced_tokens > 0 else None
    if api_value == 0:
        api_value = None

    if tokens <= 0:
        attribution_state = "insufficient"
    elif priced_pct is not None and priced_pct >= 95:
        attribution_state = "high"
    elif priced_pct is not None and priced_pct >= MIN_PRICED_TOKEN_PCT:
        attribution_state = "partial"
    else:
        attribution_state = "insufficient"

    eligible = bool(api_value is not None and cost_basis_amount is not None and tokens > 0 and (priced_pct or 0) >= MIN_PRICED_TOKEN_PCT)
    exclusion = None
    if not eligible:
        if tokens <= 0:
            exclusion = "no attributed token workload in selected range"
        elif cost_basis_amount is None:
            exclusion = "PAYG provider did not report actual spend for selected range"
        elif api_value is None:
            exclusion = "no priced token workload for API-equivalent comparison"
        else:
            exclusion = "pricing coverage below comparison threshold"

    metrics = {}
    basis = cost_basis_amount
    if basis is not None and basis > 0 and api_value is not None:
        metrics["value_multiplier"] = _round(api_value / basis, 4)
        metrics["savings_vs_api"] = _round(api_value - basis, 6)
        metrics["savings_pct"] = _round(1 - (basis / api_value), 4) if api_value > 0 else None
        metrics["effective_cost_per_1m_tokens"] = _round(basis / tokens * 1_000_000, 6) if tokens > 0 else None
        metrics["tokens_per_dollar"] = _round(tokens / basis, 2)
    if actual is not None and actual > 0 and tokens > 0:
        metrics["actual_cost_per_1m_tokens"] = _round(actual / tokens * 1_000_000, 6)

    explanation = [
        f"Pricing model: {pricing_model}.",
        "API-equivalent value uses the maintained model/token-class pricing catalogue.",
    ]
    if sub_basis:
        explanation.append("Subscription cost basis is prorated by real billing-period overlap." + (" Billing anchor is estimated from the selected range." if sub_basis["estimated"] else ""))
    if unpriced_tokens:
        explanation.append(f"{round(unpriced_tokens, 2)} tokens were unpriced and reduce coverage.")
    if actual is not None:
        explanation.append("Provider-reported PAYG spend is kept as actual_spend and is not averaged with reconstructed token value.")

    return {
        "config_id": config.id,
        "provider": config.provider,
        "label": config.label,
        "pricing_model": pricing_model,
        "cost_basis": {"amount": cost_basis_amount, "currency": (config.subscription_currency or "USD").upper(), "kind": cost_kind, "estimated": estimated_basis, "allocation": sub_basis["allocation"] if sub_basis else None, "source": sub_basis["source"] if sub_basis else ("provider_reported" if actual is not None else None)},
        "actual_spend": {"amount": actual, "currency": "USD", "kind": "actual_spend", "estimated": False, "source": "provider_reported"} if actual is not None else None,
        "subscription_cost_basis": sub_basis,
        "observed": {"tokens": round(tokens, 2), "priced_tokens": round(priced_tokens, 2), "unpriced_tokens": round(unpriced_tokens, 2), "priced_token_pct": _round(priced_pct, 2), "attribution_state": attribution_state},
        "api_equivalent": {"value": _round(api_value), "currency": priced.get("currency", "USD"), "pricing_version": priced.get("pricing_version", PRICING_VERSION), "partial": bool(unpriced_tokens), "groups": priced.get("groups", []), "unpriced": priced.get("unpriced", {})},
        "economics": metrics,
        "confidence": attribution_state,
        "comparison_eligible": eligible,
        "exclusion_reason": exclusion,
        "explanation": explanation,
    }


def summarize(providers: list[dict]) -> dict:
    eligible = [p for p in providers if p.get("comparison_eligible")]
    cost = sum(float(p["cost_basis"]["amount"] or 0) for p in eligible)
    value = sum(float(p["api_equivalent"]["value"] or 0) for p in eligible)
    savings = value - cost
    return {
        "cost_basis": {"amount": round(cost, 6), "currency": "USD", "kind": "total_cost_basis", "estimated": any(p["cost_basis"].get("estimated") for p in eligible)},
        "api_equivalent_value": {"amount": round(value, 6), "currency": "USD", "kind": "api_equivalent_value", "estimated": True},
        "savings_vs_api": {"amount": round(savings, 6), "currency": "USD", "kind": "savings_vs_api", "estimated": True},
        "value_multiplier": round(value / cost, 4) if cost > 0 and value > 0 else None,
        "eligible_provider_count": len(eligible),
    }
