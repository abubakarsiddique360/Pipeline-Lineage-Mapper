"""A tiny pipeline model: nodes transform datasets, nodes depend on other nodes."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class LineageError(ValueError):
    """Raised when a lineage description cannot be used."""


@dataclass(frozen=True)
class Node:
    id: str
    kind: str = "task"
    owner: str = ""
    writes: tuple[str, ...] = ()
    reads: tuple[str, ...] = ()
    minutes: float = 0.0
    optional: bool = False

    @property
    def is_source(self) -> bool:
        return self.kind == "source"


@dataclass(frozen=True)
class Edge:
    source: str
    target: str


@dataclass(frozen=True)
class Pipeline:
    name: str
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...] = ()

    @property
    def node_ids(self) -> tuple[str, ...]:
        return tuple(node.id for node in self.nodes)

    def node(self, node_id: str) -> Node:
        for node in self.nodes:
            if node.id == node_id:
                return node
        raise LineageError(f"unknown node {node_id!r}")

    def parents(self, node_id: str) -> tuple[str, ...]:
        return tuple(edge.source for edge in self.edges if edge.target == node_id)

    def children(self, node_id: str) -> tuple[str, ...]:
        return tuple(edge.target for edge in self.edges if edge.source == node_id)

    def producers(self, dataset: str) -> tuple[str, ...]:
        return tuple(node.id for node in self.nodes if dataset in node.writes)

    def consumers(self, dataset: str) -> tuple[str, ...]:
        return tuple(node.id for node in self.nodes if dataset in node.reads)


@dataclass
class Graph:
    pipeline: Pipeline
    order: tuple[str, ...]
    waves: tuple[tuple[str, ...], ...]
    cycles: tuple[tuple[str, ...], ...] = field(default_factory=tuple)

    @property
    def acyclic(self) -> bool:
        return not self.cycles


def pipeline_from_dict(payload: Mapping[str, Any]) -> Pipeline:
    if not isinstance(payload, Mapping):
        raise LineageError("pipeline must be a JSON object")

    raw_nodes = payload.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise LineageError("nodes must be a non-empty list")

    nodes: list[Node] = []
    seen: set[str] = set()
    for entry in raw_nodes:
        if isinstance(entry, str):
            entry = {"id": entry}
        if not isinstance(entry, Mapping) or not entry.get("id"):
            raise LineageError("every node needs an id")
        node_id = str(entry["id"])
        if node_id in seen:
            raise LineageError(f"duplicate node {node_id!r}")
        seen.add(node_id)
        minutes = float(entry.get("minutes", 0.0))
        if minutes < 0:
            raise LineageError(f"node {node_id!r} has negative minutes")
        nodes.append(
            Node(
                id=node_id,
                kind=str(entry.get("kind", "task")),
                owner=str(entry.get("owner", "")),
                writes=tuple(str(item) for item in entry.get("writes", ())),
                reads=tuple(str(item) for item in entry.get("reads", ())),
                minutes=minutes,
                optional=bool(entry.get("optional", False)),
            )
        )

    known = {node.id for node in nodes}
    edges: list[Edge] = []
    for entry in payload.get("edges", []):
        if isinstance(entry, Mapping):
            source, target = entry.get("from"), entry.get("to")
        else:
            try:
                source, target = entry
            except (TypeError, ValueError) as exc:
                raise LineageError(f"edge {entry!r} must be [from, to]") from exc
        if source not in known or target not in known:
            raise LineageError(f"edge {source!r} -> {target!r} references an unknown node")
        if source == target:
            raise LineageError(f"node {source!r} cannot depend on itself")
        edge = Edge(source=str(source), target=str(target))
        if edge not in edges:
            edges.append(edge)

    return Pipeline(
        name=str(payload.get("name", "pipeline")), nodes=tuple(nodes), edges=tuple(edges)
    )


def load_pipeline(path: Path | str) -> Pipeline:
    source = Path(path)
    if not source.exists():
        raise LineageError(f"file not found: {source}")
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LineageError(f"not valid JSON at line {exc.lineno}: {exc.msg}") from exc
    return pipeline_from_dict(payload)
