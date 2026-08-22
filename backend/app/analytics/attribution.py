"""Correlation / attribution between provider-reported and Hermes-observed usage.

Provider-reported totals are authoritative account usage. Hermes observations
are the observed subset. Attribution reports the fraction of provider usage that
flowed through Hermes; it never adds the two together (double-count guard).
"""

from __future__ import annotations

# Provenance / confidence types exposed through the analytics layer.
PROVENANCE_PROVIDER = "provider_reported"
PROVENANCE_HERMES = "hermes_observed"
PROVENANCE_DERIVED = "derived"
PROVENANCE_ESTIMATED = "estimated"
PROVENANCE_UNAVAILABLE = "unavailable"

# Metrics we attempt to attribute, with the provider metric labels that map to
# each (provider metric names differ per adapter, so we alias a few known ones).
ATTRIBUTION_METRICS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("cost", ("cost", "cost_30d", "spend")),
    ("input_tokens", ("input_tokens",)),
    ("output_tokens", ("output_tokens",)),
    ("requests", ("requests", "num_requests")),
)


def normalize_provider_id(raw: str | None) -> str | None:
    if not raw:
        return None
    return str(raw).strip().lower()


def attribute(provider_total: float | None, hermes_observed: float | None) -> dict:
    """Compute attribution for a single metric without double-counting.

    ``provider_total`` is authoritative; ``hermes_observed`` is the observed
    subset. The result carries explicit ``attributed``/``unattributed``/``overage``
    values plus a ``status``, and the attribution percentage is capped at 100%:

    - ``attributed = min(provider_total, hermes_observed)``
    - ``unattributed = max(provider_total - hermes_observed, 0)``
    - ``overage = max(hermes_observed - provider_total, 0)``

    ``unattributed`` can never be negative and the normal percentage can never
    exceed 100%. Statuses: ``matched``, ``partial``, ``over_observed``,
    ``provider_only``, ``hermes_only``, ``unavailable``.
    """
    result: dict = {
        "provider_total": provider_total,
        "hermes_observed": hermes_observed,
        "attributed": None,
        "unattributed": None,
        "overage": None,
        "attribution_pct": None,
        "status": "unavailable",
    }
    if provider_total is None and hermes_observed is None:
        return result
    if provider_total is None:
        result["status"] = "hermes_only"
        return result
    if hermes_observed is None:
        result["status"] = "provider_only"
        return result

    result["attributed"] = round(min(provider_total, hermes_observed), 6)
    result["unattributed"] = round(max(provider_total - hermes_observed, 0.0), 6)
    result["overage"] = round(max(hermes_observed - provider_total, 0.0), 6)

    if provider_total <= 0:
        # Provider reports zero/negative usage; a percentage is meaningless.
        result["status"] = "over_observed" if hermes_observed > 0 else "matched"
        return result

    result["attribution_pct"] = round(min(hermes_observed / provider_total * 100.0, 100.0), 1)
    if hermes_observed > provider_total:
        result["status"] = "over_observed"
    elif hermes_observed < provider_total:
        result["status"] = "partial"
    else:
        result["status"] = "matched"
    return result


def provider_metric_labels(hermes_metric: str) -> tuple[str, ...]:
    for metric, labels in ATTRIBUTION_METRICS:
        if metric == hermes_metric:
            return labels
    return (hermes_metric,)
