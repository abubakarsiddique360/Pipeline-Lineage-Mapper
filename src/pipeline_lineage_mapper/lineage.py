"""Topological order, waves, cycles, critical path and impact analysis."""

from __future__ import annotations

from .model import Graph, Pipeline


def _cyclic_nodes(pipeline: Pipeline) -> set[str]:
    return {name for cycle in cycles(pipeline) for name in cycle}


def order(pipeline: Pipeline) -> tuple[str, ...]:
    """Kahn's algorithm over the acyclic part, alphabetically for reproducibility.

    Nodes inside a dependency cycle are left out: they have no valid position, and pretending
    otherwise would hide the cycle instead of surfacing it.
    """
    cyclic = _cyclic_nodes(pipeline)
    remaining: dict[str, set[str]] = {
        node.id: {parent for parent in pipeline.parents(node.id) if parent not in cyclic}
        for node in pipeline.nodes
        if node.id not in cyclic
    }
    ordered: list[str] = []
    while remaining:
        ready = sorted(name for name, parents in remaining.items() if not parents)
        if not ready:
            break
        for name in ready:
            ordered.append(name)
        for name in ready:
            remaining.pop(name)
        for parents in remaining.values():
            parents.difference_update(ready)
    return tuple(ordered)


def cycles(pipeline: Pipeline) -> tuple[tuple[str, ...], ...]:
    """Every elementary cycle, each rotated to start at its alphabetically first node."""
    adjacency = {node.id: list(pipeline.children(node.id)) for node in pipeline.nodes}
    found: list[tuple[str, ...]] = []
    for start in sorted(adjacency):
        stack: list[tuple[str, tuple[str, ...]]] = [(start, (start,))]
        while stack:
            current, path = stack.pop()
            for child in adjacency[current]:
                if child == start:
                    cycle = path
                    pivot = min(range(len(cycle)), key=lambda index: cycle[index])
                    rotated = cycle[pivot:] + cycle[:pivot]
                    if rotated not in found:
                        found.append(rotated)
                elif child not in path and child > start:
                    stack.append((child, path + (child,)))
    return tuple(sorted(found))


def depth(pipeline: Pipeline) -> dict[str, int]:
    """Longest-path depth of each node. Nodes in a cycle report -1 and are not scheduled.

    A node that only depends on a cycle is still schedulable, so it lands in wave 1 - the cycle
    is the thing to fix, not everything downstream of it.
    """
    cyclic = _cyclic_nodes(pipeline)
    result: dict[str, int] = {}
    pending = [node.id for node in pipeline.nodes if node.id not in cyclic]
    while pending:
        progressed = False
        for name in list(pending):
            parents = pipeline.parents(name)
            if all(parent in result or parent in cyclic for parent in parents):
                base = max((result[parent] for parent in parents if parent in result), default=-1)
                result[name] = base + 1
                pending.remove(name)
                progressed = True
        if not progressed:
            for name in pending:
                result[name] = -1
            break
    for name in cyclic:
        result[name] = -1
    return result


def waves(pipeline: Pipeline) -> tuple[tuple[str, ...], ...]:
    depths = depth(pipeline)
    buckets: dict[int, list[str]] = {}
    for name, level in depths.items():
        if level < 0:
            continue
        buckets.setdefault(level, []).append(name)
    return tuple(tuple(sorted(buckets[level])) for level in sorted(buckets))


def graph(pipeline: Pipeline) -> Graph:
    return Graph(
        pipeline=pipeline,
        order=order(pipeline),
        waves=waves(pipeline),
        cycles=cycles(pipeline),
    )


def durations(pipeline: Pipeline) -> dict[str, float]:
    return {node.id: node.minutes for node in pipeline.nodes}


def critical_path(pipeline: Pipeline) -> tuple[tuple[str, ...], float]:
    """Longest dependency chain by summed duration, ignoring nodes inside cycles."""
    ordered = order(pipeline)
    durations_by_node = durations(pipeline)
    best: dict[str, tuple[float, tuple[str, ...]]] = {}
    for name in ordered:
        parents = [parent for parent in pipeline.parents(name) if parent in best] or [None]
        if parents == [None]:
            best[name] = (durations_by_node[name], (name,))
            continue
        total, path = max(
            (best[parent] for parent in parents), key=lambda item: (item[0], item[1])
        )
        best[name] = (total + durations_by_node[name], (*path, name))
    if not best:
        return (), 0.0
    total, path = max(best.values(), key=lambda item: (item[0], item[1]))
    return path, total


def descendants(pipeline: Pipeline, node_id: str) -> tuple[str, ...]:
    pipeline.node(node_id)
    seen: list[str] = []
    stack = list(pipeline.children(node_id))
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.append(current)
        stack.extend(pipeline.children(current))
    return tuple(sorted(seen))


def ancestors(pipeline: Pipeline, node_id: str) -> tuple[str, ...]:
    pipeline.node(node_id)
    seen: list[str] = []
    stack = list(pipeline.parents(node_id))
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.append(current)
        stack.extend(pipeline.parents(current))
    return tuple(sorted(seen))


def impact(pipeline: Pipeline, dataset: str) -> dict[str, tuple[str, ...]]:
    """Which nodes produce a dataset, and everything downstream of those producers."""
    producers = pipeline.producers(dataset)
    hit: set[str] = set()
    for producer in producers:
        hit.update(descendants(pipeline, producer))
    return {"producers": producers, "downstream": tuple(sorted(hit))}
