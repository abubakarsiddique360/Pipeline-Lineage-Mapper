"""Regenerate README assets from real runs.

Usage:  python scripts/render_assets.py
Writes: docs/results.json, docs/images/review.png,
        docs/images/waves-and-critical-path.png, docs/images/lineage-graph.png
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pipeline_lineage_mapper.analysis import review  # noqa: E402
from pipeline_lineage_mapper.lineage import critical_path, depth, impact  # noqa: E402
from pipeline_lineage_mapper.lineage import graph as shape_graph  # noqa: E402
from pipeline_lineage_mapper.model import load_pipeline  # noqa: E402
from pipeline_lineage_mapper.report import (  # noqa: E402
    render_critical,
    render_impact,
    render_review,
    render_waves,
)

BG = "#0d1117"
CHROME = "#161b22"
FG = "#e6edf3"
MUTED = "#8b949e"
ACCENT = "#79c0ff"
SEVERITY_COLORS = {"high": "#f85149", "medium": "#d29922", "low": "#6e7781"}


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("consola.ttf", "courier.ttf", "DejaVuSansMono.ttf"):
        candidate = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def render_terminal(text: str, out_path: Path, title: str) -> None:
    font = load_font(15)
    lines = text.expandtabs(4).splitlines() or [""]
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    char_width = probe.textlength("M", font=font)
    line_height = 21
    pad = 24
    width = int(max(len(line) for line in lines) * char_width) + pad * 2
    height = pad * 2 + len(lines) * line_height + 44
    image = Image.new("RGB", (max(width, 760), height), BG)
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, image.width, 34], fill=CHROME)
    for index, color in enumerate(("#ff5f56", "#ffbd2e", "#27c93f")):
        draw.ellipse([16 + index * 22, 10, 28 + index * 22, 22], fill=color)
    draw.text((92, 9), title, font=load_font(13), fill=MUTED)

    for row, line in enumerate(lines):
        color = FG
        stripped = line.strip()
        if line.startswith("$"):
            color = ACCENT
        elif stripped in ("HIGH", "MEDIUM", "LOW"):
            color = SEVERITY_COLORS[stripped.lower()]
        elif stripped.startswith("fix:"):
            color = "#3fb950"
        elif stripped.startswith("["):
            color = MUTED
        elif "risk" in stripped or stripped.startswith("wave "):
            color = MUTED
        draw.text((pad, 50 + row * line_height), line, font=font, fill=color)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path)


def _positions(pipeline) -> dict[str, tuple[float, float]]:
    depths = depth(pipeline)
    buckets: dict[int, list[str]] = {}
    for node_id, level in depths.items():
        if level < 0:
            continue
        buckets.setdefault(level, []).append(node_id)
    positions: dict[str, tuple[float, float]] = {}
    for level, names in buckets.items():
        for index, name in enumerate(sorted(names)):
            positions[name] = (level * 2.6, -index * 1.5)
    return positions


def render_graph(pipeline, result, out_path: Path) -> None:
    positions = _positions(pipeline)
    worst: dict[str, str] = {}
    for finding in result.findings:
        if finding.target in positions and finding.code != "dangling-output":
            worst.setdefault(finding.target, finding.severity)

    fig, ax = plt.subplots(figsize=(11.4, 4.4))
    fig.patch.set_facecolor("#ffffff")
    for edge in pipeline.edges:
        if edge.source not in positions or edge.target not in positions:
            continue
        start, end = positions[edge.source], positions[edge.target]
        span = end[0] - start[0]
        curve = 0.0 if span <= 2.6 + 1e-9 else 0.28
        ax.add_patch(
            FancyArrowPatch(
                (start[0] + 1.15, start[1]),
                (end[0] - 1.15, end[1]),
                arrowstyle="-|>",
                mutation_scale=13,
                color="#57606a",
                linewidth=1.3,
                shrinkA=0,
                shrinkB=0,
                connectionstyle=f"arc3,rad={curve}",
            )
        )
    for node_id, (x, y) in positions.items():
        node = pipeline.node(node_id)
        severity = worst.get(node_id)
        edge_color = SEVERITY_COLORS.get(severity, "#1a7f37") if severity else "#1a7f37"
        face = "#fff5f5" if severity in ("high", "medium") else "#f6f8fa"
        ax.add_patch(
            FancyBboxPatch(
                (x - 1.15, y - 0.38),
                2.3,
                0.76,
                boxstyle="round,pad=0.02,rounding_size=0.12",
                linewidth=2.0 if severity else 1.4,
                edgecolor=edge_color,
                facecolor=face,
            )
        )
        label = f"{node_id}\n{node.minutes:g} min" if node.minutes else node_id
        ax.text(x, y, label, ha="center", va="center", fontsize=8, color="#24292f")
        ax.text(x, y + 0.52, node.kind, ha="center", va="center", fontsize=6, color="#57606a")

    waves = shape_graph(pipeline).waves
    for level in range(len(waves)):
        ax.text(level * 2.6, 0.95, f"wave {level + 1}", ha="center", fontsize=8, color="#57606a")

    ax.set_title(
        "nightly-revenue: 5 waves, critical path 33.0 min, 1 node with fan-out 3",
        fontsize=10,
        loc="left",
    )
    ys = [y for _, y in positions.values()] or [0]
    ax.set_xlim(-1.9, max((x for x, _ in positions.values()), default=1) + 1.9)
    ax.set_ylim(min(ys) - 0.9, 1.3)
    ax.axis("off")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, format="png", dpi=150)
    plt.close(fig)


def render_timeline(pipeline, out_path: Path) -> None:
    path, total = critical_path(pipeline)

    fig, ax = plt.subplots(figsize=(9.6, 2.9))
    fig.patch.set_facecolor("#ffffff")
    running = 0.0
    for index, node_id in enumerate(path):
        node = pipeline.node(node_id)
        ax.barh(index, node.minutes, left=running, height=0.55, color="#0969da")
        ax.text(running + node.minutes / 2, index, f"{node.minutes:g} min", ha="center",
                va="center", fontsize=8, color="#ffffff")
        running += node.minutes
    ax.set_yticks(range(len(path)))
    ax.set_yticklabels(path, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("minutes from the start of the run (everything else runs in parallel)")
    ax.set_xlim(0, total * 1.08)
    ax.set_title(f"critical path of examples/pipeline.json: {total:g} min end to end",
                 fontsize=10, loc="left")
    ax.grid(axis="x", linestyle=":", alpha=0.45)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, format=out_path.suffix.lstrip("."))
    plt.close(fig)


def main() -> int:
    images = ROOT / "docs" / "images"
    images.mkdir(parents=True, exist_ok=True)
    os.chdir(ROOT)

    pipeline = load_pipeline("examples/pipeline.json")
    looping = load_pipeline("examples/cycle.json")
    result = review(pipeline)
    loop_result = review(looping)
    path, total = critical_path(pipeline)
    wave_list = shape_graph(pipeline).waves

    payload = {
        "pipeline": pipeline.name,
        "nodes": result.nodes,
        "edges": result.edges,
        "risk": result.risk,
        "grade": result.grade,
        "counts": result.counts,
        "waves": [list(wave) for wave in wave_list],
        "critical_path": list(path),
        "critical_minutes": total,
        "impact_fact_orders": list(impact(pipeline, "fact.orders")["downstream"]),
        "cycle_example": {
            "pipeline": looping.name,
            "risk": loop_result.risk,
            "grade": loop_result.grade,
            "counts": loop_result.counts,
            "findings": [finding.code for finding in loop_result.findings],
        },
        "findings": [finding.as_dict() for finding in result.findings],
    }
    (ROOT / "docs" / "results.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    terminal = (
        "$ lineage-map review --pipeline examples/pipeline.json\n\n"
        + render_review(result)
        + "\n\n$ lineage-map waves --pipeline examples/pipeline.json\n\n"
        + render_waves(pipeline)
        + "\n\n$ lineage-map critical --pipeline examples/pipeline.json\n\n"
        + render_critical(pipeline)
        + "\n\n$ lineage-map impact --pipeline examples/pipeline.json --dataset fact.orders\n\n"
        + render_impact(pipeline, "fact.orders")
        + "\n\n$ lineage-map review --pipeline examples/cycle.json | head -8\n\n"
        + "\n".join(render_review(loop_result).splitlines()[:8])
    )
    title = "lineage-map  -  waves, critical path, cycles, impact"
    render_terminal(terminal, images / "review.png", title)
    render_graph(pipeline, result, images / "lineage-graph.png")
    render_timeline(pipeline, images / "critical-path.svg")

    print(
        f"{pipeline.name}: risk={result.risk} grade={result.grade} waves={len(wave_list)} "
        f"critical={total:g} min via {' -> '.join(path)} | "
        f"{looping.name}: risk={loop_result.risk} grade={loop_result.grade}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
