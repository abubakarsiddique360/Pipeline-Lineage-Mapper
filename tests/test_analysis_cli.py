import json

import pytest

from pipeline_lineage_mapper.analysis import review
from pipeline_lineage_mapper.cli import main
from pipeline_lineage_mapper.model import pipeline_from_dict
from pipeline_lineage_mapper.report import (
    render_critical,
    render_impact,
    render_json,
    render_markdown,
    render_mermaid,
    render_node,
    render_review,
    render_waves,
)

CLEAN = {
    "name": "clean",
    "nodes": [
        {"id": "src", "kind": "source", "owner": "a", "writes": ["raw.x"], "minutes": 1},
        {"id": "mid", "owner": "b", "reads": ["raw.x"], "writes": ["stg.x"], "minutes": 2},
        {"id": "out", "kind": "sink", "owner": "c", "reads": ["stg.x"], "writes": ["rep.x"],
         "minutes": 1},
    ],
    "edges": [["src", "mid"], ["mid", "out"]],
}

PROBLEMS = {
    "name": "problems",
    "nodes": [
        {"id": "src", "kind": "source", "writes": ["raw.x", "raw.dup"], "minutes": 1},
        {"id": "dup", "owner": "b", "reads": ["raw.x"], "writes": ["raw.dup"], "minutes": 2},
        {"id": "a", "owner": "b", "reads": ["raw.x"], "writes": ["stg.a"], "minutes": 2},
        {"id": "b", "owner": "b", "reads": ["raw.x"], "writes": ["stg.b"], "minutes": 2},
        {"id": "c", "owner": "b", "reads": ["raw.x"], "writes": ["stg.c"], "minutes": 2},
        {"id": "orphan", "owner": "b", "minutes": 1},
        {"id": "reader", "owner": "b", "reads": ["nowhere.data"], "writes": ["stg.r"],
         "minutes": 1},
        {"id": "leftover", "owner": "b", "reads": ["raw.x"], "writes": ["tmp.x"], "minutes": 1},
    ],
    "edges": [
        ["src", "dup"],
        ["src", "a"],
        ["src", "b"],
        ["src", "c"],
        ["src", "reader"],
        ["src", "leftover"],
    ],
}

LOOP = {"name": "loop", "nodes": ["x", "y"], "edges": [["x", "y"], ["y", "x"]]}


def codes(result) -> list[str]:
    return [finding.code for finding in result.findings]


def test_clean_pipeline_is_grade_a():
    result = review(pipeline_from_dict(CLEAN))
    assert result.clean
    assert result.grade == "A"


def test_counts_nodes_and_edges():
    result = review(pipeline_from_dict(CLEAN))
    assert result.nodes == 3
    assert result.edges == 2


def test_cycle_is_high():
    result = review(pipeline_from_dict(LOOP))
    assert "cycle" in codes(result)
    assert result.counts["high"] >= 1


def test_duplicate_writer_is_high():
    result = review(pipeline_from_dict(PROBLEMS))
    assert "duplicate-writer" in codes(result)


def test_dangling_output_only_for_non_terminal_producers():
    result = review(pipeline_from_dict(PROBLEMS))
    targets = {finding.target for finding in result.findings if finding.code == "dangling-output"}
    assert "tmp.x" in targets
    # raw.dup is written twice and read by nobody, so both rules apply to it; the duplicate
    # writer is the finding that matters, but the dangling output is still true.
    assert "raw.dup" in targets


def test_dangling_output_skips_sink_and_export_nodes():
    pipeline = pipeline_from_dict(
        {
            "nodes": [
                {"id": "src", "kind": "source", "owner": "a", "writes": ["raw.x"]},
                {"id": "sink", "kind": "sink", "owner": "a", "reads": ["raw.x"],
                 "writes": ["rep.x"]},
                {"id": "export", "kind": "export", "owner": "a", "reads": ["raw.x"],
                 "writes": ["wh.x"]},
            ],
            "edges": [["src", "sink"], ["src", "export"]],
        }
    )
    result = review(pipeline)
    assert [f.target for f in result.findings if f.code == "dangling-output"] == []


def test_missing_upstream_is_medium():
    result = review(pipeline_from_dict(PROBLEMS))
    finding = next(item for item in result.findings if item.code == "missing-upstream")
    assert finding.severity == "medium"
    assert finding.target == "reader"


def test_no_owner_is_low():
    result = review(pipeline_from_dict(PROBLEMS))
    assert "no-owner" in codes(result)


def test_isolated_node():
    result = review(pipeline_from_dict(PROBLEMS))
    finding = next(item for item in result.findings if item.code == "isolated-node")
    assert finding.target == "orphan"


