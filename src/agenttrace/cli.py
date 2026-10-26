"""Command-line interface for AgentTrace."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agenttrace import __version__


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
        "-c", "--config",
        type=Path,
        required=True,
        help="Path to TOML configuration file",
    )
    run_parser.add_argument(
        "-o", "--outdir",
        type=Path,
        default=Path("experiments/results"),
        help="Directory to store run outputs (default: experiments/results)",
    )

    # compare command
    compare_parser = subparsers.add_parser("compare", help="Compare two experiment runs")
    compare_parser.add_argument(
        "run1",
        type=Path,
        help="Path to first run directory",
    )
    compare_parser.add_argument(
        "run2",
        type=Path,
        help="Path to second run directory",
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


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        sys.stdout.write(f"AgentTrace run placeholder: config={args.config}\n")
        return 0
    elif args.command == "compare":
        sys.stdout.write(f"AgentTrace compare: run1={args.run1}, run2={args.run2}\n")
        return 0
    elif args.command == "probe":
        sys.stdout.write("AgentTrace platform capability probe\n")
        return 0
    elif args.command == "validate":
        sys.stdout.write(f"AgentTrace validate: {args.trace_file}\n")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
