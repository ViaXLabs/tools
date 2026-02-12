#!/usr/bin/env python3
import argparse
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from csv_utils import write_apply_log_csv
from filter_utils import entity_matches_filters, load_filters
from log_utils import setup_logging
from nr_nerdgraph import NerdGraphClient


MUTATION_ADD_TAGS = """
mutation($guid: EntityGuid!, $tags: [TaggingTagInput!]!) {
  taggingAddTagsToEntity(guid: $guid, tags: $tags) {
    errors { message type }
  }
}
"""

MUTATION_REPLACE_TAGS = """
mutation($guid: EntityGuid!, $tags: [TaggingTagInput!]!) {
  taggingReplaceTagsOnEntity(guid: $guid, tags: $tags) {
    errors { message type }
  }
}
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_tag_inputs(tag_map: Dict[str, List[str]]) -> List[Dict[str, Any]]:
    return [{"key": k, "values": vals} for k, vals in tag_map.items()]


def extract_proposed(entry: Dict[str, Any]) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    proposed = entry.get("proposed") or {}
    return proposed.get("add") or {}, proposed.get("replace") or {}


def fail_if_errors(obj: Dict[str, Any], path: List[str]) -> None:
    cur: Any = obj
    for p in path:
        cur = cur.get(p, {})
    errors = cur.get("errors") if isinstance(cur, dict) else None
    if errors:
        raise RuntimeError(f"Mutation returned errors: {errors}")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Apply proposed changes from tag_report.json.\n"
            "Default: apply ADDs only.\n"
            "Always writes CSV apply_log showing DRY_RUN or OK/ERROR."
        )
    )
    parser.add_argument("--report", required=True, help="tag_report.json from checker")
    parser.add_argument("--policy", required=True, help="tag_policy.json (protected_keys enforced)")
    parser.add_argument("--filters", type=str, default=None, help="Optional filters.json path (apply only subset)")

    parser.add_argument("--dry-run", action="store_true", help="No NerdGraph calls; just log actions")
    parser.add_argument("--allow-replace", action="store_true", help="Opt-in: allow applying REPLACE actions")

    parser.add_argument("--only-guids", default=None, help="Comma-separated GUIDs to apply (optional)")
    parser.add_argument("--max", type=int, default=None, help="Max entities to process (optional)")

    parser.add_argument("--out-csv", required=True, help="Apply log CSV output path")
    parser.add_argument("--log-file", type=str, default=None)
    parser.add_argument("--verbose", action="store_true")

    args = parser.parse_args()
    logger = setup_logging(args.log_file, verbose=args.verbose)

    if not args.dry_run and not os.environ.get("NR_API_KEY"):
        raise SystemExit("ERROR: NR_API_KEY env var not set (required unless --dry-run)")

    with open(args.policy, "r", encoding="utf-8") as f:
        policy = json.load(f)
    protected = set(policy.get("protected_keys") or [])

    with open(args.report, "r", encoding="utf-8") as f:
        report = json.load(f)
    entries: List[Dict[str, Any]] = report.get("entries") or []

    guid_filter = None
    if args.only_guids:
        guid_filter = set([g.strip() for g in args.only_guids.split(",") if g.strip()])

    flt = load_filters(args.filters)
    client = NerdGraphClient() if not args.dry_run else None

    apply_rows: List[Dict[str, Any]] = []
    processed = 0

    for entry in entries:
        if not entry.get("action_needed"):
            continue

        guid = entry.get("guid")
        name = entry.get("name")

        if guid_filter is not None and guid not in guid_filter:
            continue
        if flt is not None and not entity_matches_filters(entry, flt):
            continue

        add_map, rep_map = extract_proposed(entry)

        add_map = {k: v for k, v in add_map.items() if k not in protected}
        rep_map = {k: v for k, v in rep_map.items() if k not in protected}

        if not args.allow_replace:
            rep_map = {}

        if not add_map and not rep_map:
            continue

        logger.info(f"Entity: {name} ({guid})")
        if add_map:
            logger.info(f"  ADD: {add_map}")
        if rep_map:
            logger.info(f"  REPLACE: {rep_map}")

        for k, vals in add_map.items():
            if args.dry_run:
                apply_rows.append(
                    {
                        "timestamp": now_iso(),
                        "guid": guid,
                        "name": name,
                        "action": "ADD",
                        "key": k,
                        "values": json.dumps(vals),
                        "result": "DRY_RUN",
                        "error": "",
                    }
                )
                continue

            try:
                resp = client.graphql(MUTATION_ADD_TAGS, {"guid": guid, "tags": to_tag_inputs({k: vals})})
                fail_if_errors(resp.get("data", {}) or {}, ["taggingAddTagsToEntity"])
                apply_rows.append(
                    {
                        "timestamp": now_iso(),
                        "guid": guid,
                        "name": name,
                        "action": "ADD",
                        "key": k,
                        "values": json.dumps(vals),
                        "result": "OK",
                        "error": "",
                    }
                )
            except Exception as e:
                logger.error(f"  ERROR adding {k}={vals}: {e}")
                apply_rows.append(
                    {
                        "timestamp": now_iso(),
                        "guid": guid,
                        "name": name,
                        "action": "ADD",
                        "key": k,
                        "values": json.dumps(vals),
                        "result": "ERROR",
                        "error": str(e),
                    }
                )

        for k, vals in rep_map.items():
            if args.dry_run:
                apply_rows.append(
                    {
                        "timestamp": now_iso(),
                        "guid": guid,
                        "name": name,
                        "action": "REPLACE",
                        "key": k,
                        "values": json.dumps(vals),
                        "result": "DRY_RUN",
                        "error": "",
                    }
                )
                continue

            try:
                resp = client.graphql(MUTATION_REPLACE_TAGS, {"guid": guid, "tags": to_tag_inputs({k: vals})})
                fail_if_errors(resp.get("data", {}) or {}, ["taggingReplaceTagsOnEntity"])
                apply_rows.append(
                    {
                        "timestamp": now_iso(),
                        "guid": guid,
                        "name": name,
                        "action": "REPLACE",
                        "key": k,
                        "values": json.dumps(vals),
                        "result": "OK",
                        "error": "",
                    }
                )
            except Exception as e:
                logger.error(f"  ERROR replacing {k}={vals}: {e}")
                apply_rows.append(
                    {
                        "timestamp": now_iso(),
                        "guid": guid,
                        "name": name,
                        "action": "REPLACE",
                        "key": k,
                        "values": json.dumps(vals),
                        "result": "ERROR",
                        "error": str(e),
                    }
                )

        processed += 1
        if args.max is not None and processed >= args.max:
            break

    write_apply_log_csv(args.out_csv, apply_rows)
    logger.info(f"Wrote apply log CSV: {args.out_csv}")
    logger.info(f"Entities processed: {processed}")
    logger.info(f"Rows written: {len(apply_rows)}")


if __name__ == "__main__":
    main()
