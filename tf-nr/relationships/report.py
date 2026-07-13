"""
nr-rel: query, report on, and (carefully) edit New Relic entity
relationships via NerdGraph.

Every subcommand logs to outputs/logs/. Discovery data goes to
outputs/data/. Reports go to outputs/reports/. Change plans and apply
results go to outputs/changes/.

Run `python -m src.cli <subcommand> --help` for details on any command.
"""
from __future__ import annotations

import argparse
import json
import sys

from dotenv import load_dotenv

from .entities import Graph, expand_relationships, search_entities_by_tag
from .logging_utils import DATA_DIR, ensure_output_dirs, setup_logger, timestamp
from .nerdgraph_client import NerdGraphClient, NerdGraphError
from .queries import INTROSPECT_TYPE
from .relationships import ChangeItem, apply_plan, describe_plan, load_plan, write_plan, write_results
from .report import render_report
from .suggest import suggest_missing_relationships
from .aws_client import AwsResource, KIND_FETCHERS, discover as aws_discover
from .matcher import match_resources, merge_into_graph, load_rules


def _client() -> NerdGraphClient:
    load_dotenv()
    return NerdGraphClient.from_env()


def cmd_discover(args: argparse.Namespace) -> int:
    logger = setup_logger("discover")
    ensure_output_dirs()
    try:
        client = _client()
    except NerdGraphError as exc:
        logger.error(str(exc))
        return 1

    logger.info("Searching entities matching: %s", args.query)
    try:
        seeds = search_entities_by_tag(client, args.query, max_results=args.max_seeds)
    except NerdGraphError as exc:
        logger.error("Entity search failed: %s", exc)
        return 1

    if not seeds:
        logger.warning("No entities matched that query. Nothing to expand.")
        graph = Graph()
    else:
        seed_guids = [n.guid for n in seeds]
        try:
            graph = expand_relationships(client, seed_guids, depth=args.depth)
        except NerdGraphError as exc:
            logger.error("Relationship expansion failed: %s", exc)
            return 1

    out_path = DATA_DIR / f"graph_{timestamp()}.json"
    out_path.write_text(json.dumps({"query": args.query, **graph.to_dict()}, indent=2), encoding="utf-8")
    logger.info(
        "Discovery complete: %d entities, %d relationships. Saved to %s",
        len(graph.nodes), len(graph.edges), out_path,
    )
    logger.info("Next: nr-rel report --graph %s", out_path)
    return 0


def _load_graph_arg(args: argparse.Namespace, logger) -> tuple[Graph, str]:
    """Load a graph either from a saved --graph file or by running a fresh
    --query search + expand. Returns (graph, query_label)."""
    if args.graph:
        data = json.loads(open(args.graph, encoding="utf-8").read())
        query_label = data.get("query", "(loaded from file)")
        return Graph.from_dict(data), query_label

    client = _client()
    seeds = search_entities_by_tag(client, args.query, max_results=args.max_seeds)
    graph = expand_relationships(client, [n.guid for n in seeds], depth=args.depth) if seeds else Graph()
    return graph, args.query


def cmd_report(args: argparse.Namespace) -> int:
    logger = setup_logger("report")
    try:
        graph, query_label = _load_graph_arg(args, logger)
    except (NerdGraphError, FileNotFoundError) as exc:
        logger.error(str(exc))
        return 1

    suggestions = suggest_missing_relationships(graph) if args.suggest else None
    path = render_report(graph, query_used=query_label, title=args.title, suggestions=suggestions)
    logger.info("Report ready: %s", path)
    return 0


def cmd_suggest(args: argparse.Namespace) -> int:
    logger = setup_logger("suggest")
    try:
        graph, query_label = _load_graph_arg(args, logger)
    except (NerdGraphError, FileNotFoundError) as exc:
        logger.error(str(exc))
        return 1

    suggestions = suggest_missing_relationships(graph)
    logger.info("Generated %d suggestion(s) based on shared tags.", len(suggestions))
    for s in suggestions:
        logger.info(
            "[%s] %s -> %s  (%s)  reason: %s",
            s.confidence, s.source_name, s.target_name, s.suggested_type, s.reason,
        )
    if args.html:
        path = render_report(graph, query_used=query_label, title="Suggestions", suggestions=suggestions)
        logger.info("Suggestions report: %s", path)
    return 0


