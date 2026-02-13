#!/usr/bin/env python3
import argparse
import json
import os
from typing import Any, Dict, List, Optional

from filter_utils import entity_matches_filters, load_filters
from log_utils import setup_logging
from nr_nerdgraph import NerdGraphClient


ENTITY_SEARCH_QUERY = """
query($query: String!, $cursor: String) {
  actor {
    entitySearch(query: $query) {
      results(cursor: $cursor) {
        entities {
          guid
          name
          domain
          entityType
          type
          tags {
            key
            values
          }
        }
        nextCursor
      }
    }
  }
}
"""


def fetch_entities_with_tags(
    client: NerdGraphClient,
    query: str,
    *,
    limit_pages: Optional[int] = None,
    logger=None,
) -> List[Dict[str, Any]]:
    all_entities: List[Dict[str, Any]] = []
    cursor = None
    pages = 0

    while True:
        pages += 1
        if logger:
            logger.info(f"Fetching page {pages} (cursor={'set' if cursor else 'none'})")

        resp = client.graphql(ENTITY_SEARCH_QUERY, {"query": query, "cursor": cursor})
        results = resp.get("data", {}).get("actor", {}).get("entitySearch", {}).get("results", {})

        entities = results.get("entities") or []
        all_entities.extend(entities)

        cursor = results.get("nextCursor")
        if not cursor:
            break
        if limit_pages is not None and pages >= limit_pages:
            break

    return all_entities


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Export New Relic entities + tags to JSON.\n"
            "Default query = everything in the account.\n"
            "You can pass --account-id or set NR_ACCOUNT_ID."
        )
    )
    parser.add_argument("--account-id", type=int, required=False, default=None, help="Account ID (or set NR_ACCOUNT_ID)")
    parser.add_argument("--query", type=str, default=None, help="Custom entitySearch query (advanced)")
    parser.add_argument("--out", type=str, required=True, help="Output JSON path")
    parser.add_argument("--limit-pages", type=int, default=None, help="Stop after N pages (debug)")
    parser.add_argument("--filters", type=str, default=None, help="Optional filters.json path")

    parser.add_argument("--log-file", type=str, default=None, help="Optional log file path")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")

    args = parser.parse_args()
    logger = setup_logging(args.log_file, verbose=args.verbose)

    api_key = os.environ.get("NR_API_KEY")
    if not api_key:
        raise SystemExit("ERROR: NR_API_KEY env var not set")

    account_id = args.account_id
    if account_id is None:
        env_acct = os.environ.get("NR_ACCOUNT_ID")
        if env_acct and env_acct.strip().isdigit():
            account_id = int(env_acct.strip())

    if account_id is None and not args.query:
        raise SystemExit("ERROR: Provide --account-id or set NR_ACCOUNT_ID (or provide --query).")

    q = args.query or f"accountId = {account_id}"
    logger.info(f"Export query: {q}")

    client = NerdGraphClient(api_key=api_key)
    entities = fetch_entities_with_tags(client, q, limit_pages=args.limit_pages, logger=logger)

    flt = load_filters(args.filters)
    if flt is not None:
        before = len(entities)
        entities = [e for e in entities if entity_matches_filters(e, flt)]
        logger.info(f"Applied filters: {args.filters} (kept {len(entities)} / {before})")

    payload = {"account_id": account_id, "query": q, "count": len(entities), "entities": entities}

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=False)

    logger.info(f"Wrote {len(entities)} entities to {args.out}")


if __name__ == "__main__":
    main()
