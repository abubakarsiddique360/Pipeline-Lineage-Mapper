"""Findings about a pipeline's shape."""

from __future__ import annotations

from dataclasses import dataclass

from .lineage import descendants, graph
from .model import Pipeline

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
SEVERITY_POINTS = {"high": 15, "medium": 8, "low": 3}
FAN_OUT_LIMIT = 3


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    target: str
    message: str
    hint: str

    @property
    def points(self) -> int:
        return SEVERITY_POINTS[self.severity]

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "target": self.target,
            "message": self.message,
            "hint": self.hint,
            "points": self.points,
        }


@dataclass(frozen=True)
class Review:
    pipeline: str
    findings: tuple[Finding, ...]
    risk: int
    grade: str
    counts: dict[str, int]
    nodes: int
    edges: int

    @property
    def clean(self) -> bool:
        return not self.findings

    def at_or_above(self, severity: str) -> list[Finding]:
        limit = SEVERITY_ORDER[severity]
        return [item for item in self.findings if SEVERITY_ORDER[item.severity] <= limit]

    def should_fail(self, fail_on: str) -> bool:
        if fail_on == "never":
            return False
        return bool(self.at_or_above(fail_on))

    def as_dict(self) -> dict:
        return {
            "pipeline": self.pipeline,
            "risk": self.risk,
            "grade": self.grade,
            "counts": self.counts,
            "nodes": self.nodes,
            "edges": self.edges,
            "findings": [item.as_dict() for item in self.findings],
        }


def _grade(risk: int) -> str:
    if risk == 0:
        return "A"
    if risk <= 10:
        return "B"
    if risk <= 30:
        return "C"
    if risk <= 60:
        return "D"
    return "F"


def review(pipeline: Pipeline) -> Review:
    findings: list[Finding] = []
    shape = graph(pipeline)

    for cycle in shape.cycles:
        findings.append(
            Finding(
                "cycle",
                "high",
                " -> ".join(cycle),
                f"dependency cycle through {len(cycle)} node(s)",
                "break the loop by making one hop a scheduled trigger instead of a dependency",
            )
        )

    written: dict[str, list[str]] = {}
    for node in pipeline.nodes:
        for dataset in node.writes:
            written.setdefault(dataset, []).append(node.id)
    terminal_kinds = {"sink", "export"}

    for dataset, writers in sorted(written.items()):
        if len(writers) > 1:
            findings.append(
                Finding(
                    "duplicate-writer",
                    "high",
                    dataset,
                    f"{dataset} is written by {len(writers)} nodes: {', '.join(sorted(writers))}",
                    "keep one writer per dataset, or the lineage cannot say who is right",
                )
            )
        if not pipeline.consumers(dataset):
            producer_kind = pipeline.node(writers[0]).kind
            if producer_kind in terminal_kinds:
                continue
            findings.append(
                Finding(
                    "dangling-output",
                    "low",
                    dataset,
                    f"{dataset} is written by {writers[0]} and read by nobody",
                    "drop the output, or the pipeline is paying to compute something unused",
                )
            )

    for node in pipeline.nodes:
        for dataset in node.reads:
            if dataset in written or node.is_source:
                continue
            findings.append(
                Finding(
                    "missing-upstream",
                    "medium",
                    node.id,
                    f"{node.id} reads {dataset}, which no node in this pipeline writes",
                    "mark the producer as a source node, or add the missing dependency",
                )
            )

    for node in pipeline.nodes:
        if not node.owner:
            findings.append(
                Finding(
                    "no-owner",
                    "low",
                    node.id,
                    f"{node.id} has no owner",
                    "set owner so a failure has somewhere to go",
                )
            )

    for node in pipeline.nodes:
        downstream = descendants(pipeline, node.id)
        children = pipeline.children(node.id)
        if len(children) >= FAN_OUT_LIMIT and len(downstream) >= FAN_OUT_LIMIT:
            findings.append(
                Finding(
                    "wide-fanout",
                    "medium",
                    node.id,
                    f"{node.id} feeds {len(children)} branches directly "
                    f"({len(downstream)} nodes in total downstream)",
                    "a failure here blocks every branch; split it or add an independent path",
                )
            )

    if len(pipeline.nodes) > 1:
        for node in pipeline.nodes:
            if not pipeline.parents(node.id) and not pipeline.children(node.id):
                findings.append(
                    Finding(
                        "isolated-node",
                        "medium",
                        node.id,
                        f"{node.id} has no parents and no children",
                        "wire it into the pipeline or delete it",
                    )
                )

    findings.sort(key=lambda item: (SEVERITY_ORDER[item.severity], item.target))
    risk = sum(item.points for item in findings)
    counts = {severity: 0 for severity in SEVERITY_ORDER}
    for item in findings:
        counts[item.severity] += 1
    return Review(
        pipeline=pipeline.name,
        findings=tuple(findings),
        risk=risk,
        grade=_grade(risk),
        counts=counts,
        nodes=len(pipeline.nodes),
        edges=len(pipeline.edges),
    )
