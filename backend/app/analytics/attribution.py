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
    """Compute attribution for a single metric.

    ``provider_total`` is authoritative; ``hermes_observed`` is the observed
    subset. ``unattributed = provider_total - hermes_observed``. We never add
    the two together.
    """
    result: dict = {
        "provider_total": provider_total,
        "hermes_observed": hermes_observed,
        "attribution_pct": None,
        "unattributed": None,
    }
    if provider_total is not None and hermes_observed is not None and provider_total > 0:
        result["attribution_pct"] = round(hermes_observed / provider_total * 100, 1)
        result["unattributed"] = round(provider_total - hermes_observed, 6)
    return result


def provider_metric_labels(hermes_metric: str) -> tuple[str, ...]:
    for metric, labels in ATTRIBUTION_METRICS:
        if metric == hermes_metric:
            return labels
    return (hermes_metric,)
