"""Command line entry point for lineage-map."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .analysis import SEVERITY_ORDER, review
from .lineage import graph
from .model import LineageError, load_pipeline
from .report import (
    render_critical,
    render_impact,
    render_json,
    render_markdown,
    render_mermaid,
    render_node,
    render_review,
    render_waves,
)

SEVERITIES = tuple(SEVERITY_ORDER)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lineage-map",
        description="Map a data pipeline: waves, critical path, cycles and impact.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    rev = sub.add_parser("review", help="find cycles, dangling outputs and fan-out risks")
    rev.add_argument("--pipeline", required=True)
    rev.add_argument("--format", choices=("text", "markdown", "json"), default="text")
    rev.add_argument("--fail-on", choices=("never",) + SEVERITIES, default="high")

    graph_cmd = sub.add_parser("graph", help="print the pipeline as a Mermaid flowchart")
    graph_cmd.add_argument("--pipeline", required=True)

    waves = sub.add_parser("waves", help="parallel execution waves")
    waves.add_argument("--pipeline", required=True)

    critical = sub.add_parser("critical", help="longest dependency chain by duration")
    critical.add_argument("--pipeline", required=True)

    node = sub.add_parser("node", help="everything about one node")
    node.add_argument("--pipeline", required=True)
    node.add_argument("--id", required=True)

    impact_cmd = sub.add_parser("impact", help="what a dataset change would invalidate")
    impact_cmd.add_argument("--pipeline", required=True)
    impact_cmd.add_argument("--dataset", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        pipeline = load_pipeline(args.pipeline)
    except LineageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.command == "graph":
        print(render_mermaid(pipeline))
        return 0

    if args.command == "waves":
        shape = graph(pipeline)
        print(render_waves(pipeline))
        if shape.cycles:
            print()
            print(f"warning: {len(shape.cycles)} cycle(s) - waves omit the nodes inside them")
        return 0

    if args.command == "critical":
        print(render_critical(pipeline))
        return 0

    if args.command == "node":
        try:
            print(render_node(pipeline, args.id))
        except LineageError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        return 0

    if args.command == "impact":
        print(render_impact(pipeline, args.dataset))
        return 0

    result = review(pipeline)
    if args.format == "json":
        print(render_json(result))
    elif args.format == "markdown":
        print(render_markdown(result))
    else:
        print(render_review(result))
    return 1 if result.should_fail(args.fail_on) else 0


if __name__ == "__main__":
    raise SystemExit(main())
