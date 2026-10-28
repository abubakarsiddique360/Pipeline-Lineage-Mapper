from pipeline_lineage_mapper.lineage import (
    ancestors,
    critical_path,
    cycles,
    depth,
    descendants,
    graph,
    impact,
    order,
    waves,
)
from pipeline_lineage_mapper.model import pipeline_from_dict

DIAMOND = {
    "name": "diamond",
    "nodes": [
        {"id": "a", "kind": "source", "writes": ["raw.a"], "minutes": 1},
        {"id": "b", "reads": ["raw.a"], "writes": ["stg.b"], "minutes": 2},
        {"id": "c", "reads": ["raw.a"], "writes": ["stg.c"], "minutes": 3},
        {"id": "d", "kind": "sink", "reads": ["stg.b", "stg.c"], "writes": ["out.d"], "minutes": 4},
    ],
    "edges": [["a", "b"], ["a", "c"], ["b", "d"], ["c", "d"]],
}

CYCLE = {
    "name": "loop",
    "nodes": ["x", "y", "z"],
    "edges": [["x", "y"], ["y", "x"], ["y", "z"]],
}


def diamond():
    return pipeline_from_dict(DIAMOND)


def test_topological_order_is_stable():
    assert order(diamond()) == ("a", "b", "c", "d")


def test_depth_is_longest_path():
    assert depth(diamond()) == {"a": 0, "b": 1, "c": 1, "d": 2}


def test_waves_group_by_depth():
    assert waves(diamond()) == (("a",), ("b", "c"), ("d",))


def test_no_cycles_in_diamond():
    assert graph(diamond()).acyclic
    assert cycles(diamond()) == ()


def test_cycle_is_detected_once():
    pipeline = pipeline_from_dict(CYCLE)
    found = cycles(pipeline)
    assert found == (("x", "y"),)


def test_cycle_nodes_are_excluded_from_waves():
    pipeline = pipeline_from_dict(CYCLE)
    shape = graph(pipeline)
    assert not shape.acyclic
    assert ("z",) in waves(pipeline)


def test_critical_path_follows_the_slow_branch():
    path, total = critical_path(diamond())
    assert path == ("a", "c", "d")
    assert total == 8


def test_critical_path_ignores_cycles():
    pipeline = pipeline_from_dict(CYCLE)
    path, _total = critical_path(pipeline)
    assert path


def test_descendants_and_ancestors():
    pipeline = diamond()
    assert descendants(pipeline, "a") == ("b", "c", "d")
    assert ancestors(pipeline, "d") == ("a", "b", "c")
    assert descendants(pipeline, "d") == ()


def test_impact_lists_producer_and_downstream():
    hit = impact(diamond(), "stg.b")
    assert hit["producers"] == ("b",)
    assert hit["downstream"] == ("d",)


def test_impact_of_shared_input():
    hit = impact(diamond(), "raw.a")
    assert hit["downstream"] == ("b", "c", "d")


def test_impact_of_unknown_dataset():
    assert impact(diamond(), "nope") == {"producers": (), "downstream": ()}


def test_order_is_reproducible_for_equal_nodes():
    pipeline = pipeline_from_dict(
        {"nodes": ["m", "a", "z"], "edges": [["a", "m"], ["a", "z"]]}
    )
    assert order(pipeline) == ("a", "m", "z")
