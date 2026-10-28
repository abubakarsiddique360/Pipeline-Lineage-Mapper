"""Reports for a lineage map."""

from __future__ import annotations

import json

from .analysis import SEVERITY_ORDER, Review
from .lineage import ancestors, critical_path, descendants, graph, impact
from .model import Pipeline

BADGES = {"high": "HIGH", "medium": "MEDIUM", "low": "LOW"}


def render_review(result: Review) -> str:
    lines = [f"Lineage review: {result.pipeline}", "=" * 78]
    lines.append(
        f"risk {result.risk} points (grade {result.grade})   nodes {result.nodes}   "
        f"edges {result.edges}   high {result.counts['high']}   "
        f"medium {result.counts['medium']}   low {result.counts['low']}"
    )
    if result.clean:
        lines.append("")
        lines.append("No findings. Acyclic, owned, single-writer, no dangling outputs.")
        return "\n".join(lines)
    current = None
    for finding in result.findings:
        if finding.severity != current:
            current = finding.severity
            lines.append("")
            lines.append(BADGES[current])
        lines.append(f"  [{finding.code}] {finding.target}")
        lines.append(f"      {finding.message}")
        lines.append(f"      fix: {finding.hint}")
    return "\n".join(lines)


def render_markdown(result: Review) -> str:
    lines = [
        f"### Lineage review: `{result.pipeline}`",
        "",
        f"**Risk {result.risk} points (grade {result.grade})** - {result.counts['high']} high, "
        f"{result.counts['medium']} medium, {result.counts['low']} low, "
        f"{result.nodes} nodes, {result.edges} edges.",
        "",
        "| Severity | Target | Finding | Fix |",
        "| --- | --- | --- | --- |",
    ]
    if result.clean:
        lines.append("| - | - | No findings | - |")
    for finding in result.findings:
        lines.append(
            f"| {BADGES[finding.severity]} | `{finding.target}` | "
            f"{finding.message.replace('|', '/')} | {finding.hint.replace('|', '/')} |"
        )
    return "\n".join(lines)


def render_json(result: Review) -> str:
    return json.dumps(result.as_dict(), indent=2)


def render_waves(pipeline: Pipeline) -> str:
    shape = graph(pipeline)
    lines = [f"Execution waves: {pipeline.name}", "=" * 60]
    for index, wave in enumerate(shape.waves, start=1):
        lines.append(f"wave {index}  ({len(wave)})  {', '.join(wave)}")
    lines.append("")
    note = (
        f"{len(shape.waves)} waves would run sequentially; "
        "nodes inside a wave can run in parallel."
    )
    lines.append(note)
    return "\n".join(lines)


def render_critical(pipeline: Pipeline) -> str:
    path, total = critical_path(pipeline)
    lines = [f"Critical path: {pipeline.name}", "=" * 60]
    if not path:
        lines.append("no path (the graph is entirely cyclic)")
        return "\n".join(lines)
    running = 0.0
    for position, node_id in enumerate(path, start=1):
        node = pipeline.node(node_id)
        running += node.minutes
        lines.append(
            f"{position:>2}. {node_id:<22}{node.minutes:>7.1f} min   cumulative {running:>7.1f}"
        )
    lines.append("")
    lines.append(f"wall clock if everything else runs in parallel: {total:.1f} min")
    return "\n".join(lines)


def render_impact(pipeline: Pipeline, dataset: str) -> str:
    hit = impact(pipeline, dataset)
    lines = [f"Impact of {dataset}", "=" * 60]
    if not hit["producers"]:
        lines.append(f"no node in {pipeline.name} writes {dataset}")
        return "\n".join(lines)
    lines.append(f"producers     {', '.join(hit['producers'])}")
    lines.append(f"downstream    {', '.join(hit['downstream'])}")
    lines.append("")
    lines.append(
        f"{len(hit['downstream'])} node(s) downstream would need a rerun if {dataset} changed."
    )
    return "\n".join(lines)


def render_node(pipeline: Pipeline, node_id: str) -> str:
    node = pipeline.node(node_id)
    lines = [f"Node {node.id}", "=" * 60]
    lines.append(f"kind      {node.kind}")
    lines.append(f"owner     {node.owner or '-'}")
    lines.append(f"minutes   {node.minutes:g}")
    lines.append(f"reads     {', '.join(node.reads) or '-'}")
    lines.append(f"writes    {', '.join(node.writes) or '-'}")
    lines.append(f"upstream  {', '.join(ancestors(pipeline, node_id)) or '-'}")
    lines.append(f"downstream {', '.join(descendants(pipeline, node_id)) or '-'}")
    return "\n".join(lines)


def _mermaid_id(name: str) -> str:
    return "".join(char if char.isalnum() else "_" for char in name)


def render_mermaid(pipeline: Pipeline) -> str:
    shape = graph(pipeline)
    cyclic = {node_id for cycle in shape.cycles for node_id in cycle}
    lines = ["```mermaid", "flowchart LR"]
    for wave_index, wave in enumerate(shape.waves):
        lines.append(f"    subgraph wave_{wave_index + 1}[wave {wave_index + 1}]")
        for node_id in wave:
            node = pipeline.node(node_id)
            label = f"{node_id}<br/><small>{node.kind}"
            if node.minutes:
                label += f" - {node.minutes:g} min"
            label += "</small>"
            lines.append(f"        {_mermaid_id(node_id)}[\"{label}\"]")
        lines.append("    end")
    for edge in pipeline.edges:
        lines.append(f"    {_mermaid_id(edge.source)} --> {_mermaid_id(edge.target)}")
    if cyclic:
        lines.append("    classDef cyclic stroke:#cf222e,stroke-width:3px")
        for node_id in sorted(cyclic):
            lines.append(f"    class {_mermaid_id(node_id)} cyclic")
    lines.append("```")
    return "\n".join(lines)


def severity_counts(result: Review) -> dict[str, int]:
    return {severity: result.counts.get(severity, 0) for severity in SEVERITY_ORDER}
