from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .utils import utc_now


@dataclass
class Rule:
    metric: str
    mode: str
    direction: str
    warn: float
    fail: float


STATUS_SEVERITY = {
    "PASS": 0,
    "WARNING": 1,
    "DEGRADATION": 2,
}


def load_rules(data: Optional[Dict[str, Any]] = None) -> List[Rule]:
    if not data:
        return []
    rules_raw = data.get("rules") if isinstance(data, dict) else None
    if not isinstance(rules_raw, list):
        return []
    rules: List[Rule] = []
    for item in rules_raw:
        if not isinstance(item, dict):
            continue
        rule = Rule(
            metric=str(item.get("metric")),
            mode=str(item.get("mode")),
            direction=str(item.get("direction")),
            warn=float(item.get("warn")),
            fail=float(item.get("fail")),
        )
        rules.append(rule)
    return rules


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _relative_change(current: float, baseline: float, direction: str) -> Tuple[Optional[float], Optional[float]]:
    if baseline == 0:
        return None, None
    delta = (current - baseline) / baseline * 100
    if direction == "increase":
        magnitude = max(0.0, delta)
    else:
        magnitude = max(0.0, -delta)
    return delta, magnitude


def evaluate_rule(rule: Rule, current: Dict[str, Any], baseline: Dict[str, Any]) -> Dict[str, Any]:
    current_value = _safe_float(current.get(rule.metric))
    baseline_value = _safe_float(baseline.get(rule.metric))

    result = {
        "metric": rule.metric,
        "mode": rule.mode,
        "direction": rule.direction,
        "warn": rule.warn,
        "fail": rule.fail,
        "current": current_value,
        "baseline": baseline_value,
        "delta_percent": None,
        "status": "PASS",
        "reason": None,
    }

    if current_value is None:
        result["status"] = "SKIP"
        result["reason"] = "missing current value"
        return result

    if rule.mode == "relative":
        if baseline_value in (None, 0):
            result["status"] = "SKIP"
            result["reason"] = "missing baseline value"
            return result
        delta, magnitude = _relative_change(current_value, baseline_value, rule.direction)
        result["delta_percent"] = delta
        if magnitude is None:
            result["status"] = "SKIP"
            result["reason"] = "unable to compute relative change"
            return result
        if magnitude >= rule.fail:
            result["status"] = "DEGRADATION"
        elif magnitude >= rule.warn:
            result["status"] = "WARNING"
        return result

    if rule.mode == "absolute":
        if rule.direction == "increase":
            if current_value >= rule.fail:
                result["status"] = "DEGRADATION"
            elif current_value >= rule.warn:
                result["status"] = "WARNING"
        else:
            if current_value <= rule.fail:
                result["status"] = "DEGRADATION"
            elif current_value <= rule.warn:
                result["status"] = "WARNING"
        if baseline_value is not None and baseline_value != 0:
            result["delta_percent"] = (current_value - baseline_value) / baseline_value * 100
        return result

    result["status"] = "SKIP"
    result["reason"] = "unsupported rule mode"
    return result


def analyze(current: Dict[str, Any], baseline: Dict[str, Any], rules: List[Rule]) -> Dict[str, Any]:
    results = [evaluate_rule(rule, current, baseline) for rule in rules]

    worst = "PASS"
    for res in results:
        status = res["status"]
        if status in STATUS_SEVERITY and STATUS_SEVERITY[status] > STATUS_SEVERITY[worst]:
            worst = status

    summary = {
        "PASS": sum(1 for res in results if res["status"] == "PASS"),
        "WARNING": sum(1 for res in results if res["status"] == "WARNING"),
        "DEGRADATION": sum(1 for res in results if res["status"] == "DEGRADATION"),
        "SKIP": sum(1 for res in results if res["status"] == "SKIP"),
    }

    return {
        "status": worst,
        "evaluated_at": utc_now(),
        "summary": summary,
        "results": results,
    }
