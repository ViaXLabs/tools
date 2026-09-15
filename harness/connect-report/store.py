#!/usr/bin/env python3
"""Upload a normalized deployment record to S3, partitioned by date and service.
This is the whole 'data store' - a bucket, not a database. Simple on purpose."""
import json, os
from datetime import datetime, timezone
import boto3

NORMALIZED_PATH = os.environ.get("NORMALIZED_PATH", "./normalized/record.json")
BUCKET = os.environ["S3_BUCKET"]           # required
PREFIX = os.environ.get("S3_PREFIX", "deployment-reports")

def main():
    with open(NORMALIZED_PATH) as f:
        record = json.load(f)

    service = record.get("service", "unknown")
    now = datetime.now(timezone.utc)
    key = f"{PREFIX}/{now:%Y/%m/%d}/{service}/{now:%H%M%S}.json"

    s3 = boto3.client("s3")
    s3.put_object(Bucket=BUCKET, Key=key, Body=json.dumps(record, indent=2).encode("utf-8"), ContentType="application/json")
    print(f"Uploaded to s3://{BUCKET}/{key}")

if __name__ == "__main__":
    main()
