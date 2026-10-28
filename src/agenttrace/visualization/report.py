"""Self-contained offline HTML report generation for traces and comparisons."""

from __future__ import annotations

from pathlib import Path

from agenttrace.analysis.completeness import TraceCompletenessChecker
from agenttrace.analysis.concurrency import compute_concurrency_profile
from agenttrace.analysis.critical_path import compute_critical_path_from_spans
from agenttrace.analysis.metrics import compute_distribution
from agenttrace.storage.sqlite import SQLiteTraceStore
from agenttrace.visualization.concurrency import create_concurrency_figure
from agenttrace.visualization.resources import create_resource_figure
from agenttrace.visualization.timeline import create_gantt_figure

HTML_CSS = """
:root {
  --bg-primary: #121212;
  --bg-card: #1e1e1e;
  --bg-card-hover: #262626;
  --text-main: #f0f0f0;
  --text-muted: #a0a0a0;
  --accent-teal: #00e676;
  --accent-blue: #29b6f6;
  --accent-orange: #ff9800;
  --accent-red: #f44336;
  --border-subtle: #2d2d2d;
}

body {
  margin: 0;
  padding: 24px;
  background-color: var(--bg-primary);
  color: var(--text-main);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  line-height: 1.5;
}

.report-container {
  max-width: 1400px;
  margin: 0 auto;
}

header {
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-subtle);
}

header h1 {
  margin: 0 0 8px 0;
  font-size: 1.85rem;
  font-weight: 700;
  letter-spacing: -0.5px;
  color: #fff;
}

.meta-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  color: var(--text-muted);
  font-size: 0.85rem;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 28px;
}

.kpi-card {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  padding: 16px;
  transition: transform 0.15s ease, background-color 0.15s ease;
}

.kpi-card:hover {
  background-color: var(--bg-card-hover);
  transform: translateY(-2px);
}

.kpi-title {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
  margin-bottom: 6px;
}

.kpi-value {
  font-size: 1.6rem;
  font-weight: 700;
  color: #fff;
}

.kpi-sub {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-top: 4px;
}

.chart-section {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 24px;
}

.section-title {
  margin-top: 0;
  margin-bottom: 16px;
  font-size: 1.15rem;
  font-weight: 600;
}

.data-table-container {
  overflow-x: auto;
  margin-top: 16px;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
  text-align: left;
}

th {
  background: #252525;
  color: var(--text-muted);
  font-weight: 600;
  padding: 10px 14px;
  border-bottom: 2px solid var(--border-subtle);
}

td {
  padding: 10px 14px;
  border-bottom: 1px solid var(--border-subtle);
  color: #ddd;
}

tr:hover td {
  background: rgba(255, 255, 255, 0.02);
}

.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
}

.badge-ok { background: rgba(0, 230, 118, 0.2); color: var(--accent-teal); }
.badge-error { background: rgba(244, 67, 54, 0.2); color: var(--accent-red); }
.badge-incomplete { background: rgba(255, 152, 0, 0.2); color: var(--accent-orange); }

footer {
  margin-top: 40px;
  padding-top: 16px;
  border-top: 1px solid var(--border-subtle);
  text-align: center;
  font-size: 0.75rem;
  color: var(--text-muted);
}
"""


