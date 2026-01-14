from __future__ import annotations

import html
from typing import Any, Dict, List, Optional

from .utils import utc_now


def _format_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _format_delta(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return "-"


def _status_class(status: str) -> str:
    return {
        "PASS": "status-pass",
        "WARNING": "status-warning",
        "DEGRADATION": "status-fail",
        "SKIP": "status-skip",
    }.get(status, "status-unknown")


def render_report(
    run_meta: Dict[str, Any],
    current_metrics: Dict[str, Any],
    baseline_metrics: Optional[Dict[str, Any]],
    analysis: Optional[Dict[str, Any]],
    title: str,
) -> str:
    status = analysis.get("status") if analysis else "PASS"
    generated_at = utc_now()

    rows: List[str] = []
    if analysis and analysis.get("results"):
        for res in analysis["results"]:
            status_text = str(res.get("status"))
            delta = res.get("delta_percent")
            rows.append(
                "<tr>"
                f"<td>{html.escape(str(res.get('metric')))}</td>"
                f"<td>{_format_value(res.get('baseline'))}</td>"
                f"<td>{_format_value(res.get('current'))}</td>"
                f"<td>{_format_delta(delta)}</td>"
                f"<td class=\"{_status_class(status_text)}\">{html.escape(status_text)}</td>"
                "</tr>"
            )
    else:
        for key, value in current_metrics.items():
            rows.append(
                "<tr>"
                f"<td>{html.escape(str(key))}</td>"
                "<td>-</td>"
                f"<td>{_format_value(value)}</td>"
                "<td>-</td>"
                "<td class=\"status-skip\">SKIP</td>"
                "</tr>"
            )

    summary_html = ""
    if analysis and analysis.get("summary"):
        summary = analysis["summary"]
        summary_html = (
            "<div class=\"summary\">"
            f"<div><strong>PASS</strong> {summary.get('PASS', 0)}</div>"
            f"<div><strong>WARNING</strong> {summary.get('WARNING', 0)}</div>"
            f"<div><strong>DEGRADATION</strong> {summary.get('DEGRADATION', 0)}</div>"
            f"<div><strong>SKIP</strong> {summary.get('SKIP', 0)}</div>"
            "</div>"
        )

    title_safe = html.escape(title)
    run_id = html.escape(str(run_meta.get("run_id")))
    baseline_id = html.escape(str(run_meta.get("baseline_id") or "-"))

    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{title_safe}</title>
  <style>
    :root {{
      --pass: #2a7a2a;
      --warn: #b36b00;
      --fail: #b00020;
      --muted: #6b7280;
      --bg: #f8fafc;
      --card: #ffffff;
      --line: #e2e8f0;
    }}
    body {{
      font-family: "Helvetica Neue", Arial, sans-serif;
      margin: 0;
      padding: 24px;
      background: var(--bg);
      color: #111827;
    }}
    .header {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 16px;
    }}
    .title {{
      font-size: 24px;
      font-weight: 700;
    }}
    .meta {{
      color: var(--muted);
      font-size: 13px;
    }}
    .card {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 16px;
      margin-bottom: 16px;
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
    }}
    .status {{
      font-weight: 700;
      font-size: 16px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    th, td {{
      padding: 8px 10px;
      border-bottom: 1px solid var(--line);
      text-align: left;
    }}
    th {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--muted);
    }}
    .status-pass {{ color: var(--pass); font-weight: 700; }}
    .status-warning {{ color: var(--warn); font-weight: 700; }}
    .status-fail {{ color: var(--fail); font-weight: 700; }}
    .status-skip {{ color: var(--muted); font-weight: 700; }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 12px;
      font-size: 13px;
      color: var(--muted);
      margin-top: 12px;
    }}
  </style>
</head>
<body>
  <div class=\"header\">
    <div>
      <div class=\"title\">{title_safe}</div>
      <div class=\"meta\">Run: {run_id} | Baseline: {baseline_id}</div>
    </div>
    <div class=\"status { _status_class(status) }\">{html.escape(status)}</div>
  </div>

  <div class=\"card\">
    <div class=\"meta\">Generated at {generated_at}</div>
    {summary_html}
  </div>

  <div class=\"card\">
    <table>
      <thead>
        <tr>
          <th>Metric</th>
          <th>Baseline</th>
          <th>Current</th>
          <th>Delta %</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        {"".join(rows)}
      </tbody>
    </table>
  </div>
</body>
</html>"""
