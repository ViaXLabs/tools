"""
Render the HTML relationship report from a Graph (and optional suggestions).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .entities import Graph
from .logging_utils import REPORT_DIR, ensure_output_dirs, timestamp
from .suggest import Suggestion

logger = logging.getLogger("nr_rel.report")

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


def render_report(
    graph: Graph,
    query_used: str,
    title: str = "Relationship Report",
    suggestions: list[Suggestion] | None = None,
    aws_matches: list | None = None,
) -> Path:
    ensure_output_dirs()
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("report_template.html")

    node_list = list(graph.nodes.values())
    edge_list = graph.edges
    entity_types = sorted({n.entity_type for n in node_list})
    rel_types = sorted({e.rel_type for e in edge_list})
    node_names = {n.guid: n.name for n in node_list}

    graph_json = json.dumps(graph.to_dict())

    suggestion_dicts = [
        {
            "confidence": s.confidence,
            "source_name": s.source_name,
            "target_name": s.target_name,
            "suggested_type": s.suggested_type,
            "reason": s.reason,
        }
        for s in (suggestions or [])
    ]

    html = template.render(
        title=title,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        query_used=query_used,
        nodes=[
            {
                "name": n.name,
                "entity_type": n.entity_type,
                "guid": n.guid,
                "tags": n.tags,
                "system": n.system,
            }
            for n in node_list
        ],
        edges=[
            {"type": e.rel_type, "source": e.source_guid, "target": e.target_guid, "metadata": e.metadata}
            for e in edge_list
        ],
        node_names=node_names,
        entity_types=entity_types,
        rel_types=rel_types,
        suggestions=suggestion_dicts,
        aws_matches=[m.to_dict() for m in (aws_matches or [])],
        graph_json=graph_json,
    )

    out_path = REPORT_DIR / f"report_{timestamp()}.html"
    out_path.write_text(html, encoding="utf-8")
    logger.info("Wrote HTML report to %s", out_path)
    return out_path
