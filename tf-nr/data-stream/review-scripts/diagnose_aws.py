#!/usr/bin/env python3
"""
diagnose_aws.py — AWS-side diagnostic for a New Relic CloudWatch Metric
Stream (Firehose) integration.

Walks the data path up to the handoff to New Relic and prints a per-hop
report with a verdict:

    CloudWatch -> Metric Stream -> Firehose -> (NR endpoint)
                                    + S3 backup, error logs, AWS Config

Requires: boto3  (pip install boto3).  Python 3.8+.
Read-only: makes no changes to AWS.

Usage:
    ./diagnose_aws.py --name prod --region us-east-1

Exit codes:  0 healthy · 2 broken (problem found) · 3 error (couldn't run)
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

def _window(hours=1):
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    return start, end

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
# CLI
# =====================================================================

def main():
    p = argparse.ArgumentParser(
        description="AWS-side diagnostic for a New Relic metric stream integration")
    p.add_argument("--name", required=True, help="var.name suffix used in Terraform")
    p.add_argument("--region", default="us-east-1", help="AWS region the stream lives in")
    args = p.parse_args()

    status = diagnose_aws(args.name, args.region)
    sys.exit({"healthy": 0, "broken": 2, "error": 3}.get(status, 3))

if __name__ == "__main__":
    main()
