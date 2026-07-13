"""
Heuristic "you might be missing a relationship" suggestions.

This is deliberately simple and transparent (no ML, no black box): it
flags pairs of entities that share strong tag signals (same `service`,
same `team` + same `env`, etc.) but have no existing edge between them
in the graph you've already discovered. You review the output and turn
whichever ones make sense into a change plan with `plan-add`.
"""
from __future__ import annotations

from dataclasses import dataclass

from .entities import Graph

# Tag keys, in priority order, that we treat as strong relationship signals.
# Tune this list to match your account's tagging conventions.
STRONG_SIGNAL_TAGS = ["service", "app", "application"]
SUPPORTING_TAGS = ["team", "env", "environment", "cluster", "namespace"]


@dataclass
class Suggestion:
    source_guid: str
    source_name: str
    target_guid: str
    target_name: str
    suggested_type: str
    reason: str
    confidence: str  # "high" | "medium"


def _existing_edges(graph: Graph) -> set[tuple[str, str]]:
    pairs = set()
    for e in graph.edges:
        pairs.add((e.source_guid, e.target_guid))
        pairs.add((e.target_guid, e.source_guid))
    return pairs


def suggest_missing_relationships(graph: Graph) -> list[Suggestion]:
    existing = _existing_edges(graph)
    nodes = list(graph.nodes.values())
    suggestions: list[Suggestion] = []

    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            a, b = nodes[i], nodes[j]
            if (a.guid, b.guid) in existing:
                continue
            if a.type == b.type and a.entity_type == b.entity_type:
                # same-type entities are less likely to be a meaningful
                # "relationship" candidate (e.g. two hosts) -- skip unless
                # they share a strong signal tag AND a supporting tag.
                shared_strong = _shared_tag_values(a, b, STRONG_SIGNAL_TAGS)
                shared_support = _shared_tag_values(a, b, SUPPORTING_TAGS)
                if shared_strong and shared_support:
                    suggestions.append(
                        Suggestion(
                            a.guid, a.name, b.guid, b.name,
                            suggested_type="RELATED_TO",
                            reason=f"share {shared_strong} and {shared_support}",
                            confidence="medium",
                        )
                    )
                continue

            shared_strong = _shared_tag_values(a, b, STRONG_SIGNAL_TAGS)
            if shared_strong:
                suggestions.append(
                    Suggestion(
                        a.guid, a.name, b.guid, b.name,
                        suggested_type="CONTAINS" if a.type == "APPLICATION" else "RELATED_TO",
                        reason=f"share {shared_strong}",
                        confidence="high",
                    )
                )

    return suggestions


def _shared_tag_values(a, b, keys: list[str]) -> dict[str, list[str]]:
    shared: dict[str, list[str]] = {}
    for key in keys:
        a_vals = set(a.tags.get(key, []))
        b_vals = set(b.tags.get(key, []))
        overlap = a_vals & b_vals
        if overlap:
            shared[key] = sorted(overlap)
    return shared
