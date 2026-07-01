#!/usr/bin/env python3
"""
diagnose_newrelic.py — New-Relic-side diagnostic for an AWS CloudWatch
Metric Stream integration.

Confirms (via NerdGraph):
  - the AWS account is LINKED in New Relic (+ per-integration status)
  - metric-stream data is landing in NRDB
  - which namespaces / stream ARNs arrive, and ingest freshness

Requires: requests  (pip install requests).  Python 3.8+.
Read-only: makes no changes to New Relic.

Usage:
    export NR_API_KEY="NRAK-xxxx"     # USER key, not a license/ingest key
    export NR_ACCOUNT_ID="1234567"
    export NR_REGION="US"             # US or EU (default US)
    ./diagnose_newrelic.py
  (or pass --api-key / --account-id / --region)

Exit codes:  0 healthy · 2 broken (problem found) · 3 error (couldn't run)
"""

import argparse
import os
import sys
from datetime import datetime, timezone

# ---------- presentation ----------

class C:
    BOLD = "\033[1m"; DIM = "\033[2m"; RST = "\033[0m"
    G = "\033[32m"; R = "\033[31m"; Y = "\033[33m"; B = "\033[36m"

def _supports_color() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

_COLOR = _supports_color()

def _c(code: str) -> str:
    return code if _COLOR else ""

def ok(msg):   print(f"   {_c(C.G)}\u2713{_c(C.RST)} {msg}")
def bad(msg):  print(f"   {_c(C.R)}\u2717{_c(C.RST)} {msg}")
def warn(msg): print(f"   {_c(C.Y)}!{_c(C.RST)} {msg}")
def info(msg): print(f"     {_c(C.DIM)}{msg}{_c(C.RST)}")
def kv(k, v):  print(f"     {k:<26} {v}")
def section(title):
    print(f"\n{_c(C.B)}{_c(C.BOLD)}== {title} =={_c(C.RST)}")
def header(title):
    print(f"\n{_c(C.BOLD)}{_c(C.B)}  {title}{_c(C.RST)}")

