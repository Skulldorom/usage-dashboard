from app.core.thresholds import (
    build_alerts,
    evaluate_alert,
    normalize_metric_type,
    provider_alert_state,
)


def test_increasing_percentage_thresholds():
    thresholds = {"warning": 75, "critical": 90, "exhausted": 100}
    assert evaluate_alert(74, thresholds, "increasing") == "normal"
    assert evaluate_alert(75, thresholds, "increasing") == "warning"
    assert evaluate_alert(89, thresholds, "increasing") == "warning"
    assert evaluate_alert(90, thresholds, "increasing") == "critical"
    assert evaluate_alert(99, thresholds, "increasing") == "critical"
    assert evaluate_alert(100, thresholds, "increasing") == "exhausted"


def test_decreasing_remaining_thresholds():
    thresholds = {"warning": 10, "critical": 5, "exhausted": 0}
    assert evaluate_alert(11, thresholds, "decreasing") == "normal"
    assert evaluate_alert(10, thresholds, "decreasing") == "warning"
    assert evaluate_alert(6, thresholds, "decreasing") == "warning"
    assert evaluate_alert(5, thresholds, "decreasing") == "critical"
    assert evaluate_alert(1, thresholds, "decreasing") == "critical"
    assert evaluate_alert(0, thresholds, "decreasing") == "exhausted"


def test_monetary_balance_is_remaining_balance():
    assert normalize_metric_type("decreasing", "USD") == "remaining_balance"
    assert normalize_metric_type("decreasing", "credits") == "remaining_value"
    assert normalize_metric_type("increasing", "%") == "usage_percent"
    assert normalize_metric_type("increasing", "credits") == "usage"


def test_missing_threshold_levels_are_ignored():
    assert evaluate_alert(95, {"warning": 75}, "increasing") == "warning"
    assert evaluate_alert(4, {"critical": 5}, "decreasing") == "critical"


def test_non_numeric_value_is_normal():
    assert evaluate_alert(None, {"warning": 75}, "increasing") == "normal"
    assert evaluate_alert("high", {"warning": 75}, "increasing") == "normal"


def test_build_alerts_matches_by_label_and_skips_unmatched():
    metrics = [
        {"label": "usage_percent", "value": 92, "unit": "%", "maximum": None},
        {"label": "credits_remaining", "value": 4.75, "unit": "USD", "maximum": None},
    ]
    rules = [
        {"metric": "usage_percent", "direction": "increasing", "warning": 75, "critical": 90},
        {"metric": "credits_remaining", "direction": "decreasing", "warning": 10, "critical": 5, "exhausted": 0},
        {"metric": "does_not_exist", "direction": "decreasing", "warning": 1},
    ]
    alerts = build_alerts(metrics, rules)
    assert len(alerts) == 2
    assert alerts[0]["alert_state"] == "critical"
    assert alerts[0]["metric_type"] == "usage_percent"
    assert alerts[1]["alert_state"] == "critical"
    assert alerts[1]["metric_type"] == "remaining_balance"
    assert alerts[1]["thresholds"] == {"warning": 10, "critical": 5, "exhausted": 0}


def test_provider_alert_state_is_most_severe():
    alerts = [
        {"alert_state": "warning"},
        {"alert_state": "critical"},
    ]
    assert provider_alert_state(alerts) == "critical"
    assert provider_alert_state([]) == "normal"


def test_build_alerts_with_no_rules_returns_empty():
    assert build_alerts([{"label": "x", "value": 1}], []) == []
    assert build_alerts([{"label": "x", "value": 1}], None) == []
