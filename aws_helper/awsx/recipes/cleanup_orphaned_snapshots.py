"""cleanup.orphaned-snapshots

Finds EBS snapshots owned by this account whose source volume no longer
exists, and (optionally) deletes them. A single `aws ec2 describe-*` call
can't do this join -- it requires cross-referencing two API calls, which is
exactly the kind of "intricate" op this tool is for.
"""
from __future__ import annotations
import click
from awsx.registry import register
from awsx.aws import client


@register(
    name="orphaned-snapshots",
    group="cleanup",
    summary="Find (and optionally delete) EBS snapshots with no parent volume",
    params=[
        click.Option(["--older-than-days"], type=int, default=0,
                      help="Only consider snapshots older than N days"),
    ],
    mutating=True,  # can call ec2:DeleteSnapshot with --execute
)
def run(session, region, dry_run, older_than_days=0, **kwargs):
    import datetime

    ec2 = client(session, "ec2", region)
    snapshots = ec2.describe_snapshots(OwnerIds=["self"])["Snapshots"]
    live_volume_ids = {
        v["VolumeId"]
        for page in ec2.get_paginator("describe_volumes").paginate()
        for v in page["Volumes"]
    }

    cutoff = None
    if older_than_days:
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=older_than_days)

    orphaned = []
    for snap in snapshots:
        vol_id = snap.get("VolumeId")
        if vol_id in live_volume_ids:
            continue
        if cutoff and snap["StartTime"] > cutoff:
            continue
        orphaned.append({
            "SnapshotId": snap["SnapshotId"],
            "VolumeId": vol_id,
            "VolumeSize": snap.get("VolumeSize"),
            "StartTime": snap["StartTime"].isoformat(),
            "Description": snap.get("Description", ""),
        })

    deleted = []
    if not dry_run:
        for snap in orphaned:
            ec2.delete_snapshot(SnapshotId=snap["SnapshotId"])
            deleted.append(snap["SnapshotId"])

    return {
        "region": region,
        "orphaned_count": len(orphaned),
        "orphaned_snapshots": orphaned,
        "deleted": deleted,
        "dry_run": dry_run,
    }
