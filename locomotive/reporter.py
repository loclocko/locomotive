from __future__ import annotations

import csv
import html
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .utils import utc_now


def _format_value(value: Any, decimals: int = 2) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{decimals}f}"
    return str(value)


def _format_delta(value: Any) -> str:
    if value is None:
        return "-"
    try:
        v = float(value)
        arrow = "↑" if v > 0 else "↓" if v < 0 else "→"
        return f"{arrow} {abs(v):.1f}%"
    except (TypeError, ValueError):
        return "-"


def _format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}m {secs}s"


def _status_class(status: str) -> str:
    return {
        "PASS": "status-pass",
        "WARNING": "status-warning",
        "DEGRADATION": "status-fail",
        "SKIP": "status-skip",
    }.get(status, "status-unknown")


def _delta_class(value: Any, metric: str) -> str:
    """Return CSS class based on delta direction and metric type."""
    if value is None:
        return ""
    try:
        v = float(value)
        # For error_rate and response times, decrease is good
        # For rps, increase is good
        if "rps" in metric.lower():
            return "delta-good" if v > 0 else "delta-bad" if v < 0 else ""
        else:
            return "delta-good" if v < 0 else "delta-bad" if v > 0 else ""
    except (TypeError, ValueError):
        return ""


def load_stats_history(history_path: Path) -> List[Dict[str, Any]]:
    """Load locust_stats_history.csv and return as list of dicts."""
    if not history_path.exists():
        return []

    history = []
    with open(history_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Only include aggregated rows
            if row.get("Name") == "Aggregated" or row.get("Name") == "":
                history.append(row)
    return history


def load_endpoint_stats(stats_path: Path) -> List[Dict[str, Any]]:
    """Load locust_stats.csv and return endpoint statistics."""
    if not stats_path.exists():
        return []

    endpoints = []
    with open(stats_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Skip aggregated row for endpoint table
            if row.get("Name") and row.get("Name") != "Aggregated":
                endpoints.append(row)
    return endpoints


def _build_chart_data(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build chart data from stats history."""
    if not history:
        return {"labels": [], "rps": [], "users": [], "p50": [], "p95": [], "p99": [], "errors": []}

    labels = []
    rps_data = []
    users_data = []
    p50_data = []
    p95_data = []
    p99_data = []
    errors_data = []

    start_ts = None
    for row in history:
        try:
            ts = int(row.get("Timestamp", 0))
            if start_ts is None:
                start_ts = ts
            elapsed = ts - start_ts
            labels.append(elapsed)

            users_data.append(int(row.get("User Count", 0)))

            rps = row.get("Requests/s", "0")
            rps_data.append(float(rps) if rps and rps != "N/A" else 0)

            failures = row.get("Failures/s", "0")
            errors_data.append(float(failures) if failures and failures != "N/A" else 0)

            p50 = row.get("50%", "0")
            p50_data.append(float(p50) if p50 and p50 != "N/A" else None)

            p95 = row.get("95%", "0")
            p95_data.append(float(p95) if p95 and p95 != "N/A" else None)

            p99 = row.get("99%", "0")
            p99_data.append(float(p99) if p99 and p99 != "N/A" else None)
        except (ValueError, TypeError):
            continue

    return {
        "labels": labels,
        "rps": rps_data,
        "users": users_data,
        "p50": p50_data,
        "p95": p95_data,
        "p99": p99_data,
        "errors": errors_data,
    }


def _build_endpoint_rows(endpoints: List[Dict[str, Any]]) -> str:
    """Build HTML rows for endpoint statistics table."""
    rows = []
    for ep in endpoints:
        name = html.escape(f"{ep.get('Type', '')} {ep.get('Name', '')}".strip())
        requests = ep.get("Request Count", "0")
        failures = ep.get("Failure Count", "0")
        avg = ep.get("Average Response Time", "0")
        p50 = ep.get("50%", "0")
        p95 = ep.get("95%", "0")
        p99 = ep.get("99%", "0")
        max_rt = ep.get("Max Response Time", "0")
        rps = ep.get("Requests/s", "0")

        # Calculate error rate for this endpoint
        try:
            req_count = int(requests)
            fail_count = int(failures)
            error_rate = (fail_count / req_count * 100) if req_count > 0 else 0
        except (ValueError, ZeroDivisionError):
            error_rate = 0

        error_class = "error-cell" if error_rate > 0 else ""

        rows.append(
            f"<tr>"
            f"<td class='endpoint-name'>{name}</td>"
            f"<td class='num'>{requests}</td>"
            f"<td class='num {error_class}'>{failures}</td>"
            f"<td class='num'>{_format_value(float(avg) if avg else 0, 1)}</td>"
            f"<td class='num'>{_format_value(float(p50) if p50 else 0, 0)}</td>"
            f"<td class='num'>{_format_value(float(p95) if p95 else 0, 0)}</td>"
            f"<td class='num'>{_format_value(float(p99) if p99 else 0, 0)}</td>"
            f"<td class='num'>{_format_value(float(max_rt) if max_rt else 0, 0)}</td>"
            f"<td class='num'>{_format_value(float(rps) if rps else 0, 2)}</td>"
            f"</tr>"
        )
    return "\n".join(rows)


def render_report(
    run_meta: Dict[str, Any],
    current_metrics: Dict[str, Any],
    baseline_metrics: Optional[Dict[str, Any]],
    analysis: Optional[Dict[str, Any]],
    title: str,
    stats_history: Optional[List[Dict[str, Any]]] = None,
    endpoint_stats: Optional[List[Dict[str, Any]]] = None,
) -> str:
    status = analysis.get("status") if analysis else "PASS"
    generated_at = utc_now()

    # Build analysis rows
    analysis_rows: List[str] = []
    if analysis and analysis.get("results"):
        for res in analysis["results"]:
            status_text = str(res.get("status"))
            delta = res.get("delta_percent")
            metric = str(res.get("metric", ""))
            delta_cls = _delta_class(delta, metric)
            analysis_rows.append(
                "<tr>"
                f"<td>{html.escape(metric)}</td>"
                f"<td class='num'>{_format_value(res.get('baseline'))}</td>"
                f"<td class='num'>{_format_value(res.get('current'))}</td>"
                f"<td class='num {delta_cls}'>{_format_delta(delta)}</td>"
                f"<td class='{_status_class(status_text)}'>{html.escape(status_text)}</td>"
                "</tr>"
            )
    else:
        for key, value in current_metrics.items():
            analysis_rows.append(
                "<tr>"
                f"<td>{html.escape(str(key))}</td>"
                "<td class='num'>-</td>"
                f"<td class='num'>{_format_value(value)}</td>"
                "<td class='num'>-</td>"
                "<td class='status-skip'>SKIP</td>"
                "</tr>"
            )

    # Build summary HTML
    summary_html = ""
    if analysis and analysis.get("summary"):
        summary = analysis["summary"]
        summary_html = f"""
        <div class="status-summary">
            <span class="status-badge pass">{summary.get('PASS', 0)} PASS</span>
            <span class="status-badge warning">{summary.get('WARNING', 0)} WARN</span>
            <span class="status-badge fail">{summary.get('DEGRADATION', 0)} FAIL</span>
            <span class="status-badge skip">{summary.get('SKIP', 0)} SKIP</span>
        </div>
        """
    elif not baseline_metrics:
        summary_html = """
        <div class="info-message">
            <strong>First run detected:</strong> No baseline available for comparison.
            This run will be used as baseline for future comparisons.
        </div>
        """

    # Build chart data
    chart_data = _build_chart_data(stats_history or [])
    chart_data_json = json.dumps(chart_data)

    # Build endpoint rows
    endpoint_rows = _build_endpoint_rows(endpoint_stats or [])
    has_endpoints = bool(endpoint_stats)

    # Calculate test duration
    run_time = run_meta.get("run_time", 60)
    duration_str = _format_duration(run_time) if isinstance(run_time, (int, float)) else str(run_time)

    # Get KPI values
    rps = current_metrics.get("rps", 0)
    avg_ms = current_metrics.get("avg_ms", 0)
    p95_ms = current_metrics.get("p95_ms", 0)
    p99_ms = current_metrics.get("p99_ms", 0)
    error_rate = current_metrics.get("error_rate", 0)
    total_requests = current_metrics.get("requests", 0)
    total_failures = current_metrics.get("failures", 0)

    # Delta values for KPIs
    rps_delta = ""
    avg_delta = ""
    p95_delta = ""
    error_delta = ""

    if baseline_metrics:
        if baseline_metrics.get("rps"):
            d = (rps - baseline_metrics["rps"]) / baseline_metrics["rps"] * 100
            rps_delta = f'<span class="{_delta_class(d, "rps")}">{_format_delta(d)}</span>'
        if baseline_metrics.get("avg_ms"):
            d = (avg_ms - baseline_metrics["avg_ms"]) / baseline_metrics["avg_ms"] * 100
            avg_delta = f'<span class="{_delta_class(d, "avg_ms")}">{_format_delta(d)}</span>'
        if baseline_metrics.get("p95_ms"):
            d = (p95_ms - baseline_metrics["p95_ms"]) / baseline_metrics["p95_ms"] * 100
            p95_delta = f'<span class="{_delta_class(d, "p95_ms")}">{_format_delta(d)}</span>'
        if baseline_metrics.get("error_rate"):
            d = (error_rate - baseline_metrics["error_rate"]) / baseline_metrics["error_rate"] * 100 if baseline_metrics["error_rate"] > 0 else 0
            error_delta = f'<span class="{_delta_class(d, "error_rate")}">{_format_delta(d)}</span>'

    title_safe = html.escape(title)
    run_id = html.escape(str(run_meta.get("run_id", "-"))[:12])
    baseline_id = html.escape(str(run_meta.get("baseline_id") or "-")[:12])

    has_charts = bool(stats_history and len(stats_history) > 2)

    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title_safe}</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    :root {{
      --pass: #059669;
      --pass-bg: #d1fae5;
      --warn: #d97706;
      --warn-bg: #fef3c7;
      --fail: #dc2626;
      --fail-bg: #fee2e2;
      --skip: #6b7280;
      --skip-bg: #f3f4f6;
      --bg: #f8fafc;
      --card: #ffffff;
      --line: #e2e8f0;
      --text: #1e293b;
      --text-muted: #64748b;
      --primary: #3b82f6;
      --primary-light: #dbeafe;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      margin: 0;
      padding: 24px;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
    }}
    .container {{ max-width: 1400px; margin: 0 auto; }}

    /* Header */
    .header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 24px;
      flex-wrap: wrap;
      gap: 16px;
    }}
    .header-left {{ display: flex; align-items: center; gap: 16px; }}
    .title {{ font-size: 28px; font-weight: 700; margin: 0; }}
    .status-badge-large {{
      padding: 8px 20px;
      border-radius: 8px;
      font-weight: 700;
      font-size: 14px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .status-badge-large.pass {{ background: var(--pass-bg); color: var(--pass); }}
    .status-badge-large.warning {{ background: var(--warn-bg); color: var(--warn); }}
    .status-badge-large.fail {{ background: var(--fail-bg); color: var(--fail); }}
    .meta {{ color: var(--text-muted); font-size: 13px; }}
    .meta-ids {{ font-family: monospace; font-size: 12px; }}

    /* Cards */
    .card {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 20px;
      margin-bottom: 20px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }}
    .card-title {{
      font-size: 14px;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 16px;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .card-title::before {{
      content: "";
      width: 4px;
      height: 16px;
      background: var(--primary);
      border-radius: 2px;
    }}

    /* KPI Grid */
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }}
    .kpi-card {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 20px;
      text-align: center;
    }}
    .kpi-value {{
      font-size: 32px;
      font-weight: 700;
      color: var(--text);
      line-height: 1.2;
    }}
    .kpi-label {{
      font-size: 12px;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-top: 4px;
    }}
    .kpi-delta {{
      font-size: 13px;
      margin-top: 8px;
    }}
    .delta-good {{ color: var(--pass); }}
    .delta-bad {{ color: var(--fail); }}

    /* Charts */
    .charts-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
      gap: 20px;
      margin-bottom: 24px;
    }}
    .chart-container {{
      position: relative;
      height: 280px;
    }}

    /* Tables */
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    th, td {{
      padding: 12px 16px;
      border-bottom: 1px solid var(--line);
      text-align: left;
    }}
    th {{
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      background: var(--bg);
    }}
    td.num {{ text-align: right; font-family: monospace; }}
    tr:hover {{ background: var(--bg); }}
    .endpoint-name {{ font-weight: 500; }}
    .error-cell {{ color: var(--fail); font-weight: 600; }}

    /* Status classes */
    .status-pass {{ color: var(--pass); font-weight: 600; }}
    .status-warning {{ color: var(--warn); font-weight: 600; }}
    .status-fail {{ color: var(--fail); font-weight: 600; }}
    .status-skip {{ color: var(--skip); }}

    /* Status summary */
    .status-summary {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
    }}
    .status-badge {{
      padding: 4px 12px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
    }}
    .status-badge.pass {{ background: var(--pass-bg); color: var(--pass); }}
    .status-badge.warning {{ background: var(--warn-bg); color: var(--warn); }}
    .status-badge.fail {{ background: var(--fail-bg); color: var(--fail); }}
    .status-badge.skip {{ background: var(--skip-bg); color: var(--skip); }}

    /* Info message */
    .info-message {{
      background: var(--warn-bg);
      border: 1px solid #fbbf24;
      border-radius: 8px;
      padding: 12px 16px;
      font-size: 13px;
      color: #92400e;
    }}

    /* Footer */
    .footer {{
      text-align: center;
      padding: 24px;
      color: var(--text-muted);
      font-size: 12px;
    }}
    .footer a {{ color: var(--primary); text-decoration: none; }}
    .footer a:hover {{ text-decoration: underline; }}

    /* Two columns layout */
    .two-cols {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
    }}
    @media (max-width: 900px) {{
      .two-cols {{ grid-template-columns: 1fr; }}
      .charts-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <!-- Header -->
    <div class="header">
      <div>
        <h1 class="title">{title_safe}</h1>
        <div class="meta">
          Generated at {generated_at}<br>
          <span class="meta-ids">Run: {run_id} | Baseline: {baseline_id}</span>
        </div>
      </div>
      <div class="status-badge-large {_status_class(status).replace('status-', '')}">{html.escape(status)}</div>
    </div>

    <!-- KPI Cards -->
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-value">{_format_value(rps, 1)}</div>
        <div class="kpi-label">Requests/sec</div>
        <div class="kpi-delta">{rps_delta}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-value">{_format_value(avg_ms, 0)}<span style="font-size:16px">ms</span></div>
        <div class="kpi-label">Avg Response</div>
        <div class="kpi-delta">{avg_delta}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-value">{_format_value(p95_ms, 0)}<span style="font-size:16px">ms</span></div>
        <div class="kpi-label">P95 Response</div>
        <div class="kpi-delta">{p95_delta}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-value">{_format_value(error_rate, 2)}<span style="font-size:16px">%</span></div>
        <div class="kpi-label">Error Rate</div>
        <div class="kpi-delta">{error_delta}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-value">{total_requests:,}</div>
        <div class="kpi-label">Total Requests</div>
        <div class="kpi-delta">{total_failures} failures</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-value">{duration_str}</div>
        <div class="kpi-label">Duration</div>
      </div>
    </div>

    {'<!-- Charts -->' if has_charts else '<!-- No chart data available -->'}
    {f'''
    <div class="charts-grid">
      <div class="card">
        <div class="card-title">Throughput & Users Over Time</div>
        <div class="chart-container">
          <canvas id="throughputChart"></canvas>
        </div>
      </div>
      <div class="card">
        <div class="card-title">Response Time Percentiles</div>
        <div class="chart-container">
          <canvas id="responseChart"></canvas>
        </div>
      </div>
    </div>
    ''' if has_charts else ''}

    <!-- Analysis & Endpoints -->
    <div class="two-cols">
      <div class="card">
        <div class="card-title">Regression Analysis</div>
        {summary_html}
        <table>
          <thead>
            <tr>
              <th>Metric</th>
              <th>Baseline</th>
              <th>Current</th>
              <th>Delta</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {"".join(analysis_rows)}
          </tbody>
        </table>
      </div>

      {'<div class="card"><div class="card-title">Endpoint Statistics</div><table><thead><tr><th>Endpoint</th><th>Requests</th><th>Failures</th><th>Avg</th><th>P50</th><th>P95</th><th>P99</th><th>Max</th><th>RPS</th></tr></thead><tbody>' + endpoint_rows + '</tbody></table></div>' if has_endpoints else ''}
    </div>

    <!-- Footer -->
    <div class="footer">
      Generated by <a href="https://github.com/loclocko/locomotive">Locomotive</a> - CI/CD Load Testing
    </div>
  </div>

  {f'''
  <script>
    const chartData = {chart_data_json};

    // Throughput & Users Chart
    new Chart(document.getElementById('throughputChart'), {{
      type: 'line',
      data: {{
        labels: chartData.labels.map(t => t + 's'),
        datasets: [
          {{
            label: 'RPS',
            data: chartData.rps,
            borderColor: '#3b82f6',
            backgroundColor: 'rgba(59, 130, 246, 0.1)',
            fill: true,
            tension: 0.3,
            yAxisID: 'y'
          }},
          {{
            label: 'Users',
            data: chartData.users,
            borderColor: '#8b5cf6',
            backgroundColor: 'transparent',
            borderDash: [5, 5],
            tension: 0.3,
            yAxisID: 'y1'
          }},
          {{
            label: 'Errors/s',
            data: chartData.errors,
            borderColor: '#ef4444',
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            fill: true,
            tension: 0.3,
            yAxisID: 'y'
          }}
        ]
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        interaction: {{ mode: 'index', intersect: false }},
        plugins: {{
          legend: {{ position: 'top' }}
        }},
        scales: {{
          x: {{ title: {{ display: true, text: 'Time' }} }},
          y: {{
            type: 'linear',
            position: 'left',
            title: {{ display: true, text: 'Requests/s' }},
            min: 0
          }},
          y1: {{
            type: 'linear',
            position: 'right',
            title: {{ display: true, text: 'Users' }},
            grid: {{ drawOnChartArea: false }},
            min: 0
          }}
        }}
      }}
    }});

    // Response Time Chart
    new Chart(document.getElementById('responseChart'), {{
      type: 'line',
      data: {{
        labels: chartData.labels.map(t => t + 's'),
        datasets: [
          {{
            label: 'P50',
            data: chartData.p50,
            borderColor: '#10b981',
            backgroundColor: 'transparent',
            tension: 0.3
          }},
          {{
            label: 'P95',
            data: chartData.p95,
            borderColor: '#f59e0b',
            backgroundColor: 'transparent',
            tension: 0.3
          }},
          {{
            label: 'P99',
            data: chartData.p99,
            borderColor: '#ef4444',
            backgroundColor: 'transparent',
            tension: 0.3
          }}
        ]
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        interaction: {{ mode: 'index', intersect: false }},
        plugins: {{
          legend: {{ position: 'top' }}
        }},
        scales: {{
          x: {{ title: {{ display: true, text: 'Time' }} }},
          y: {{
            title: {{ display: true, text: 'Response Time (ms)' }},
            min: 0
          }}
        }}
      }}
    }});
  </script>
  ''' if has_charts else ''}
</body>
</html>'''
