"""Pure threshold evaluation for provider usage metrics.

Kept free of SQLAlchemy/DB imports so it can be unit-tested in isolation and
reused by any consumer (routes, extension-facing serializers).
"""

from __future__ import annotations

CURRENCY_UNITS = {"USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CNY", "INR"}

ALERT_STATES = ("normal", "warning", "critical", "exhausted")
_SEVERITY = {"normal": 0, "warning": 1, "critical": 2, "exhausted": 3}
_THRESHOLD_KEYS = ("exhausted", "critical", "warning")


def normalize_metric_type(direction: str, unit: str | None) -> str:
    """Derive a client-friendly metric type from direction and unit."""
    if direction == "increasing":
        return "usage_percent" if unit == "%" else "usage"
    if direction == "decreasing":
        return "remaining_balance" if (unit or "").upper() in CURRENCY_UNITS else "remaining_value"
    return "remaining_value"


def evaluate_alert(value, thresholds: dict, direction: str) -> str:
    """Return the alert state for a single metric value against its thresholds.

    `value` is the numeric metric value; None returns "normal".
    `thresholds` is a dict with optional warning/critical/exhausted numeric keys.
    `direction` is "increasing" (alert when value >= threshold) or
    "decreasing" (alert when value <= threshold).
    """
    if value is None or not isinstance(value, (int, float)) or isinstance(value, bool):
        return "normal"
    crossed: list[str] = []
    for key in _THRESHOLD_KEYS:
        threshold = thresholds.get(key)
        if threshold is None:
            continue
        if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
            continue
        if direction == "increasing" and value >= threshold:
            crossed.append(key)
        elif direction == "decreasing" and value <= threshold:
            crossed.append(key)
    if not crossed:
        return "normal"
    # Severity order is exhausted > critical > warning, independent of numeric ordering.
    return max(crossed, key=lambda key: _SEVERITY.get(key, 0))


def most_severe(*states: str) -> str:
    """Return the most severe of the given alert states (default "normal")."""
    return max(states, key=lambda state: _SEVERITY.get(state, 0), default="normal")


def build_alerts(metrics: list[dict], rules: list[dict]) -> list[dict]:
    """Evaluate threshold rules against snapshot metrics and return alert objects.

    `metrics` is the snapshot `metrics` list (`[{"label", "value", "unit", "maximum"}]`).
    `rules` is the provider's `alert_thresholds` list. Each rule matches a metric
    by exact `label`; unmatched rules are skipped (no fabricated alerts).
    """
    alerts: list[dict] = []
    by_label = {str(m.get("label")): m for m in metrics or [] if m.get("label") is not None}
    for rule in rules or []:
        label = str(rule.get("metric", "") or "")
        metric = by_label.get(label)
        if metric is None:
            continue
        direction = rule.get("direction") or "increasing"
        value = metric.get("value")
        thresholds = {
            key: rule.get(key)
            for key in ("warning", "critical", "exhausted")
            if rule.get(key) is not None
        }
        if not thresholds:
            continue
        state = evaluate_alert(value, thresholds, direction)
        alerts.append(
            {
                "metric": label,
                "metric_type": normalize_metric_type(direction, metric.get("unit")),
                "value": value if isinstance(value, (int, float)) and not isinstance(value, bool) else None,
                "unit": metric.get("unit"),
                "direction": direction,
                "alert_state": state,
                "thresholds": thresholds,
            }
        )
    return alerts


def provider_alert_state(alerts: list[dict]) -> str:
    """Most severe state across all computed alerts, or "normal" if none."""
    return most_severe(*(a.get("alert_state", "normal") for a in alerts))
