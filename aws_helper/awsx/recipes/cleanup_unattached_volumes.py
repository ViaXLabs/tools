"""cleanup.unattached-volumes

Finds EBS volumes in 'available' (unattached) state, with age and estimated
monthly cost, and optionally tags or deletes them.
"""
from __future__ import annotations
import datetime
import click
from awsx.registry import register
from awsx.aws import client

# Rough us-east-1 gp3 pricing for a quick cost estimate; not authoritative.
_GB_MONTH_ESTIMATE = 0.08


@register(
    name="unattached-volumes",
    group="cleanup",
    summary="Find unattached EBS volumes, with age and rough monthly cost",
    params=[
        click.Option(["--tag-key"], default=None, help="Tag key to apply instead of deleting"),
        click.Option(["--tag-value"], default="awsx-flagged-unattached"),
    ],
    mutating=True,  # can call ec2:CreateTags with --execute
)
def run(session, region, dry_run, tag_key=None, tag_value="awsx-flagged-unattached", **kwargs):
    ec2 = client(session, "ec2", region)
    volumes = [
        v for page in ec2.get_paginator("describe_volumes").paginate(
            Filters=[{"Name": "status", "Values": ["available"]}]
        )
        for v in page["Volumes"]
    ]

    now = datetime.datetime.now(datetime.timezone.utc)
    findings = []
    for v in volumes:
        age_days = (now - v["CreateTime"]).days
        findings.append({
            "VolumeId": v["VolumeId"],
            "SizeGiB": v["Size"],
            "AgeDays": age_days,
            "EstMonthlyCostUSD": round(v["Size"] * _GB_MONTH_ESTIMATE, 2),
            "Tags": v.get("Tags", []),
        })

    acted_on = []
    if not dry_run and tag_key:
        for f in findings:
            ec2.create_tags(Resources=[f["VolumeId"]], Tags=[{"Key": tag_key, "Value": tag_value}])
            acted_on.append(f["VolumeId"])

    total_est_cost = round(sum(f["EstMonthlyCostUSD"] for f in findings), 2)

    return {
        "region": region,
        "unattached_count": len(findings),
        "est_total_monthly_cost_usd": total_est_cost,
        "volumes": findings,
        "tagged": acted_on,
        "dry_run": dry_run,
    }
