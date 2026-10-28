"""Command-line interface for AgentTrace."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agenttrace import __version__
from agenttrace.validation import validate_trace


def create_parser() -> argparse.ArgumentParser:
    """Construct command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="agenttrace",
        description="AgentTrace: Instrumented research prototype for synthetic agent workloads.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # run command
    run_parser = subparsers.add_parser("run", help="Execute an instrumented experiment run")
    run_parser.add_argument(
        "-c",
        "--config",
        type=Path,
        required=True,
        help="Path to TOML configuration file",
    )
    run_parser.add_argument(
        "-o",
        "--outdir",
        type=Path,
        default=Path("experiments/results"),
        help="Directory to store run outputs (default: experiments/results)",
    )

    # compare command
    compare_parser = subparsers.add_parser("compare", help="Compare two experiment runs")
    compare_parser.add_argument(
        "run1",
        type=Path,
        help="Path to first run directory or JSONL trace file",
    )
    compare_parser.add_argument(
        "run2",
        type=Path,
        help="Path to second run directory or JSONL trace file",
    )
    compare_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Optional path to write comparison markdown report",
    )

    # analyze command
    analyze_parser = subparsers.add_parser(
        "analyze", help="Analyze a trace file for concurrency, critical path, and latency"
    )
    analyze_parser.add_argument(
        "trace_file",
        type=Path,
        help="Path to JSONL trace file",
    )

    # probe command (platform verification)
    subparsers.add_parser("probe", help="Probe host capabilities and resource metrics")

    # validate command
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate a trace file for completeness",
    )
    validate_parser.add_argument(
        "trace_file",
        type=Path,
        help="Path to JSONL trace file",
    )

    return parser


def _resolve_trace_path(p: Path) -> Path:
    if p.is_dir():
        candidate = p / "trace.jsonl"
        if candidate.is_file():
            return candidate
    return p


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        sys.stdout.write(f"AgentTrace run placeholder: config={args.config}\n")
        return 0
    elif args.command == "analyze":
        from agenttrace.analysis.concurrency import compute_concurrency_profile
        from agenttrace.analysis.critical_path import compute_critical_path_from_spans
        from agenttrace.analysis.metrics import compute_distribution
        from agenttrace.storage.sqlite import SQLiteTraceStore

        trace_path = _resolve_trace_path(args.trace_file)
        if not trace_path.is_file():
            sys.stderr.write(f"Trace file not found: {trace_path}\n")
            return 1

        store = SQLiteTraceStore()
        count = store.ingest_jsonl(trace_path)
        spans = store.get_spans()

        prof = compute_concurrency_profile(spans)
        cp = compute_critical_path_from_spans(spans, observed_makespan_ns=prof.makespan_ns)
        durations = [s["duration_ms"] for s in spans if s.get("duration_ms") is not None]
        dist = compute_distribution(durations)

        sys.stdout.write(f"=== AgentTrace Analysis: {trace_path.name} ===\n")
        sys.stdout.write(f"Records ingested: {count} | Completed spans: {len(spans)}\n")
        sys.stdout.write(f"Observed makespan: {prof.makespan_ms:.2f} ms\n")
        sys.stdout.write(
            f"Max concurrency: {prof.max_concurrency} | "
            f"Mean concurrency: {prof.mean_concurrency:.2f}\n"
        )
        sys.stdout.write(
            f"Critical path duration: {cp.critical_path_duration_ms:.2f} ms "
            f"(Ratio: {cp.critical_path_ratio:.3f})\n"
        )
        sys.stdout.write(f"Critical path sequence: {' -> '.join(cp.critical_path)}\n")
        sys.stdout.write(
            f"Span latencies: p50={dist.p50:.2f} ms, p90={dist.p90:.2f} ms, "
            f"p95={dist.p95:.2f} ms, p99={dist.p99:.2f} ms\n"
        )
        return 0

    elif args.command == "compare":
        from agenttrace.analysis.compare import compare_runs

        p1 = _resolve_trace_path(args.run1)
        p2 = _resolve_trace_path(args.run2)

        if not p1.is_file() or not p2.is_file():
            sys.stderr.write(f"Error: input files not found ({p1}, {p2})\n")
            return 1

        result = compare_runs(p1, p2, baseline_label=p1.name, candidate_label=p2.name)
        report = result.summary_markdown()

        if getattr(args, "output", None):
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(report, encoding="utf-8")
            sys.stdout.write(f"Wrote comparison report to {args.output}\n")
        else:
            sys.stdout.write(report + "\n")
        return 0

    elif args.command == "probe":
        sys.stdout.write("AgentTrace platform capability probe\n")
        return 0
    elif args.command == "validate":
        try:
            val_result = validate_trace(args.trace_file)
        except OSError as error:
            sys.stderr.write(f"AgentTrace validate: {error}\n")
            return 1

        status = "valid" if val_result.valid else "invalid"
        sys.stdout.write(
            f"Trace {args.trace_file}: {status}; "
            f"{val_result.records_validated}/{val_result.records_seen} records validated; "
            f"{val_result.total_spans_completed}/{val_result.total_spans_started} spans complete "
            f"({val_result.completeness_percentage:.1f}%)\n"
        )
        for issue in val_result.issues:
            sys.stdout.write(f"- {issue}\n")
        return 0 if val_result.valid else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
