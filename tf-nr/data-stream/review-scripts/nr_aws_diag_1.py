#!/usr/bin/env python3
"""
nr_aws_diag.py — New Relic <- AWS Metric Stream diagnostics.

Walks the data path and prints a per-hop report with a verdict:

    CloudWatch -> Metric Stream -> Firehose -> NR endpoint -> NRDB

Subcommands:
    aws   : checks up to the handoff to New Relic (boto3)
    nr    : checks the New Relic side via NerdGraph (requests)
    all   : run both

Requires: boto3 (aws), requests (nr).  Python 3.8+.

Examples:
    ./nr_aws_diag.py aws --name prod --region us-east-1
    NR_API_KEY=NRAK-xxx NR_ACCOUNT_ID=1234567 NR_REGION=US ./nr_aws_diag.py nr
    ./nr_aws_diag.py all --name prod --region us-east-1
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

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

# ---------- helpers ----------

def _window(hours=1):
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    return start, end

# =====================================================================
# AWS SIDE
# =====================================================================

def diagnose_aws(name: str, region: str) -> str:
    """Returns a status: 'healthy', 'broken', or 'error' (couldn't run)."""
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        bad("boto3 not installed. Run: pip install boto3")
        return "error"

    stream_name = f"newrelic-metric-stream-{name}"
    firehose_name = f"newrelic_firehose_stream_{name}"
    start, end = _window(1)

    verdict = {"emit": False, "rec_in": False, "del_ok": False, "rejected": False}

    header("AWS -> New Relic Metric Stream Diagnostic")
    kv("Name suffix", name)
    kv("Region", region)
    kv("Window", f"{start:%Y-%m-%dT%H:%M:%SZ} -> {end:%Y-%m-%dT%H:%M:%SZ}")
    info("Note: --region must match the region your metric stream lives in,")
    info("or all throughput/delivery checks will read zero.")

    sts = boto3.client("sts", region_name=region)
    cw = boto3.client("cloudwatch", region_name=region)
    fh = boto3.client("firehose", region_name=region)
    s3 = boto3.client("s3", region_name=region)

    # --- 0. identity ---
    section("0 - AWS credentials")
    try:
        ident = sts.get_caller_identity()
        kv("Account", ident["Account"])
        kv("ARN", ident["Arn"])
        ok("Authenticated.")
    except (BotoCoreError, ClientError) as e:
        bad(f"Cannot authenticate to AWS: {e}")
        info("Run 'aws configure' / 'aws sso login' first.")
        return "error"

    def sum_metric(namespace, metric, dim_name, dim_value, stat):
        try:
            resp = cw.get_metric_statistics(
                Namespace=namespace, MetricName=metric,
                Dimensions=[{"Name": dim_name, "Value": dim_value}],
                StartTime=start, EndTime=end, Period=300, Statistics=[stat],
            )
            return sum(dp[stat] for dp in resp.get("Datapoints", []))
        except (BotoCoreError, ClientError):
            return 0.0

    # --- 1. metric stream state ---
    section("1 - Metric Stream state")
    try:
        ms = cw.get_metric_stream(Name=stream_name)
        state = ms.get("State", "?")
        outfmt = ms.get("OutputFormat", "?")
        kv("State", state)
        kv("OutputFormat", outfmt)
        kv("Firehose ARN", ms.get("FirehoseArn", "?"))
        kv("Role ARN", ms.get("RoleArn", "?"))
        if state == "running":
            ok("Stream is running.")
        else:
            bad(f"Stream is NOT running (state={state}).")
        if outfmt == "opentelemetry0.7":
            warn("opentelemetry1.0 is the current recommended format.")
    except (BotoCoreError, ClientError) as e:
        bad(f"Stream '{stream_name}' not found or unreadable: {e}")

    # --- 2. throughput ---
    section("2 - Metric Stream throughput")
    up = sum_metric("AWS/CloudWatch/MetricStreams", "MetricUpdate",
                    "MetricStreamName", stream_name, "Sum")
    er = sum_metric("AWS/CloudWatch/MetricStreams", "PublishErrorRate",
                    "MetricStreamName", stream_name, "Average")
    kv("MetricUpdate (sum, 1h)", f"{up:.4f}")
    kv("PublishErrorRate (avg, 1h)", f"{er:.4f}")
    if up > 0:
        ok("Stream is emitting metrics.")
        verdict["emit"] = True
    else:
        bad("No metric updates - check include/exclude filters or source metrics.")
    if er > 0:
        bad("Publish errors present - stream IAM role may lack firehose:PutRecord.")

    # --- 3. firehose status + delivery ---
    section("3 - Firehose status & delivery")
    bucket_name = None
    log_group = None
    log_enabled = False
    try:
        desc = fh.describe_delivery_stream(DeliveryStreamName=firehose_name)
        d = desc["DeliveryStreamDescription"]
        status = d.get("DeliveryStreamStatus", "?")
        dests = d.get("Destinations", [])
        http_desc = dests[0].get("HttpEndpointDestinationDescription", {}) if dests else {}
        url = http_desc.get("EndpointConfiguration", {}).get("Url", "n/a")
        bucket_arn = http_desc.get("S3DestinationDescription", {}).get("BucketARN", "n/a")
        log_opts = http_desc.get("CloudWatchLoggingOptions", {})
        log_enabled = log_opts.get("Enabled", False)
        log_group = log_opts.get("LogGroupName", "")
        kv("Status", status)
        kv("NR endpoint", url)
        kv("S3 backup", bucket_arn)
        if bucket_arn != "n/a":
            bucket_name = bucket_arn.split(":::")[-1]
        if status == "ACTIVE":
            ok("Firehose ACTIVE.")
        else:
            bad(f"Firehose not ACTIVE (status={status}).")
        if "eu01" in url:
            warn("EU endpoint - confirm NR account is EU and provider region=EU.")
        elif "aws-api.newrelic.com" in url:
            info("US endpoint - confirm NR account is US.")

        rec_in = sum_metric("AWS/Firehose", "IncomingRecords",
                            "DeliveryStreamName", firehose_name, "Sum")
        del_ok = sum_metric("AWS/Firehose", "DeliveryToHttpEndpoint.Success",
                            "DeliveryStreamName", firehose_name, "Sum")
        print()
        kv("IncomingRecords (1h)", f"{rec_in:.4f}")
        kv("DeliveryToHttpEndpoint.Success", f"{del_ok:.4f}")
        if rec_in > 0:
            ok("Firehose is receiving records from the stream.")
            verdict["rec_in"] = True
        else:
            bad("Firehose receiving nothing - break is stream->firehose (IAM role).")
        if del_ok > 0:
            ok("Firehose is delivering to New Relic.")
            verdict["del_ok"] = True
        else:
            bad("No successful HTTP delivery - check endpoint URL + license key.")
    except (BotoCoreError, ClientError) as e:
        bad(f"Firehose '{firehose_name}' not found or unreadable: {e}")

    # --- 4. error logging ---
    section("4 - Firehose error logging")
    if log_enabled and log_group:
        ok(f"CloudWatch logging enabled: {log_group}")
        info("Read recent delivery errors with:")
        info(f"  aws logs tail \"{log_group}\" --region {region} --since 1h --format short")
    else:
        warn("CloudWatch error logging is DISABLED on this Firehose.")
        info("Without it, NR's rejection reason is only in the S3 backup objects (section 5).")
        info("To enable: set cloudwatch_logging_options in the Firehose http_endpoint_configuration.")

    # --- 5. S3 backup ---
    section("5 - S3 backup bucket (rejected records)")
    if bucket_name:
        kv("Bucket", f"s3://{bucket_name}/")
        try:
            keys = []
            paginator = s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=bucket_name):
                for obj in page.get("Contents", []):
                    keys.append((obj["LastModified"], obj["Key"]))
            kv("Object count", str(len(keys)))
            if keys:
                verdict["rejected"] = True
                bad("Rejected records present - data reaches NR but is being REFUSED.")
                info("Newest rejected objects:")
                for _, key in sorted(keys)[-3:]:
                    print(f"       {key}")
                info("Inspect one (decode NR's response yourself):")
                info(f"  aws s3 cp s3://{bucket_name}/<key> - | gunzip | jq .")
            else:
                ok("No rejected records in backup.")
        except (BotoCoreError, ClientError) as e:
            warn(f"Could not list backup bucket: {e}")
    else:
        warn("Could not resolve backup bucket from Firehose config.")

    # --- 6. AWS Config ---
    section("6 - AWS Config (entity metadata enrichment)")
    try:
        cfg = boto3.client("config", region_name=region)
        st = cfg.describe_configuration_recorder_status()
        recorders = st.get("ConfigurationRecordersStatus", [])
        if recorders and recorders[0].get("recording"):
            ok("AWS Config is recording.")
        elif recorders:
            warn("AWS Config recorder exists but is NOT recording.")
        else:
            warn("No AWS Config recorder in this region.")
            info("Metrics still flow without it, but entities may be sparsely decorated.")
    except (BotoCoreError, ClientError):
        warn("AWS Config not enabled in this region (or no permission to read it).")
        info("New Relic uses Config to enrich metrics with resource metadata/entities.")

    # --- verdict ---
    section("VERDICT")
    if verdict["rejected"]:
        bad("Data reaches New Relic but is REJECTED.")
        info("Fix: license key (40 hex chars) OR US/EU region mismatch OR wrong NR account.")
        info("Read a backup object (section 5) for the exact reason.")
        return "broken"
    elif verdict["del_ok"]:
        ok("AWS side is delivering successfully.")
        info("If New Relic shows no data, the problem is the NR link - run the 'nr' subcommand.")
        return "healthy"
    elif verdict["rec_in"]:
        bad("Firehose has records but no successful delivery.")
        info("Check the NR endpoint URL and the access_key (license key) on the Firehose.")
        return "broken"
    elif verdict["emit"]:
        bad("Stream emits, but Firehose isn't receiving.")
        info("Check the metric-stream IAM role grants firehose:PutRecord to this stream.")
        return "broken"
    else:
        bad("Nothing flowing from the Metric Stream.")
        info("Check stream state, include/exclude filters, and the metric-stream IAM role.")
        return "broken"