def cmd_aws_discover(args: argparse.Namespace) -> int:
    logger = setup_logger("aws-discover")
    ensure_output_dirs()
    kinds = [k.strip() for k in args.kinds.split(",") if k.strip()]
    regions = [r.strip() for r in args.regions.split(",") if r.strip()]

    unknown = [k for k in kinds if k not in KIND_FETCHERS]
    if unknown:
        logger.error("Unknown kind(s): %s. Known kinds: %s", unknown, list(KIND_FETCHERS))
        return 1

    logger.info("Discovering AWS resources: kinds=%s regions=%s profile=%s", kinds, regions, args.profile or "(default)")
    try:
        resources = aws_discover(kinds, regions, profile=args.profile)
    except Exception as exc:  # noqa: BLE001
        logger.error("AWS discovery failed: %s", exc)
        return 1

    out_path = DATA_DIR / f"aws_inventory_{timestamp()}.json"
    out_path.write_text(
        json.dumps({"kinds": kinds, "regions": regions, "resources": [r.to_dict() for r in resources]}, indent=2),
        encoding="utf-8",
    )
    logger.info("Discovered %d AWS resource(s). Saved to %s", len(resources), out_path)
    logger.info("Next: nr-rel match --graph <nr graph.json> --aws-inventory %s", out_path)
    return 0


def cmd_match(args: argparse.Namespace) -> int:
    logger = setup_logger("match")
    try:
        nr_graph, query_label = _load_graph_arg(args, logger)
    except (NerdGraphError, FileNotFoundError) as exc:
        logger.error("Could not load New Relic graph: %s", exc)
        return 1

    try:
        aws_data = json.loads(open(args.aws_inventory, encoding="utf-8").read())
    except FileNotFoundError as exc:
        logger.error(str(exc))
        return 1
    aws_resources = [AwsResource.from_dict(r) for r in aws_data.get("resources", [])]

    rules = load_rules(args.rules) if args.rules else load_rules()
    results = match_resources(aws_resources, list(nr_graph.nodes.values()), rules=rules, fuzzy_threshold=args.threshold)

    if args.unmatched_only:
        to_show = [r for r in results if r.confidence == "none"]
    else:
        to_show = results
    for r in to_show:
        logger.info(
            "[%s] %s '%s' -> %s  (score=%.2f)  %s",
            r.confidence, r.aws_resource.kind, r.aws_resource.id,
            r.nr_node.name if r.nr_node else "NO MATCH", r.score, r.matched_on,
        )

    results_path = DATA_DIR / f"match_{timestamp()}.json"
    results_path.write_text(json.dumps([r.to_dict() for r in results], indent=2), encoding="utf-8")
    logger.info("Full match results written to %s", results_path)

    if args.report:
        merge_into_graph(nr_graph, results)
        report_path = render_report(
            nr_graph, query_used=query_label, title="AWS <-> New Relic Reconciliation",
            aws_matches=results,
        )
        logger.info("Combined report: %s", report_path)

    n_unmatched = sum(1 for r in results if r.confidence == "none")
    return 1 if n_unmatched and args.fail_on_unmatched else 0


def cmd_plan_add(args: argparse.Namespace) -> int:
    logger = setup_logger("plan-add")
    item = ChangeItem(
        action="add", source_guid=args.source, target_guid=args.target,
        rel_type=args.type, reason=args.reason or "",
    )
    path = write_plan([item], note=args.note or "")
    logger.info("Plan written to %s -- review it, then run:\n  nr-rel apply --plan %s", path, path)
    return 0


def cmd_plan_remove(args: argparse.Namespace) -> int:
    logger = setup_logger("plan-remove")
    item = ChangeItem(
        action="remove", source_guid=args.source, target_guid=args.target,
        rel_type=args.type, reason=args.reason or "",
    )
    path = write_plan([item], note=args.note or "")
    logger.info("Plan written to %s -- review it, then run:\n  nr-rel apply --plan %s", path, path)
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    logger = setup_logger("apply")
    plan = load_plan(args.plan)
    print(describe_plan(plan))

    if not args.yes:
        answer = input("\nApply this plan against New Relic now? Type 'yes' to continue: ")
        if answer.strip().lower() != "yes":
            logger.info("Aborted by user -- no changes made.")
            return 1

    try:
        client = _client()
    except NerdGraphError as exc:
        logger.error(str(exc))
        return 1

    results = apply_plan(client, plan, dry_run=args.dry_run)
    results_path = write_results(results)

    n_ok = sum(1 for r in results if r.get("status") == "success")
    n_err = sum(1 for r in results if r.get("status") in ("error", "exception"))
    logger.info("Apply complete: %d succeeded, %d failed. Details: %s", n_ok, n_err, results_path)
    return 1 if n_err else 0


