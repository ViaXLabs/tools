#!/usr/bin/env python3
import argparse
import json
from typing import Any, Dict, List

from csv_utils import (
    write_check_report_csv,
    write_check_report_csv_wide_all,
    write_check_report_csv_wide_required,
)
from filter_utils import entity_matches_filters, load_filters
from log_utils import setup_logging
from tag_policy import evaluate_entity, load_policy


def _default_wide_all_name(path: str) -> str:
    if path.lower().endswith(".csv"):
        return path[:-4] + "_wide_all.csv"
    return path + "_wide_all.csv"


def _default_wide_required_name(path: str) -> str:
    if path.lower().endswith(".csv"):
        return path[:-4] + "_wide_required.csv"
    return path + "_wide_required.csv"


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Dry-run checker.\n"
            "Outputs:\n"
            "  - JSON report\n"
            "  - Normal CSV (current tags + would-be tags JSON)\n"
            "  - Wide CSV (REQUIRED tags only)\n"
            "  - Wide CSV (ALL tags, required columns first)\n"
        )
    )
    parser.add_argument("--in", dest="in_path", required=True, help="Input JSON from export_newrelic_entity_tags.py")
    parser.add_argument("--policy", required=True, help="tag_policy.json path")
    parser.add_argument("--filters", type=str, default=None, help="Optional filters.json path (review only subset)")

    parser.add_argument("--out-json", required=True, help="Output report JSON path")
    parser.add_argument("--out-csv", required=True, help="Output report CSV path (normal)")

    parser.add_argument("--out-csv-wide-required", default=None, help="Output wide REQUIRED CSV path")
    parser.add_argument("--out-csv-wide-all", default=None, help="Output wide ALL CSV path")

    parser.add_argument("--only-action-needed", action="store_true", help="Only include entities that need attention")
    parser.add_argument(
        "--propose-replacements",
        action="store_true",
        help="Opt-in: propose REPLACE for invalid tags. Default is ADD missing only.",
    )

    parser.add_argument("--log-file", type=str, default=None)
    parser.add_argument("--verbose", action="store_true")

    args = parser.parse_args()
    logger = setup_logging(args.log_file, verbose=args.verbose)

    wide_required_path = args.out_csv_wide_required or _default_wide_required_name(args.out_csv)
    wide_all_path = args.out_csv_wide_all or _default_wide_all_name(args.out_csv)

    policy = load_policy(args.policy)
    logger.info(f"Loaded policy: {args.policy}")
    logger.info(f"Propose replacements: {args.propose_replacements}")

    with open(args.in_path, "r", encoding="utf-8") as f:
        exported = json.load(f)

    entities: List[Dict[str, Any]] = exported.get("entities") or []
    logger.info(f"Loaded entities from export: {len(entities)}")

    flt = load_filters(args.filters)
    if flt is not None:
        before = len(entities)
        entities = [e for e in entities if entity_matches_filters(e, flt)]
        logger.info(f"Applied filters for review: {args.filters} (kept {len(entities)} / {before})")

    report_entries: List[Dict[str, Any]] = []
    action_needed_count = 0

    for ent in entities:
        entry = evaluate_entity(ent, policy, propose_replacements=args.propose_replacements)

        if entry["action_needed"]:
            action_needed_count += 1
            add_map = (entry.get("proposed") or {}).get("add") or {}
            rep_map = (entry.get("proposed") or {}).get("replace") or {}
            if add_map or rep_map:
                logger.info(f"[PROPOSE] {entry.get('name')} ({entry.get('guid')}) ADD={add_map} REPLACE={rep_map}")
            else:
                logger.info(
                    f"[FLAG] {entry.get('name')} ({entry.get('guid')}) "
                    f"missing={entry.get('missing')} invalid={len(entry.get('invalid') or [])}"
                )

        if args.only_action_needed and not entry["action_needed"]:
            continue

        report_entries.append(entry)

    report = {
        "source": args.in_path,
        "policy": args.policy,
        "filters": args.filters,
        "total_entities_considered": len(entities),
        "entities_in_report": len(report_entries),
        "action_needed": action_needed_count,
        "propose_replacements": bool(args.propose_replacements),
        "entries": report_entries,
    }

    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    write_check_report_csv(args.out_csv, report_entries)
    write_check_report_csv_wide_required(wide_required_path, report_entries, policy)
    write_check_report_csv_wide_all(wide_all_path, report_entries, policy)

    logger.info(f"Wrote JSON report:           {args.out_json}")
    logger.info(f"Wrote CSV report:            {args.out_csv}")
    logger.info(f"Wrote WIDE REQUIRED CSV:     {wide_required_path}")
    logger.info(f"Wrote WIDE ALL CSV:          {wide_all_path}")
    logger.info(f"Action needed: {action_needed_count} (out of {len(entities)})")


if __name__ == "__main__":
    main()