def generate_trace_html_report(
    trace_path: str | Path,
    output_path: str | Path,
    include_plotlyjs: bool | str = "cdn",
) -> Path:
    """Generate a self-contained HTML analysis and visualization report for a trace."""
    path = Path(trace_path)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Ingest trace into SQLite store
    store = SQLiteTraceStore()
    total_records = store.ingest_jsonl(path)
    spans = store.get_spans()
    resource_samples = store.get_resource_samples()

    # Analytical computations
    concurrency = compute_concurrency_profile(spans)
    cp = compute_critical_path_from_spans(spans, observed_makespan_ns=concurrency.makespan_ns)
    durations = [s["duration_ms"] for s in spans if s.get("duration_ms") is not None]
    dist = compute_distribution(durations)

    # Completeness verification
    completeness = TraceCompletenessChecker(path).check()

    # Generate Plotly Figures
    fig_gantt = create_gantt_figure(spans, critical_path_ids=cp.critical_path)
    fig_concurrency = create_concurrency_figure(concurrency)
    fig_resources = create_resource_figure(resource_samples)

    gantt_html = fig_gantt.to_html(
        full_html=False, include_plotlyjs=include_plotlyjs, default_height="500px"
    )
    concurrency_html = fig_concurrency.to_html(
        full_html=False, include_plotlyjs=False, default_height="320px"
    )
    resources_html = fig_resources.to_html(
        full_html=False, include_plotlyjs=False, default_height="650px"
    )

    # Generate HTML Table Rows
    table_rows: list[str] = []
    for s in spans:
        status = s.get("status", "ok")
        badge_cls = f"badge-{status}"
        is_cp = s["span_id"] in cp.critical_path
        row = (
            f"<tr>"
            f"<td><code>{s.get('span_id')}</code></td>"
            f"<td>{s.get('task_id', '')}</td>"
            f"<td>{s.get('name', '')}</td>"
            f"<td><span class='badge {badge_cls}'>{status}</span></td>"
            f"<td>{s.get('duration_ms', 0):.2f}</td>"
            f"<td>{'<b>YES</b>' if is_cp else 'No'}</td>"
            f"<td><code>{s.get('parent_span_id') or '-'}</code></td>"
            f"</tr>"
        )
        table_rows.append(row)

    table_body = "\n".join(table_rows)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>AgentTrace Report: {path.name}</title>
  <style>{HTML_CSS}</style>
</head>
<body>
  <div class="report-container">
    <header>
      <h1>AgentTrace Performance & Attribution Report</h1>
      <div class="meta-tags">
        <span>File: <b>{path.name}</b></span>
        <span>Records: <b>{total_records}</b></span>
        <span>Spans Completed: <b>{len(spans)}</b></span>
        <span>Trace Status: <b>{"VALID" if completeness.is_valid else "INCOMPLETE"}</b></span>
      </div>
    </header>

    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-title">Makespan</div>
        <div class="kpi-value">
          {concurrency.makespan_ms:.1f} <span style="font-size: 1rem">ms</span>
        </div>
        <div class="kpi-sub">Total execution window</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-title">Max Concurrency</div>
        <div class="kpi-value">{concurrency.max_concurrency}</div>
        <div class="kpi-sub">Mean: {concurrency.mean_concurrency:.2f} active spans</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-title">Critical Path</div>
        <div class="kpi-value">
          {cp.critical_path_duration_ms:.1f} <span style="font-size: 1rem">ms</span>
        </div>
        <div class="kpi-sub">Ratio: {cp.critical_path_ratio:.3f} | Latency lower bound</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-title">Latency Distribution</div>
        <div class="kpi-value">{dist.p50:.1f} <span style="font-size: 1rem">ms</span></div>
        <div class="kpi-sub">p95: {dist.p95:.1f} ms | IQR: {dist.iqr:.1f} ms</div>
      </div>
    </div>

    <div class="chart-section">
      <h2 class="section-title">Workflow Execution Timeline (Gantt)</h2>
      {gantt_html}
    </div>

    <div class="chart-section">
      <h2 class="section-title">Instantaneous Concurrency Profile (Sweep-Line)</h2>
      {concurrency_html}
    </div>

    <div class="chart-section">
      <h2 class="section-title">Synchronized Process Resource Telemetry</h2>
      {resources_html}
    </div>

    <div class="chart-section">
      <h2 class="section-title">Span Manifest & Causal Details</h2>
      <div class="data-table-container">
        <table>
          <thead>
            <tr>
              <th>Span ID</th>
              <th>Task ID</th>
              <th>Name</th>
              <th>Status</th>
              <th>Duration (ms)</th>
              <th>Critical Path</th>
              <th>Parent Span</th>
            </tr>
          </thead>
          <tbody>
            {table_body}
          </tbody>
        </table>
      </div>
    </div>

    <footer>
      Generated by <b>AgentTrace</b> research instrumentation platform.<br>
      Monotonic nanosecond timing and honest attribution.
    </footer>
  </div>
</body>
</html>"""

    out.write_text(html_content, encoding="utf-8")
    return out
