from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .analyzer import analyze as analyze_metrics
from .analyzer import load_rules, merge_results
from .config import load_config
from .gate import evaluate_gate, summarize_history
from .launcher import LocustLauncher, find_stats_history_csv, parse_locust_stats_history
from .reporter import render_report
from .scenario import generate_locustfile
from .storage import Storage
from .template import generate_template, generate_github_workflow


DEFAULT_CONFIG = "loconfig.json"


def _get_section(config: Dict[str, Any], name: str) -> Dict[str, Any]:
    value = config.get(name)
    return value if isinstance(value, dict) else {}


def _normalize_mode(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    if text in {"resilience", "acceptance"}:
        return text
    return ""


def _resolve_gate_config(analysis_cfg: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
    gate_cfg = _get_section(analysis_cfg, "gate")
    mode = _normalize_mode(analysis_cfg.get("mode") or gate_cfg.get("mode"))
    thresholds = gate_cfg.get("thresholds")
    has_thresholds = isinstance(thresholds, dict) and bool(thresholds)
    if not mode and has_thresholds:
        mode = "resilience"
    if mode == "resilience" and not has_thresholds:
        mode = ""
    return mode, gate_cfg


def _load_history_summary(storage: Storage, run_id: str, warmup_seconds: Optional[int]) -> Optional[Dict[str, float]]:
    if not warmup_seconds:
        return None
    history_path = find_stats_history_csv(storage.raw_dir(run_id))
    if not history_path:
        return None
    history = parse_locust_stats_history(history_path)
    return summarize_history(history, warmup_seconds)


def _parse_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(value)]


def _parse_int(value: Any, name: str) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an integer")


def _default_run_id() -> str:
    for key in ["GITHUB_SHA", "GITHUB_RUN_ID", "CI_PIPELINE_ID"]:
        value = os.environ.get(key)
        if value:
            return value
    return f"run-{int(time.time())}"


def _collect_ci_meta() -> Dict[str, Any]:
    keys = [
        "GITHUB_SHA",
        "GITHUB_REF",
        "GITHUB_RUN_ID",
        "GITHUB_RUN_NUMBER",
        "GITHUB_REPOSITORY",
        "GITHUB_WORKFLOW",
        "GITHUB_ACTIONS",
    ]
    meta = {key.lower(): os.environ.get(key) for key in keys if os.environ.get(key)}
    return meta


def _load_rules_from_sources(rules_path: Optional[str], inline_rules: Optional[List[Dict[str, Any]]]) -> List[Any]:
    if rules_path:
        data = json.loads(Path(rules_path).read_text(encoding="utf-8"))
        return load_rules(data)
    if inline_rules:
        return load_rules({"rules": inline_rules})
    return []


def _build_storage(args: argparse.Namespace, config: Dict[str, Any]) -> Storage:
    artifacts = _get_section(config, "artifacts")
    storage_root = args.storage or artifacts.get("storage") or "artifacts"
    return Storage.from_root(storage_root)


def _build_run_id(args: argparse.Namespace, config: Dict[str, Any]) -> str:
    artifacts = _get_section(config, "artifacts")
    return args.run_id or artifacts.get("run_id") or _default_run_id()


def _build_locust_config(args: argparse.Namespace, config: Dict[str, Any]) -> Dict[str, Any]:
    # Support both "locust" and "load" section names
    locust_cfg = _get_section(config, "locust")
    if not locust_cfg:
        locust_cfg = _get_section(config, "load")
    
    scenario_cfg = _get_section(config, "scenario")
    scenario_headers = scenario_cfg.get("headers") if isinstance(scenario_cfg.get("headers"), dict) else {}
    locust_headers = locust_cfg.get("headers") if isinstance(locust_cfg.get("headers"), dict) else {}
    headers = {**locust_headers, **scenario_headers}
    
    merged: Dict[str, Any] = {
        "locustfile": args.locustfile or locust_cfg.get("locustfile"),
        "host": args.host or locust_cfg.get("host"),
        "users": _parse_int(args.users, "users") if args.users is not None else _parse_int(locust_cfg.get("users"), "users"),
        "spawn_rate": _parse_int(args.spawn_rate, "spawn_rate") if args.spawn_rate is not None else _parse_int(locust_cfg.get("spawn_rate"), "spawn_rate"),
        "run_time": args.run_time or locust_cfg.get("run_time"),
        "tags": _parse_list(args.tags) if args.tags is not None else _parse_list(locust_cfg.get("tags")),
        "exclude_tags": _parse_list(args.exclude_tags) if args.exclude_tags is not None else _parse_list(locust_cfg.get("exclude_tags")),
        "stop_timeout": _parse_int(args.stop_timeout, "stop_timeout") if args.stop_timeout is not None else _parse_int(locust_cfg.get("stop_timeout"), "stop_timeout"),
        "extra_args": _parse_list(args.extra_arg) if args.extra_arg is not None else _parse_list(locust_cfg.get("extra_args")),
        "locust_cmd": args.locust_cmd or locust_cfg.get("locust_cmd"),
        "headers": headers,
        "meta": {"ci": _collect_ci_meta()},
    }
    return merged


def _maybe_generate_locustfile(
    storage: Storage,
    run_id: str,
    locust_config: Dict[str, Any],
    config: Dict[str, Any],
) -> None:
    """Generate locustfile from scenario config if no locustfile is specified."""
    if locust_config.get("locustfile"):
        return
    
    scenario = _get_section(config, "scenario")
    if not scenario:
        raise ValueError("Either 'locustfile' in load config or 'scenario' section is required")
    
    if not scenario.get("requests"):
        raise ValueError("scenario.requests must be a non-empty list")
    
    output_dir = storage.run_dir(run_id) / "generated"
    locustfile_path = generate_locustfile(scenario, locust_config, output_dir)
    locust_config["locustfile"] = str(locustfile_path)


def _run(storage: Storage, run_id: str, locust_config: Dict[str, Any]) -> Dict[str, Any]:
    launcher = LocustLauncher(storage, run_id, locust_config)
    return launcher.run()


def _analyze(
    storage: Storage,
    run_id: str,
    baseline_id: str,
    rules_path: Optional[str],
    inline_rules: Optional[List[Dict[str, Any]]],
    save: bool = True,
) -> Dict[str, Any]:
    current_metrics = storage.load_json(storage.metrics_path(run_id))
    baseline_metrics = {}
    baseline_path = storage.metrics_path(baseline_id)
    if baseline_path.exists():
        baseline_metrics = storage.load_json(baseline_path)
    rules = _load_rules_from_sources(rules_path, inline_rules)
    analysis = analyze_metrics(current_metrics, baseline_metrics, rules)
    analysis["run_id"] = run_id
    analysis["baseline_id"] = baseline_id
    if save:
        storage.save_json(storage.analysis_path(run_id), analysis)
    return analysis


def _report(
    storage: Storage,
    run_id: str,
    baseline_id: Optional[str],
    title: str,
    output_path: Optional[str],
) -> str:
    run_meta_path = storage.run_meta_path(run_id)
    if run_meta_path.exists():
        run_meta = storage.load_json(run_meta_path)
    else:
        run_meta = {"run_id": run_id}
    if baseline_id:
        run_meta["baseline_id"] = baseline_id

    current_metrics = {}
    metrics_path = storage.metrics_path(run_id)
    if metrics_path.exists():
        current_metrics = storage.load_json(metrics_path)

    baseline_metrics = None
    if baseline_id:
        baseline_path = storage.metrics_path(baseline_id)
        if baseline_path.exists():
            baseline_metrics = storage.load_json(baseline_path)

    analysis = None
    analysis_path = storage.analysis_path(run_id)
    if analysis_path.exists():
        analysis = storage.load_json(analysis_path)

    html = render_report(run_meta, current_metrics, baseline_metrics, analysis, title)

    if output_path:
        output = Path(output_path)
    else:
        output = storage.report_path(run_id)
    storage.save_text(output, html)
    return str(output)


def _exit_code_for_status(status: str, fail_on: str) -> int:
    if fail_on == "WARNING" and status in {"WARNING", "DEGRADATION"}:
        return 1
    if fail_on == "DEGRADATION" and status == "DEGRADATION":
        return 1
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    """Initialize a new loconfig configuration."""
    output_path = Path(args.output)
    openapi_path = Path(args.openapi) if args.openapi else None
    host = args.host or "http://localhost:8000"
    
    if output_path.exists() and not args.force:
        print(f"Error: {output_path} already exists. Use --force to overwrite.")
        return 1
    
    generate_template(output_path, host=host, openapi_path=openapi_path)
    print(f"Created: {output_path}")
    
    # Optionally generate GitHub workflow
    if args.github_workflow:
        workflow_path = Path(".github/workflows/loadtest.yml")
        if workflow_path.exists() and not args.force:
            print(f"Skipped: {workflow_path} already exists")
        else:
            generate_github_workflow(workflow_path, config_name=output_path.name)
            print(f"Created: {workflow_path}")
    
    print()
    print("Next steps:")
    print(f"  1. Edit {output_path} to configure your endpoints")
    print("  2. Run: loco ci --config", output_path)
    
    return 0


def cmd_run(args: argparse.Namespace, config: Dict[str, Any]) -> int:
    storage = _build_storage(args, config)
    run_id = _build_run_id(args, config)
    locust_config = _build_locust_config(args, config)
    
    _maybe_generate_locustfile(storage, run_id, locust_config, config)
    result = _run(storage, run_id, locust_config)

    if args.set_baseline and result.get("returncode") == 0:
        storage.set_baseline(run_id)

    return int(result.get("returncode") or 0)


def cmd_analyze(args: argparse.Namespace, config: Dict[str, Any]) -> int:
    storage = _build_storage(args, config)
    run_id = _build_run_id(args, config)

    analysis_cfg = _get_section(config, "analysis")
    mode, gate_cfg = _resolve_gate_config(analysis_cfg)
    baseline_id = args.baseline or analysis_cfg.get("baseline") or storage.get_baseline()
    if not baseline_id and not mode:
        raise ValueError("baseline run id is required")

    rules_path = args.rules or analysis_cfg.get("rules_file")
    inline_rules = analysis_cfg.get("rules")

    result_sets: List[List[Dict[str, Any]]] = []
    baseline_results = None
    if baseline_id:
        baseline_results = _analyze(storage, run_id, baseline_id, rules_path, inline_rules, save=False)
        result_sets.append(baseline_results.get("results") or [])

    gate_eval = None
    if mode:
        current_metrics = storage.load_json(storage.metrics_path(run_id))
        warmup_seconds = gate_cfg.get("warmup_seconds")
        history_summary = _load_history_summary(storage, run_id, _parse_int(warmup_seconds, "warmup_seconds") if warmup_seconds is not None else None)
        gate_eval = evaluate_gate(current_metrics, gate_cfg, mode, history_summary)
        if gate_eval:
            result_sets.append(gate_eval.get("results") or [])

    if result_sets:
        combined = merge_results(result_sets)
        combined["run_id"] = run_id
        if baseline_id:
            combined["baseline_id"] = baseline_id
        if gate_eval:
            combined["gate"] = gate_eval.get("gate")
        storage.save_json(storage.analysis_path(run_id), combined)

        fail_on = args.fail_on or analysis_cfg.get("fail_on") or "DEGRADATION"
        return _exit_code_for_status(combined.get("status"), fail_on)

    return 0


def cmd_report(args: argparse.Namespace, config: Dict[str, Any]) -> int:
    storage = _build_storage(args, config)
    run_id = _build_run_id(args, config)

    analysis_cfg = _get_section(config, "analysis")
    report_cfg = _get_section(config, "report")
    baseline_id = args.baseline or analysis_cfg.get("baseline") or storage.get_baseline()
    title = args.title or report_cfg.get("title") or "CI Load Test Report"
    output_path = args.output or report_cfg.get("output")

    _report(storage, run_id, baseline_id, title, output_path)
    return 0


def cmd_ci(args: argparse.Namespace, config: Dict[str, Any]) -> int:
    """Run full CI pipeline: run tests, analyze, generate report."""
    storage = _build_storage(args, config)
    run_id = _build_run_id(args, config)
    locust_config = _build_locust_config(args, config)

    _maybe_generate_locustfile(storage, run_id, locust_config, config)
    run_result = _run(storage, run_id, locust_config)

    if args.set_baseline and run_result.get("returncode") == 0:
        storage.set_baseline(run_id)

    analysis_cfg = _get_section(config, "analysis")
    report_cfg = _get_section(config, "report")
    mode, gate_cfg = _resolve_gate_config(analysis_cfg)
    baseline_id = args.baseline or analysis_cfg.get("baseline") or storage.get_baseline()

    metrics_path = storage.metrics_path(run_id)
    metrics_exist = metrics_path.exists()
    analysis = None
    result_sets: List[List[Dict[str, Any]]] = []
    baseline_results = None

    if baseline_id and metrics_exist:
        rules_path = args.rules or analysis_cfg.get("rules_file")
        inline_rules = analysis_cfg.get("rules")
        baseline_results = _analyze(storage, run_id, baseline_id, rules_path, inline_rules, save=False)
        result_sets.append(baseline_results.get("results") or [])
    else:
        baseline_id = None

    gate_eval = None
    if mode and metrics_exist:
        current_metrics = storage.load_json(metrics_path)
        warmup_seconds = gate_cfg.get("warmup_seconds")
        history_summary = _load_history_summary(storage, run_id, _parse_int(warmup_seconds, "warmup_seconds") if warmup_seconds is not None else None)
        gate_eval = evaluate_gate(current_metrics, gate_cfg, mode, history_summary)
        if gate_eval:
            result_sets.append(gate_eval.get("results") or [])

    if result_sets:
        combined = merge_results(result_sets)
        combined["run_id"] = run_id
        if baseline_id:
            combined["baseline_id"] = baseline_id
        if gate_eval:
            combined["gate"] = gate_eval.get("gate")
        storage.save_json(storage.analysis_path(run_id), combined)
        analysis = combined

    title = args.title or report_cfg.get("title") or "CI Load Test Report"
    output_path = args.output or report_cfg.get("output")
    _report(storage, run_id, baseline_id, title, output_path)

    locust_code = int(run_result.get("returncode") or 0)
    if not metrics_exist:
        return locust_code or 1
    if locust_code != 0 and not mode:
        return locust_code

    if analysis:
        fail_on = args.fail_on or analysis_cfg.get("fail_on") or "DEGRADATION"
        return _exit_code_for_status(analysis.get("status"), fail_on)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="loco",
        description="Locomotive - CI/CD load testing runner and regression analyzer for Locust",
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Path to config JSON/YAML")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # init command
    init_parser = subparsers.add_parser("init", help="Initialize a new loconfig configuration")
    init_parser.add_argument("--output", "-o", default="loconfig.json", help="Output config file path")
    init_parser.add_argument("--openapi", help="Path to OpenAPI spec to generate request templates")
    init_parser.add_argument("--host", help="Default host URL")
    init_parser.add_argument("--github-workflow", action="store_true", help="Also generate GitHub Actions workflow")
    init_parser.add_argument("--force", "-f", action="store_true", help="Overwrite existing files")

    # run command
    run_parser = subparsers.add_parser("run", help="Run locust and store metrics")
    _add_run_args(run_parser)

    # analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Analyze metrics vs baseline")
    _add_analyze_args(analyze_parser)

    # report command
    report_parser = subparsers.add_parser("report", help="Generate HTML report")
    _add_report_args(report_parser)

    # ci command (all-in-one)
    ci_parser = subparsers.add_parser("ci", help="Run, analyze, and report (full CI pipeline)")
    _add_run_args(ci_parser)
    _add_analyze_args(ci_parser)
    _add_report_args(ci_parser)

    return parser


def _add_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--locustfile", help="Path to locustfile (optional if scenario is in config)")
    parser.add_argument("--host", help="Target host URL")
    parser.add_argument("--users", help="Number of concurrent users")
    parser.add_argument("--spawn-rate", help="Users spawned per second")
    parser.add_argument("--run-time", help="Test duration (e.g., 1m, 30s)")
    parser.add_argument("--tags", help="Only run tasks with these tags (comma-separated)")
    parser.add_argument("--exclude-tags", help="Exclude tasks with these tags")
    parser.add_argument("--stop-timeout", help="Timeout for stopping users")
    parser.add_argument("--extra-arg", action="append", help="Extra arguments to pass to locust")
    parser.add_argument("--locust-cmd", help="Custom locust command")
    parser.add_argument("--storage", help="Artifacts storage directory")
    parser.add_argument("--run-id", help="Unique run identifier")
    parser.add_argument("--set-baseline", action="store_true", help="Set this run as baseline")


def _add_analyze_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--baseline", help="Baseline run ID to compare against")
    parser.add_argument("--rules", help="Path to rules JSON file")
    parser.add_argument("--fail-on", choices=["WARNING", "DEGRADATION"], help="Exit code 1 threshold")


def _add_report_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--title", help="Report title")
    parser.add_argument("--output", help="Report output path")


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    
    # init command doesn't need config file
    if args.command == "init":
        return cmd_init(args)
    
    config = load_config(args.config)

    if args.command == "run":
        return cmd_run(args, config)
    if args.command == "analyze":
        return cmd_analyze(args, config)
    if args.command == "report":
        return cmd_report(args, config)
    if args.command == "ci":
        return cmd_ci(args, config)

    parser.print_help()
    return 1
