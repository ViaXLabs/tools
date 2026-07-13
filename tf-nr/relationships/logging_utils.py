"""
Discovery: find entities by tag, then walk their relationships out to a
given depth, building a simple in-memory graph you can report on or
save to disk for later `report` / `suggest` / `apply` runs.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from .nerdgraph_client import NerdGraphClient
from .queries import (
    ENTITY_SEARCH_BY_TAG,
    ENTITIES_WITH_RELATIONSHIPS_BATCH,
)

logger = logging.getLogger("nr_rel.entities")


@dataclass
class Node:
    guid: str
    name: str
    type: str
    entity_type: str
    tags: dict[str, list[str]] = field(default_factory=dict)
    system: str = "newrelic"  # "newrelic" or "aws" -- lets reports/graphs distinguish origin


@dataclass
class Edge:
    source_guid: str
    target_guid: str
    rel_type: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Graph:
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)

    def add_node(self, node: Node) -> None:
        self.nodes[node.guid] = node

    def add_edge(self, edge: Edge) -> None:
        # de-dupe identical edges
        for existing in self.edges:
            if (
                existing.source_guid == edge.source_guid
                and existing.target_guid == edge.target_guid
                and existing.rel_type == edge.rel_type
            ):
                return
        self.edges.append(edge)

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [
                {
                    "guid": n.guid,
                    "name": n.name,
                    "type": n.type,
                    "entity_type": n.entity_type,
                    "tags": n.tags,
                    "system": n.system,
                }
                for n in self.nodes.values()
            ],
            "edges": [
                {
                    "source": e.source_guid,
                    "target": e.target_guid,
                    "type": e.rel_type,
                    "metadata": e.metadata,
                }
                for e in self.edges
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Graph":
        g = cls()
        for n in data.get("nodes", []):
            g.add_node(
                Node(
                    n["guid"], n["name"], n["type"], n.get("entity_type", n["type"]),
                    n.get("tags", {}), n.get("system", "newrelic"),
                )
            )
        for e in data.get("edges", []):
            g.add_edge(Edge(e["source"], e["target"], e["type"], e.get("metadata", {})))
        return g


def _tags_to_list(raw_tags: Optional[list[dict[str, Any]]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for t in raw_tags or []:
        result[t["key"]] = t.get("values", [])
    return result


def search_entities_by_tag(
    client: NerdGraphClient, tag_query: str, max_results: int = 500
) -> list[Node]:
    """tag_query uses NRQL-like entity search syntax, e.g. "tags.team = 'payments'"
    or "tags.env = 'prod' AND tags.service = 'checkout'". You can also pass a
    bare NRQL-style clause combining name/type/tags per NerdGraph's entitySearch
    query language.
    """
    nodes: list[Node] = []
    cursor = None
    while True:
        variables = {"query": tag_query, "cursor": cursor}
        data = client.execute(ENTITY_SEARCH_BY_TAG, variables)
        search = data.get("actor", {}).get("entitySearch", {})
        results = search.get("results", {})
        for e in results.get("entities", []):
            nodes.append(
                Node(
                    guid=e["guid"],
                    name=e["name"],
                    type=e["type"],
                    entity_type=e.get("entityType", e["type"]),
                    tags=_tags_to_list(e.get("tags")),
                )
            )
        cursor = results.get("nextCursor")
        if not cursor or len(nodes) >= max_results:
            break
    logger.info("entitySearch('%s') matched %d entities", tag_query, len(nodes))
    return nodes[:max_results]


def expand_relationships(
    client: NerdGraphClient,
    seed_guids: list[str],
    depth: int = 1,
    batch_size: int = 25,
) -> Graph:
    """Starting from seed_guids, fetch each entity's relationships and follow
    them outward `depth` hops, merging everything into one Graph.
    """
    graph = Graph()
    frontier = list(dict.fromkeys(seed_guids))  # de-dup, preserve order
    visited: set[str] = set()

    for hop in range(depth + 1):
        if not frontier:
            break
        next_frontier: list[str] = []
        for i in range(0, len(frontier), batch_size):
            batch = frontier[i : i + batch_size]
            data = client.execute(ENTITIES_WITH_RELATIONSHIPS_BATCH, {"guids": batch})
            entities = data.get("actor", {}).get("entities", []) or []
            for e in entities:
                if e is None:
                    continue
                node = Node(
                    guid=e["guid"],
                    name=e["name"],
                    type=e["type"],
                    entity_type=e.get("entityType", e["type"]),
                    tags=_tags_to_list(e.get("tags")),
                )
                graph.add_node(node)
                visited.add(node.guid)

                for rel in e.get("relationships") or []:
                    src = rel.get("source", {}).get("entity")
                    tgt = rel.get("target", {}).get("entity")
                    if not src or not tgt:
                        continue
                    graph.add_node(
                        Node(src["guid"], src["name"], src["type"], src.get("entityType", src["type"]), {})
                    ) if src["guid"] not in graph.nodes else None
                    graph.add_node(
                        Node(tgt["guid"], tgt["name"], tgt["type"], tgt.get("entityType", tgt["type"]), {})
                    ) if tgt["guid"] not in graph.nodes else None
                    graph.add_edge(Edge(src["guid"], tgt["guid"], rel["type"]))

                    for candidate in (src["guid"], tgt["guid"]):
                        if candidate not in visited and candidate not in next_frontier:
                            next_frontier.append(candidate)
        frontier = next_frontier
        logger.info("Hop %d complete: %d nodes, %d edges so far", hop, len(graph.nodes), len(graph.edges))

    return graph