# =====================================================================
def diagnose_nr(api_key: str, account_id: str, region: str) -> str:
    """Returns a status: 'healthy', 'broken', or 'error' (couldn't run)."""
    try:
        import requests
    except ImportError:
        bad("requests not installed. Run: pip install requests")
        return "error"

    gql_url = ("https://api.eu.newrelic.com/graphql" if region.upper() == "EU"
               else "https://api.newrelic.com/graphql")

    def gql(document: str):
        try:
            resp = requests.post(
                gql_url,
                headers={"Content-Type": "application/json", "API-Key": api_key},
                json={"query": document}, timeout=30,
            )
            return resp.json()
        except requests.RequestException as e:
            return {"errors": [{"message": str(e)}]}

    def nrql(query: str):
        # No manual escaping needed — json= handles it.
        doc = (f'{{ actor {{ account(id: {account_id}) '
               f'{{ nrql(query: {_gql_str(query)}) {{ results }} }} }} }}')
        return gql(doc)

    verdict = {"linked": False, "data": False}

    if not str(account_id).isdigit():
        bad(f"NR_ACCOUNT_ID '{account_id}' is not numeric. Expected a numeric account id.")
        return "error"

    header("New Relic Setup & Data Checker")
    kv("Account", account_id)
    kv("Region", region)
    kv("Endpoint", gql_url)

    # --- 0. key sanity ---
    section("0 - API key / access")
    who = gql("{ actor { user { name email } } }")
    if "errors" in who:
        bad("NerdGraph error:")
        for e in who["errors"]:
            print(f"       {e.get('message')}")
        info("Ensure NR_API_KEY is a USER key (NRAK-) and NR_REGION matches the account.")
        return "error"
    user = who.get("data", {}).get("actor", {}).get("user", {})
    kv("User", user.get("name", "?"))
    kv("Email", user.get("email", "?"))
    ok("Authenticated.")

    # --- 1. linked accounts ---
    section("1 - Linked AWS accounts (link_account step)")
    linked = gql(f"{{ actor {{ account(id: {account_id}) {{ cloud "
                 f"{{ linkedAccounts {{ id name createdAt integrations {{ name }} }} }} }} }} }}")
    if "errors" in linked:
        bad("NerdGraph error:")
        for e in linked["errors"]:
            print(f"       {e.get('message')}")
    else:
        accounts = (linked.get("data", {}).get("actor", {}).get("account", {})
                    .get("cloud", {}).get("linkedAccounts", []) or [])
        if not accounts:
            bad("No linked AWS accounts. The link_account resource never registered.")
            info("Nothing will flow until it does - re-apply and verify role ARN + external id.")
        else:
            verdict["linked"] = True
            ok(f"Found {len(accounts)} linked account(s):")
            for a in accounts:
                integ = ", ".join(i["name"] for i in a.get("integrations", [])) or "none"
                print(f"       [{a['id']}] {a['name']}  (created {a['createdAt']})")
                print(f"         integrations: {integ}")

    # --- 2. data in NRDB ---
    section("2 - Metric-stream data in NRDB (last 30 min)")
    r = nrql("FROM Metric SELECT count(*) WHERE collector.name = "
             "'cloudwatch-metric-streams' SINCE 30 minutes ago")
    cnt = _nrql_first(r, "count", 0)
    if cnt is None:
        bad("Query error:")
        for e in r.get("errors", []):
            print(f"       {e.get('message')}")
    else:
        kv("Data points", str(cnt))
        if cnt > 0:
            ok("Data IS arriving from a metric stream.")
            verdict["data"] = True
        else:
            bad("ZERO metric-stream data points in NRDB.")

    # --- 3. namespaces ---
    section("3 - Namespaces arriving (last 1h)")
    r = nrql("FROM Metric SELECT uniques(aws.Namespace) WHERE collector.name = "
             "'cloudwatch-metric-streams' SINCE 1 hour ago")
    results = _nrql_results(r)
    namespaces = results[0].get("uniques.aws.Namespace", []) if results else []
    if namespaces:
        for ns in namespaces:
            print(f"       - {ns}")
        ok(f"{len(namespaces)} namespace(s) flowing.")
    else:
        warn("No namespaces - check include/exclude filters on the metric stream.")

    # --- 4. stream ARNs ---
    section("4 - Source stream ARNs (last 1h)")
    r = nrql("FROM Metric SELECT count(*) WHERE collector.name = "
             "'cloudwatch-metric-streams' FACET aws.MetricStreamArn SINCE 1 hour ago")
    results = _nrql_results(r)
    if results:
        for row in results:
            arn = row.get("aws.MetricStreamArn", "unknown")
            print(f"       {arn}: {row.get('count', 0)}")
    else:
        warn("No stream ARNs found.")

    # --- 5. freshness ---
    section("5 - Ingest trend (per 5 min, last 30 min)")
    r = nrql("FROM Metric SELECT count(*) WHERE collector.name = "
             "'cloudwatch-metric-streams' TIMESERIES 5 minutes SINCE 30 minutes ago")
    results = _nrql_results(r)
    if results:
        for row in results[-6:]:
            begin = row.get("beginTimeSeconds")
            # NerdGraph returns beginTimeSeconds in epoch SECONDS. Guard against
            # a millisecond value sneaking in (would yield a year-56000 date).
            if begin and begin > 1e11:
                begin = begin / 1000.0
            ts = (datetime.fromtimestamp(begin, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                  if begin else "?")
            print(f"       {ts}  {row.get('count', 0)}")
    else:
        warn("No timeseries data.")

    # --- verdict ---
    section("VERDICT")
    if not verdict["linked"]:
        bad("AWS account is NOT linked in New Relic - fix the link_account resource first.")
        return "broken"
    elif verdict["data"]:
        ok("Linked AND receiving data. New Relic side is healthy.")
        return "healthy"
    else:
        bad("Account linked but NO data arriving. Cross-check with the 'aws' subcommand:")
        info("AWS DeliveryToHttpEndpoint.Success > 0 but NR = 0 -> wrong account/key/region.")
        info("S3 backup bucket has objects -> NR rejected the data (read those objects).")
        return "broken"

# ---------- NerdGraph parsing helpers ----------

def _gql_str(s: str) -> str:
    """Return a GraphQL-safe double-quoted string literal."""
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'

def _nrql_results(resp):
    try:
        return resp["data"]["actor"]["account"]["nrql"]["results"]
    except (KeyError, TypeError):
        return None

def _nrql_first(resp, field, default=None):
    results = _nrql_results(resp)
    if results is None:
        return None
    if not results:
        return default
    return results[0].get(field, default)


# =====================================================================
# CLI
# =====================================================================

def main():
    p = argparse.ArgumentParser(
        description="New-Relic-side diagnostic for an AWS metric stream integration")
    p.add_argument("--api-key", default=os.environ.get("NR_API_KEY"))
    p.add_argument("--account-id", default=os.environ.get("NR_ACCOUNT_ID"))
    p.add_argument("--region", default=os.environ.get("NR_REGION", "US"))
    args = p.parse_args()

    if not args.api_key or not args.account_id:
        bad("Missing NR credentials. Set NR_API_KEY and NR_ACCOUNT_ID (or pass --api-key/--account-id).")
        sys.exit(3)

    status = diagnose_nr(args.api_key, args.account_id, args.region)
    sys.exit({"healthy": 0, "broken": 2, "error": 3}.get(status, 3))

if __name__ == "__main__":
    main()