# =====================================================================
# NEW RELIC SIDE
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
    p = argparse.ArgumentParser(description="New Relic <- AWS metric stream diagnostics")
    sub = p.add_subparsers(dest="cmd", required=True)

    pa = sub.add_parser("aws", help="diagnose the AWS side")
    pa.add_argument("--name", required=True, help="var.name suffix used in Terraform")
    pa.add_argument("--region", default="us-east-1")

    pn = sub.add_parser("nr", help="diagnose the New Relic side")
    pn.add_argument("--api-key", default=os.environ.get("NR_API_KEY"))
    pn.add_argument("--account-id", default=os.environ.get("NR_ACCOUNT_ID"))
    pn.add_argument("--region", default=os.environ.get("NR_REGION", "US"))

    pall = sub.add_parser("all", help="run both sides")
    pall.add_argument("--name", required=True)
    pall.add_argument("--region", default="us-east-1")
    pall.add_argument("--api-key", default=os.environ.get("NR_API_KEY"))
    pall.add_argument("--account-id", default=os.environ.get("NR_ACCOUNT_ID"))
    pall.add_argument("--nr-region", default=os.environ.get("NR_REGION", "US"))

    args = p.parse_args()

    # Exit codes: 0 healthy · 2 broken (problem found) · 3 error (couldn't run)
    STATUS_EXIT = {"healthy": 0, "broken": 2, "error": 3}

    if args.cmd == "aws":
        status = diagnose_aws(args.name, args.region)
        sys.exit(STATUS_EXIT.get(status, 3))

    elif args.cmd == "nr":
        if not args.api_key or not args.account_id:
            bad("Missing NR credentials. Set NR_API_KEY and NR_ACCOUNT_ID (or pass --api-key/--account-id).")
            sys.exit(3)
        status = diagnose_nr(args.api_key, args.account_id, args.region)
        sys.exit(STATUS_EXIT.get(status, 3))

    elif args.cmd == "all":
        aws_status = diagnose_aws(args.name, args.region)
        if not args.api_key or not args.account_id:
            print()
            warn("Skipping NR side: set NR_API_KEY and NR_ACCOUNT_ID to include it.")
            # Don't fail solely because NR creds were absent — report the AWS result.
            sys.exit(STATUS_EXIT.get(aws_status, 3))
        nr_status = diagnose_nr(args.api_key, args.account_id, args.nr_region)
        # Worst status wins: error > broken > healthy.
        order = {"healthy": 0, "broken": 1, "error": 2}
        worst = aws_status if order.get(aws_status, 2) >= order.get(nr_status, 2) else nr_status
        print()
        section("OVERALL")
        if worst == "healthy":
            ok("Both sides healthy.")
        elif worst == "broken":
            bad("A problem was found - see the section verdicts above.")
        else:
            bad("A check could not be run - see above.")
        sys.exit(STATUS_EXIT.get(worst, 3))

if __name__ == "__main__":
    main()
