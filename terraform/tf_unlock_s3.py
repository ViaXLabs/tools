#!/usr/bin/env python3
"""
tf_unlock_s3.py — Check and clear a Terraform native S3 state lock (.tflock).

For Terraform's `use_lockfile = true` S3 backend (Terraform 1.10+).
Not for DynamoDB-based locking.

Usage:
    python3 tf_unlock_s3.py <bucket> <state-key> [--max-age MINUTES] [--force]

Example:
    python3 tf_unlock_s3.py my-tf-bucket prod/infrastructure/terraform.tfstate
    python3 tf_unlock_s3.py my-tf-bucket prod/infra/terraform.tfstate --max-age 0 --force

Requires: pip install boto3
"""

import argparse
import sys
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError


def main():
    p = argparse.ArgumentParser(description="Clear a Terraform S3-native state lock.")
    p.add_argument("bucket", help="S3 bucket holding the terraform state")
    p.add_argument("state_key", help="Key/path to the .tfstate file (without .tflock)")
    p.add_argument("--max-age", type=int, default=15,
                   help="Only auto-delete locks older than this many minutes (default: 15, 0 = skip check)")
    p.add_argument("--force", action="store_true", help="Skip confirmation prompt")
    args = p.parse_args()

    lock_key = f"{args.state_key}.tflock"
    s3 = boto3.client("s3")

    print(f"Checking for lock: s3://{args.bucket}/{lock_key}\n")

    try:
        head = s3.head_object(Bucket=args.bucket, Key=lock_key)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
            print("✅ No lock file found. Nothing to do.")
            sys.exit(0)
        print(f"❌ AWS error: {e}", file=sys.stderr)
        sys.exit(4)

    age_min = (datetime.now(timezone.utc) - head["LastModified"]).total_seconds() / 60
    print(f"🔒 Lock found. Last modified: {head['LastModified']}  (age: {age_min:.1f} min)\n")

    try:
        body = s3.get_object(Bucket=args.bucket, Key=lock_key)["Body"].read().decode()
        print("Lock contents (who/what/when):\n", body, "\n")
    except ClientError:
        print("(couldn't read lock contents)\n")

    if args.max_age and age_min < args.max_age:
        print(f"🛑 Lock is younger than {args.max_age} min threshold — likely an active run. Not deleting.")
        print(f"   Re-run with --max-age 0 --force if you're sure it's stale.")
        sys.exit(2)

    if not args.force:
        if input("Delete this lock file now? [y/N] ").strip().lower() != "y":
            print("Aborted. Lock file NOT deleted.")
            sys.exit(3)

    s3.delete_object(Bucket=args.bucket, Key=lock_key)
    print("✅ Lock cleared. Terraform should run again.")


if __name__ == "__main__":
    main()