def test_wide_fanout():
    result = review(pipeline_from_dict(PROBLEMS))
    finding = next(item for item in result.findings if item.code == "wide-fanout")
    assert finding.target == "src"


def test_findings_sorted_by_severity():
    from pipeline_lineage_mapper.analysis import SEVERITY_ORDER

    result = review(pipeline_from_dict(PROBLEMS))
    order = [SEVERITY_ORDER[item.severity] for item in result.findings]
    assert order == sorted(order)


def test_should_fail_threshold():
    result = review(pipeline_from_dict(CLEAN))
    assert not result.should_fail("high")
    assert not result.should_fail("never")


def test_reports_render():
    result = review(pipeline_from_dict(PROBLEMS))
    assert "Lineage review" in render_review(result)
    assert "| Severity |" in render_markdown(result)
    payload = json.loads(render_json(result))
    assert payload["counts"]["medium"] >= 1


def test_clean_review_text():
    assert "No findings" in render_review(review(pipeline_from_dict(CLEAN)))


@pytest.fixture
def pipeline_file(tmp_path):
    path = tmp_path / "pipeline.json"
    path.write_text(json.dumps(PROBLEMS), encoding="utf-8")
    return path


@pytest.fixture
def clean_file(tmp_path):
    path = tmp_path / "clean.json"
    path.write_text(json.dumps(CLEAN), encoding="utf-8")
    return path


def test_cli_review(pipeline_file, capsys):
    assert main(["review", "--pipeline", str(pipeline_file), "--fail-on", "never"]) == 0
    assert "Lineage review" in capsys.readouterr().out


def test_cli_review_exit_code(pipeline_file, capsys):
    assert main(["review", "--pipeline", str(pipeline_file)]) == 1
    capsys.readouterr()


def test_cli_review_clean(clean_file, capsys):
    assert main(["review", "--pipeline", str(clean_file)]) == 0
    assert "No findings" in capsys.readouterr().out


def test_cli_review_markdown(pipeline_file, capsys):
    assert main(["review", "--pipeline", str(pipeline_file), "--format", "markdown",
                 "--fail-on", "never"]) == 0
    assert "| Severity |" in capsys.readouterr().out


def test_cli_review_json(pipeline_file, capsys):
    assert main(["review", "--pipeline", str(pipeline_file), "--format", "json",
                 "--fail-on", "never"]) == 0
    assert json.loads(capsys.readouterr().out)["nodes"] == 8


def test_cli_graph(clean_file, capsys):
    assert main(["graph", "--pipeline", str(clean_file)]) == 0
    output = capsys.readouterr().out
    assert "flowchart LR" in output
    assert "subgraph wave_1" in output


def test_cli_waves(clean_file, capsys):
    assert main(["waves", "--pipeline", str(clean_file)]) == 0
    assert "wave 1" in capsys.readouterr().out


def test_cli_waves_warns_about_cycles(tmp_path, capsys):
    path = tmp_path / "loop.json"
    path.write_text(json.dumps(LOOP), encoding="utf-8")
    assert main(["waves", "--pipeline", str(path)]) == 0
    assert "cycle(s)" in capsys.readouterr().out


def test_cli_critical(clean_file, capsys):
    assert main(["critical", "--pipeline", str(clean_file)]) == 0
    output = capsys.readouterr().out
    assert "Critical path" in output
    assert "4.0 min" in output


def test_cli_node(clean_file, capsys):
    assert main(["node", "--pipeline", str(clean_file), "--id", "mid"]) == 0
    output = capsys.readouterr().out
    assert "upstream  src" in output


def test_cli_node_unknown(clean_file, capsys):
    assert main(["node", "--pipeline", str(clean_file), "--id", "zzz"]) == 2
    assert "unknown node" in capsys.readouterr().err


def test_cli_impact(clean_file, capsys):
    assert main(["impact", "--pipeline", str(clean_file), "--dataset", "raw.x"]) == 0
    assert "downstream    mid, out" in capsys.readouterr().out


def test_cli_missing_file(tmp_path, capsys):
    assert main(["review", "--pipeline", str(tmp_path / "none.json")]) == 2
    assert "file not found" in capsys.readouterr().err


def test_mermaid_marks_cycle_nodes(tmp_path):
    pipeline = pipeline_from_dict(LOOP)
    text = render_mermaid(pipeline)
    assert "classDef cyclic" in text
    assert "x --> y" in text


def test_render_helpers_do_not_crash():
    pipeline = pipeline_from_dict(CLEAN)
    assert "Execution waves" in render_waves(pipeline)
    assert "Impact of raw.x" in render_impact(pipeline, "raw.x")
    assert "Node src" in render_node(pipeline, "src")
    assert "wall clock if everything else runs in parallel" in render_critical(pipeline)
