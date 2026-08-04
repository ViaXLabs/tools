"""cost.idle-resources

Cross-references running EC2 instances and RDS databases against CloudWatch
CPU utilization over a lookback window to flag likely-idle (and therefore
wasteful) resources. This kind of "compute + metrics" join is the main
thing that's painful to do with raw aws-cli piping.
"""
from __future__ import annotations
import datetime
import click
from awsx.registry import register
from awsx.aws import client


@register(
    name="idle-resources",
    group="cost",
    summary="Find EC2/RDS resources with low average CPU over a lookback window",
    params=[
        click.Option(["--lookback-days"], type=int, default=14),
        click.Option(["--cpu-threshold"], type=float, default=5.0,
                      help="Flag if average CPU% is below this"),
    ],
)
def run(session, region, dry_run, lookback_days=14, cpu_threshold=5.0, **kwargs):
    ec2 = client(session, "ec2", region)
    cw = client(session, "cloudwatch", region)
    rds = client(session, "rds", region)

    end = datetime.datetime.now(datetime.timezone.utc)
    start = end - datetime.timedelta(days=lookback_days)

    def avg_cpu(namespace, dimension_name, dimension_value):
        resp = cw.get_metric_statistics(
            Namespace=namespace,
            MetricName="CPUUtilization",
            Dimensions=[{"Name": dimension_name, "Value": dimension_value}],
            StartTime=start,
            EndTime=end,
            Period=86400,
            Statistics=["Average"],
        )
        points = resp.get("Datapoints", [])
        if not points:
            return None
        return round(sum(p["Average"] for p in points) / len(points), 2)

    flagged_instances = []
    for page in ec2.get_paginator("describe_instances").paginate(
        Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
    ):
        for res in page["Reservations"]:
            for inst in res["Instances"]:
                cpu = avg_cpu("AWS/EC2", "InstanceId", inst["InstanceId"])
                if cpu is not None and cpu < cpu_threshold:
                    flagged_instances.append({
                        "InstanceId": inst["InstanceId"],
                        "InstanceType": inst["InstanceType"],
                        "AvgCpuPercent": cpu,
                        "Tags": inst.get("Tags", []),
                    })

    flagged_dbs = []
    for page in rds.get_paginator("describe_db_instances").paginate():
        for db in page["DBInstances"]:
            cpu = avg_cpu("AWS/RDS", "DBInstanceIdentifier", db["DBInstanceIdentifier"])
            if cpu is not None and cpu < cpu_threshold:
                flagged_dbs.append({
                    "DBInstanceIdentifier": db["DBInstanceIdentifier"],
                    "DBInstanceClass": db["DBInstanceClass"],
                    "AvgCpuPercent": cpu,
                })

    return {
        "region": region,
        "lookback_days": lookback_days,
        "cpu_threshold": cpu_threshold,
        "flagged_ec2_instances": flagged_instances,
        "flagged_rds_instances": flagged_dbs,
    }
