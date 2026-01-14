from __future__ import annotations

import csv
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from .storage import Storage
from .utils import utc_now


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip()
        if text == "" or text.upper() == "N/A":
            return None
        return float(text)
    except ValueError:
        return None


def _safe_int(value: Any) -> Optional[int]:
    num = _safe_float(value)
    if num is None:
        return None
    return int(num)


def _find_stats_csv(raw_dir: Path) -> Optional[Path]:
    preferred = raw_dir / "locust_stats.csv"
    if preferred.exists():
        return preferred
    matches = sorted(raw_dir.glob("*_stats.csv"))
    if matches:
        return matches[0]
    return None


def _select_aggregate_row(rows: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
    for row in rows:
        name = (row.get("Name") or "").strip().lower()
        typ = (row.get("Type") or "").strip().lower()
        if name == "aggregated" or typ == "aggregated":
            return row
    for row in rows:
        name = (row.get("Name") or "").strip().lower()
        if name in {"total", "overall"}:
            return row
    if rows:
        return rows[0]
    return None


def parse_locust_stats(path: Path) -> Dict[str, Any]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    row = _select_aggregate_row(rows)
    if not row:
        return {}

    norm_map = {_normalize_key(key): key for key in row.keys()}

    def fetch(*candidates: str) -> Optional[str]:
        for cand in candidates:
            key = norm_map.get(_normalize_key(cand))
            if key is not None:
                return row.get(key)
        return None

    requests = _safe_int(fetch("Requests", "Request Count"))
    failures = _safe_int(fetch("Failures", "Failure Count"))
    error_rate = _safe_float(fetch("Failure%", "Failure %"))
    if error_rate is None and requests:
        error_rate = (failures or 0) / requests * 100

    metrics: Dict[str, Any] = {
        "requests": requests,
        "failures": failures,
        "error_rate": error_rate,
        "avg_ms": _safe_float(fetch("Average Response Time", "Average Response Time (ms)")),
        "median_ms": _safe_float(fetch("Median Response Time", "Median Response Time (ms)")),
        "min_ms": _safe_float(fetch("Min Response Time", "Min Response Time (ms)")),
        "max_ms": _safe_float(fetch("Max Response Time", "Max Response Time (ms)")),
        "p95_ms": _safe_float(fetch("95%", "95% Response Time")),
        "p99_ms": _safe_float(fetch("99%", "99% Response Time")),
        "rps": _safe_float(fetch("Requests/s", "Requests/s")),
    }

    return metrics


class LocustLauncher:
    def __init__(self, storage: Storage, run_id: str, config: Dict[str, Any]) -> None:
        self.storage = storage
        self.run_id = run_id
        self.config = config

    def run(self) -> Dict[str, Any]:
        self.storage.ensure_run(self.run_id)
        raw_dir = self.storage.raw_dir(self.run_id)
        csv_prefix = raw_dir / "locust"

        locust_cmd = self.config.get("locust_cmd") or "locust"
        locustfile = self.config.get("locustfile")
        host = self.config.get("host")
        users = self.config.get("users")
        spawn_rate = self.config.get("spawn_rate")
        run_time = self.config.get("run_time")
        tags = self.config.get("tags") or []
        exclude_tags = self.config.get("exclude_tags") or []
        stop_timeout = self.config.get("stop_timeout")
        extra_args = self.config.get("extra_args") or []

        if not locustfile:
            raise ValueError("locustfile is required")
        if users is None:
            raise ValueError("users is required")
        if spawn_rate is None:
            raise ValueError("spawn_rate is required")
        if not run_time:
            raise ValueError("run_time is required")

        cmd: List[str] = [
            locust_cmd,
            "-f",
            str(locustfile),
            "--headless",
            "-u",
            str(users),
            "-r",
            str(spawn_rate),
            "--run-time",
            str(run_time),
            "--csv",
            str(csv_prefix),
        ]

        if host:
            cmd += ["--host", str(host)]
        if tags:
            cmd += ["--tags", ",".join(tags)]
        if exclude_tags:
            cmd += ["--exclude-tags", ",".join(exclude_tags)]
        if stop_timeout:
            cmd += ["--stop-timeout", str(stop_timeout)]
        if extra_args:
            cmd += [str(arg) for arg in extra_args]

        started_at = utc_now()
        result = subprocess.run(cmd)
        finished_at = utc_now()

        stats_path = _find_stats_csv(raw_dir)
        metrics: Dict[str, Any] = {}
        if stats_path:
            metrics = parse_locust_stats(stats_path)
            self.storage.save_json(self.storage.metrics_path(self.run_id), metrics)

        run_meta = {
            "run_id": self.run_id,
            "started_at": started_at,
            "finished_at": finished_at,
            "returncode": result.returncode,
            "command": cmd,
            "locustfile": str(locustfile),
            "host": host,
            "users": users,
            "spawn_rate": spawn_rate,
            "run_time": run_time,
        }
        extra_meta = self.config.get("meta") or {}
        if extra_meta:
            run_meta["meta"] = extra_meta
        self.storage.save_json(self.storage.run_meta_path(self.run_id), run_meta)

        return {
            "returncode": result.returncode,
            "metrics": metrics,
            "stats_path": str(stats_path) if stats_path else None,
        }
