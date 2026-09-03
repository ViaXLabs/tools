#!/usr/bin/env python3
"""
tf_lock_manager.py — Report on and clear Terraform state locks across
both the legacy DynamoDB lock table and the newer S3-native lock files.

Two subcommands:

  report   Scan one or more DynamoDB tables and/or S3 buckets for
           existing locks. Prints a numbered table and saves results
           to a local cache file so `clear` can act on them by index.

  clear    Delete a lock by its report index, or by explicit
           --type/--table/--lock-id or --type/--bucket/--key.
           Use --instructions-only to print manual steps instead of
           deleting. Use --force to skip the confirmation prompt.

Examples:
  python3 tf_lock_manager.py report \\
      --dynamo-table tf-locks-nonprod --dynamo-table tf-locks-prod \\
      --s3-bucket my-tf-bucket

  python3 tf_lock_manager.py clear --index 2
  python3 tf_lock_manager.py clear --index 2 --instructions-only
  python3 tf_lock_manager.py clear --type s3 --bucket my-tf-bucket \\
      --key prod/infra/terraform.tfstate.tflock
  python3 tf_lock_manager.py clear --type dynamo --table tf-locks-prod \\
      --lock-id my-bucket/prod/infra/terraform.tfstate

Requires: pip install boto3
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

CACHE_FILE = Path.home() / ".tf_lock_report_cache.json"


def age_minutes(iso_ts):
    try:
        created = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - created).total_seconds() / 60
    except Exception:
        return None


def scan_dynamo(table_name):
    table = boto3.resource("dynamodb").Table(table_name)
    results = []
    try:
        items = table.scan().get("Items", [])
    except ClientError as e:
        print(f"  ⚠️  Could not scan {table_name}: {e}", file=sys.stderr)
        return results

    for item in items:
        lock_id = item.get("LockID", "unknown")
        info = {}
        try:
            info = json.loads(item.get("Info", ""))
        except (TypeError, ValueError):
            pass
        results.append({
            "type": "dynamo",
            "table": table_name,
            "lock_id": lock_id,
            "who": info.get("Who", "?"),
            "operation": info.get("Operation", "?"),
            "path": info.get("Path", lock_id),
            "created": info.get("Created", "?"),
            "age_min": age_minutes(info.get("Created", "")),
        })
    return results


def scan_s3(bucket, prefix=""):
    s3 = boto3.client("s3")
    results = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if not obj["Key"].endswith(".tflock"):
                continue
            body = ""
            try:
                body = s3.get_object(Bucket=bucket, Key=obj["Key"])["Body"].read().decode()
            except ClientError:
                pass
            info = {}
            try:
                info = json.loads(body)
            except (TypeError, ValueError):
                pass
            age = (datetime.now(timezone.utc) - obj["LastModified"]).total_seconds() / 60
            results.append({
                "type": "s3",
                "bucket": bucket,
                "key": obj["Key"],
                "who": info.get("Who", "?"),
                "operation": info.get("Operation", "?"),
                "path": obj["Key"][: -len(".tflock")],
                "created": str(obj["LastModified"]),
                "age_min": age,
            })
    return results


def cmd_report(args):
    if not args.dynamo_table and not args.s3_bucket:
        print("Provide at least one --dynamo-table and/or --s3-bucket.", file=sys.stderr)
        sys.exit(1)

    all_locks = []
    for table in args.dynamo_table:
        print(f"Scanning DynamoDB table: {table} ...")
        all_locks += scan_dynamo(table)
    for bucket in args.s3_bucket:
        print(f"Scanning S3 bucket: {bucket} ...")
        all_locks += scan_s3(bucket, args.s3_prefix or "")

    CACHE_FILE.write_text(json.dumps(all_locks, indent=2))

    if not all_locks:
        print("\n✅ No locks found anywhere. Nothing to report.")
        return

    print(f"\nFound {len(all_locks)} lock(s):\n")
    print(f"{'#':<3} {'Source':<8} {'Age(min)':<10} {'Who':<22} {'Path'}")
    print("-" * 95)
    for i, lock in enumerate(all_locks):
        age = f"{lock['age_min']:.1f}" if lock["age_min"] is not None else "?"
        print(f"{i:<3} {lock['type']:<8} {age:<10} {lock['who']:<22} {lock['path']}")

    print(f"\nSaved to {CACHE_FILE}")
    print("Next: python3 tf_lock_manager.py clear --index N   (add --instructions-only to just see the steps)")


def print_instructions(lock):
    print("\nManual removal steps:")
    if lock["type"] == "dynamo":
        print(f"  aws dynamodb delete-item --table-name {lock['table']} \\")
        print(f"    --key '{{\"LockID\": {{\"S\": \"{lock['lock_id']}\"}}}}'")
    else:
        print(f"  aws s3 rm s3://{lock['bucket']}/{lock['key']}")


def delete_lock(lock, force):
    label = lock.get("lock_id") or lock.get("key")
    if not force:
        if input(f"Delete {lock['type']} lock '{label}'? [y/N] ").strip().lower() != "y":
            print("Aborted. Nothing deleted.")
            return
    if lock["type"] == "dynamo":
        boto3.resource("dynamodb").Table(lock["table"]).delete_item(Key={"LockID": lock["lock_id"]})
    else:
        boto3.client("s3").delete_object(Bucket=lock["bucket"], Key=lock["key"])
    print("✅ Deleted.")


def cmd_clear(args):
    if args.index is not None:
        if not CACHE_FILE.exists():
            print("No report cache found — run `report` first.", file=sys.stderr)
            sys.exit(1)
        locks = json.loads(CACHE_FILE.read_text())
        if args.index >= len(locks) or args.index < 0:
            print(f"Index {args.index} out of range (0-{len(locks) - 1}).", file=sys.stderr)
            sys.exit(1)
        lock = locks[args.index]
    elif args.type == "dynamo" and args.table and args.lock_id:
        lock = {"type": "dynamo", "table": args.table, "lock_id": args.lock_id}
    elif args.type == "s3" and args.bucket and args.key:
        lock = {"type": "s3", "bucket": args.bucket, "key": args.key}
    else:
        print("Provide --index, or --type dynamo with --table/--lock-id, "
              "or --type s3 with --bucket/--key.", file=sys.stderr)
        sys.exit(1)

    if args.instructions_only:
        print_instructions(lock)
    else:
        delete_lock(lock, args.force)


def main():
    p = argparse.ArgumentParser(description="Report on and clear Terraform state locks (DynamoDB + S3).")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("report", help="Scan for existing locks")
    r.add_argument("--dynamo-table", action="append", default=[], help="DynamoDB lock table (repeatable)")
    r.add_argument("--s3-bucket", action="append", default=[], help="S3 bucket to scan for .tflock files (repeatable)")
    r.add_argument("--s3-prefix", default="", help="Optional S3 prefix to limit the scan")
    r.set_defaults(func=cmd_report)

    c = sub.add_parser("clear", help="Delete a lock, or print manual instructions")
    c.add_argument("--index", type=int, help="Index from the last `report` run")
    c.add_argument("--type", choices=["dynamo", "s3"], help="Lock type (if not using --index)")
    c.add_argument("--table", help="DynamoDB table name")
    c.add_argument("--lock-id", help="DynamoDB LockID value")
    c.add_argument("--bucket", help="S3 bucket name")
    c.add_argument("--key", help="S3 object key (the .tflock file)")
    c.add_argument("--instructions-only", action="store_true", help="Print manual steps instead of deleting")
    c.add_argument("--force", action="store_true", help="Skip confirmation prompt")
    c.set_defaults(func=cmd_clear)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
