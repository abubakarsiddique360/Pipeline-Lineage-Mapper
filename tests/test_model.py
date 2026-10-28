import json

import pytest

from pipeline_lineage_mapper.model import (
    LineageError,
    Pipeline,
    load_pipeline,
    pipeline_from_dict,
)

DIAMOND = {
    "name": "diamond",
    "nodes": [
        {"id": "a", "kind": "source", "owner": "team-a", "writes": ["raw.a"], "minutes": 1},
        {"id": "b", "owner": "team-b", "reads": ["raw.a"], "writes": ["stg.b"], "minutes": 2},
        {"id": "c", "owner": "team-c", "reads": ["raw.a"], "writes": ["stg.c"], "minutes": 3},
        {
            "id": "d",
            "kind": "sink",
            "owner": "team-d",
            "reads": ["stg.b", "stg.c"],
            "writes": ["out.d"],
            "minutes": 4,
        },
    ],
    "edges": [["a", "b"], ["a", "c"], ["b", "d"], ["c", "d"]],
}


def test_parses_nodes_and_edges():
    pipeline = pipeline_from_dict(DIAMOND)
    assert pipeline.name == "diamond"
    assert pipeline.node_ids == ("a", "b", "c", "d")
    assert len(pipeline.edges) == 4


def test_parents_and_children():
    pipeline = pipeline_from_dict(DIAMOND)
    assert pipeline.parents("d") == ("b", "c")
    assert pipeline.children("a") == ("b", "c")


def test_producers_and_consumers():
    pipeline = pipeline_from_dict(DIAMOND)
    assert pipeline.producers("stg.b") == ("b",)
    assert pipeline.consumers("raw.a") == ("b", "c")


def test_node_lookup_raises_for_unknown():
    pipeline = pipeline_from_dict(DIAMOND)
    with pytest.raises(LineageError, match="unknown node"):
        pipeline.node("zzz")


def test_string_node_shorthand():
    pipeline = pipeline_from_dict({"nodes": ["x", "y"], "edges": [["x", "y"]]})
    assert pipeline.node_ids == ("x", "y")
    assert pipeline.node("x").kind == "task"


def test_rejects_empty_nodes():
    with pytest.raises(LineageError, match="nodes must be a non-empty list"):
        pipeline_from_dict({"nodes": []})


def test_rejects_duplicate_node():
    with pytest.raises(LineageError, match="duplicate node"):
        pipeline_from_dict({"nodes": ["x", "x"]})


def test_rejects_negative_minutes():
    with pytest.raises(LineageError, match="negative minutes"):
        pipeline_from_dict({"nodes": [{"id": "x", "minutes": -1}]})


def test_rejects_edge_to_unknown_node():
    with pytest.raises(LineageError, match="unknown node"):
        pipeline_from_dict({"nodes": ["x"], "edges": [["x", "y"]]})


def test_rejects_self_dependency():
    with pytest.raises(LineageError, match="cannot depend on itself"):
        pipeline_from_dict({"nodes": ["x"], "edges": [["x", "x"]]})


def test_duplicate_edges_are_collapsed():
    pipeline = pipeline_from_dict(
        {"nodes": ["x", "y"], "edges": [["x", "y"], ["x", "y"]]}
    )
    assert len(pipeline.edges) == 1


def test_load_pipeline_roundtrip(tmp_path):
    path = tmp_path / "p.json"
    path.write_text(json.dumps(DIAMOND), encoding="utf-8")
    assert load_pipeline(path).name == "diamond"


def test_load_pipeline_missing(tmp_path):
    with pytest.raises(LineageError, match="file not found"):
        load_pipeline(tmp_path / "none.json")


def test_load_pipeline_bad_json(tmp_path):
    path = tmp_path / "p.json"
    path.write_text("{oops", encoding="utf-8")
    with pytest.raises(LineageError, match="not valid JSON"):
        load_pipeline(path)


def test_pipeline_type_is_exported():
    assert isinstance(pipeline_from_dict(DIAMOND), Pipeline)
