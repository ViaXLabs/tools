#!/usr/bin/env python3
"""Pull recent deployment records from S3 and render a single static HTML report.

Styling is inline (no <style> block) on purpose - Confluence's storage format
strips <style> blocks, and this report always gets published there."""
import json, os
from datetime import datetime, timezone, timedelta
import boto3

BUCKET = os.environ["S3_BUCKET"]
PREFIX = os.environ.get("S3_PREFIX", "deployment-reports")
DAYS_BACK = int(os.environ.get("REPORT_DAYS_BACK", "7"))
OUT_PATH = os.environ.get("REPORT_HTML_PATH", "./report/deployment-report.html")

TD = 'style="border:1px solid #ccc;padding:6px 10px;text-align:left;font-size:14px;"'
TH = 'style="border:1px solid #ccc;padding:6px 10px;text-align:left;font-size:14px;background:#f2f2f2;"'

def list_recent_records(s3):
    records = []
    now = datetime.now(timezone.utc)
    for i in range(DAYS_BACK):
        day = now - timedelta(days=i)
        prefix = f"{PREFIX}/{day:%Y/%m/%d}/"
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
            for obj in page.get("Contents", []):
                body = s3.get_object(Bucket=BUCKET, Key=obj["Key"])["Body"].read()
                records.append(json.loads(body))
    return sorted(records, key=lambda r: r.get("reported_at", ""), reverse=True)

def render_row(r):
    tickets = ", ".join(t.get("key", "") for t in r.get("tickets", []))
    docs = str(len(r.get("docs", [])))
    commit = (r.get("source") or {}).get("commit_sha") or ""
    return (
        f'<tr>'
        f'<td {TD}>{r.get("service")}</td>'
        f'<td {TD}>{r.get("environment")}</td>'
        f'<td {TD}>{commit[:8]}</td>'
        f'<td {TD}>{(r.get("rollout") or {}).get("sync_status", "")}</td>'
        f'<td {TD}>{tickets}</td>'
        f'<td {TD}>{docs}</td>'
        f'<td {TD}>{r.get("reported_at")}</td>'
        f'</tr>'
    )

def render_html(records):
    rows = "\n".join(render_row(r) for r in records)
    headers = ["Service", "Environment", "Commit", "Sync status", "Tickets", "Docs linked", "Reported at"]
    header_row = "".join(f'<th {TH}>{h}</th>' for h in headers)
    return (
        f'<h1>Deployment report</h1>'
        f'<p>Last {DAYS_BACK} days, generated {datetime.now(timezone.utc).isoformat()}</p>'
        f'<table style="border-collapse:collapse;width:100%;">'
        f'<tr>{header_row}</tr>'
        f'{rows}'
        f'</table>'
    )

def main():
    s3 = boto3.client("s3")
    records = list_recent_records(s3)
    html = render_html(records)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        f.write(html)
    print("Wrote", OUT_PATH, "with", len(records), "records")

if __name__ == "__main__":
    main()