def cmd_schema(args: argparse.Namespace) -> int:
    logger = setup_logger("schema")
    try:
        client = _client()
    except NerdGraphError as exc:
        logger.error(str(exc))
        return 1
    data = client.execute(INTROSPECT_TYPE, {"name": args.type_name})
    type_info = data.get("__type")
    if not type_info:
        logger.warning("No type named %s found in the schema.", args.type_name)
        return 1
    print(json.dumps(type_info, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nr-rel", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("discover", help="Find entities by tag and walk their relationships")
    p.add_argument("--query", required=True, help="entitySearch query, e.g. \"tags.team = 'payments'\"")
    p.add_argument("--depth", type=int, default=1, help="hops to expand from the matched entities (default 1)")
    p.add_argument("--max-seeds", type=int, default=500, help="cap on directly-matched entities")
    p.set_defaults(func=cmd_discover)

    p = sub.add_parser("report", help="Render an HTML relationship report")
    p.add_argument("--graph", help="path to a saved graph JSON from `discover`")
    p.add_argument("--query", help="or: run a fresh search (see `discover --query`)")
    p.add_argument("--depth", type=int, default=1)
    p.add_argument("--max-seeds", type=int, default=500)
    p.add_argument("--title", default="Relationship Report")
    p.add_argument("--suggest", action="store_true", help="include heuristic suggestions in the report")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("suggest", help="Print (and optionally render) tag-based relationship suggestions")
    p.add_argument("--graph", help="path to a saved graph JSON from `discover`")
    p.add_argument("--query", help="or: run a fresh search")
    p.add_argument("--depth", type=int, default=1)
    p.add_argument("--max-seeds", type=int, default=500)
    p.add_argument("--html", action="store_true", help="also render an HTML report of the suggestions")
    p.set_defaults(func=cmd_suggest)

    p = sub.add_parser("aws-discover", help="Query AWS (ECS/EKS/RDS, extensible) for resources to reconcile against New Relic")
    p.add_argument(
        "--kinds", default="ecs-clusters,ecs-services,eks-clusters,rds-instances,rds-clusters",
        help=f"comma-separated list of: {', '.join(KIND_FETCHERS)}",
    )
    p.add_argument("--regions", required=True, help="comma-separated AWS regions, e.g. us-east-1,us-west-2")
    p.add_argument("--profile", help="AWS named profile (uses default credential chain if omitted)")
    p.set_defaults(func=cmd_aws_discover)

    p = sub.add_parser("match", help="Reconcile AWS resources with New Relic entities by name/tag, despite naming differences")
    p.add_argument("--graph", help="path to a saved NR graph JSON from `discover`")
    p.add_argument("--query", help="or: run a fresh NR search")
    p.add_argument("--depth", type=int, default=1)
    p.add_argument("--max-seeds", type=int, default=500)
    p.add_argument("--aws-inventory", required=True, help="path to an AWS inventory JSON from `aws-discover`")
    p.add_argument("--rules", help="path to a custom match rules YAML (default: config/aws_match_rules.yaml)")
    p.add_argument("--threshold", type=float, default=0.82, help="fuzzy-match score cutoff, 0-1 (default 0.82)")
    p.add_argument("--unmatched-only", action="store_true", help="only log resources that didn't match anything")
    p.add_argument("--report", action="store_true", help="render a combined HTML report with matches overlaid")
    p.add_argument("--fail-on-unmatched", action="store_true", help="exit 1 if any AWS resource went unmatched (useful in CI)")
    p.set_defaults(func=cmd_match)

    p = sub.add_parser("plan-add", help="Stage adding a relationship (writes a plan, makes no changes)")
    p.add_argument("--source", required=True, help="source entity GUID")
    p.add_argument("--target", required=True, help="target entity GUID")
    p.add_argument("--type", required=True, help="relationship type, e.g. CONTAINS, RELATED_TO")
    p.add_argument("--reason", help="why -- shown in the review output")
    p.add_argument("--note", help="free-text note stored on the plan")
    p.set_defaults(func=cmd_plan_add)

    p = sub.add_parser("plan-remove", help="Stage removing a relationship (writes a plan, makes no changes)")
    p.add_argument("--source", required=True)
    p.add_argument("--target", required=True)
    p.add_argument("--type", required=True)
    p.add_argument("--reason", help="why -- shown in the review output")
    p.add_argument("--note", help="free-text note stored on the plan")
    p.set_defaults(func=cmd_plan_remove)

    p = sub.add_parser("apply", help="Review and execute a change plan against New Relic")
    p.add_argument("--plan", required=True, help="path to a plan JSON from plan-add/plan-remove")
    p.add_argument("--yes", action="store_true", help="skip the interactive confirmation prompt")
    p.add_argument(
        "--dry-run", action="store_true",
        help="print what would happen without calling NerdGraph (default is dry-run OFF -- this really applies)",
    )
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("schema", help="Introspect a NerdGraph type -- verify field names before scripting")
    p.add_argument("type_name", help="e.g. Entity, EntityRelationship, EntitySearch")
    p.set_defaults(func=cmd_schema)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
