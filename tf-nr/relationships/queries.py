"""
Read-only AWS discovery for the resource kinds we want to reconcile against
New Relic: ECS clusters/services, EKS clusters, RDS instances/clusters.

Auth follows boto3's normal credential chain (env vars, ~/.aws/credentials
profile, or an instance/task role) -- nothing here accepts or stores
credentials directly. Set AWS_PROFILE / AWS_DEFAULT_REGION as you normally
would, or pass --profile/--region on the CLI.

Every call here is List*/Describe*/Get* -- nothing mutates AWS.

To add a new resource kind: write a `fetch_<kind>(session, region) ->
list[AwsResource]` function following the pattern below, and register it
in KIND_FETCHERS at the bottom of this file. The matcher and config file
work with any kind automatically -- see config/aws_match_rules.yaml.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger("nr_rel.aws_client")


@dataclass
class AwsResource:
    kind: str  # e.g. "ecs_cluster", "eks_cluster", "rds_instance"
    id: str  # the natural identifier a human would recognize (name/identifier)
    arn: str
    region: str
    tags: dict[str, str] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "id": self.id, "arn": self.arn,
            "region": self.region, "tags": self.tags, "raw": self.raw,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AwsResource":
        return cls(**data)


def _tag_list_to_dict(tag_list: list[dict[str, str]] | None) -> dict[str, str]:
    out = {}
    for t in tag_list or []:
        key = t.get("Key") or t.get("key")
        val = t.get("Value") or t.get("value")
        if key is not None:
            out[key] = val or ""
    return out


def _session(profile: str | None, region: str):
    import boto3
    return boto3.Session(profile_name=profile, region_name=region)


def fetch_ecs_clusters(session, region: str) -> list[AwsResource]:
    client = session.client("ecs", region_name=region)
    resources: list[AwsResource] = []
    cluster_arns: list[str] = []
    paginator = client.get_paginator("list_clusters")
    for page in paginator.paginate():
        cluster_arns.extend(page.get("clusterArns", []))

    for i in range(0, len(cluster_arns), 100):
        batch = cluster_arns[i : i + 100]
        described = client.describe_clusters(clusters=batch, include=["TAGS"])
        for c in described.get("clusters", []):
            resources.append(
                AwsResource(
                    kind="ecs_cluster",
                    id=c["clusterName"],
                    arn=c["clusterArn"],
                    region=region,
                    tags=_tag_list_to_dict(c.get("tags")),
                    raw={"status": c.get("status"), "activeServicesCount": c.get("activeServicesCount")},
                )
            )
    logger.info("ECS: found %d cluster(s) in %s", len(resources), region)
    return resources


def fetch_ecs_services(session, region: str) -> list[AwsResource]:
    client = session.client("ecs", region_name=region)
    resources: list[AwsResource] = []

    cluster_arns: list[str] = []
    paginator = client.get_paginator("list_clusters")
    for page in paginator.paginate():
        cluster_arns.extend(page.get("clusterArns", []))

    for cluster_arn in cluster_arns:
        service_arns: list[str] = []
        svc_paginator = client.get_paginator("list_services")
        for page in svc_paginator.paginate(cluster=cluster_arn):
            service_arns.extend(page.get("serviceArns", []))

        for i in range(0, len(service_arns), 10):  # describe_services caps at 10
            batch = service_arns[i : i + 10]
            if not batch:
                continue
            described = client.describe_services(cluster=cluster_arn, services=batch, include=["TAGS"])
            for s in described.get("services", []):
                resources.append(
                    AwsResource(
                        kind="ecs_service",
                        id=s["serviceName"],
                        arn=s["serviceArn"],
                        region=region,
                        tags=_tag_list_to_dict(s.get("tags")),
                        raw={"clusterArn": cluster_arn, "status": s.get("status"), "desiredCount": s.get("desiredCount")},
                    )
                )
    logger.info("ECS: found %d service(s) in %s", len(resources), region)
    return resources


def fetch_eks_clusters(session, region: str) -> list[AwsResource]:
    client = session.client("eks", region_name=region)
    resources: list[AwsResource] = []
    names: list[str] = []
    paginator = client.get_paginator("list_clusters")
    for page in paginator.paginate():
        names.extend(page.get("clusters", []))

    for name in names:
        described = client.describe_cluster(name=name)
        c = described.get("cluster", {})
        resources.append(
            AwsResource(
                kind="eks_cluster",
                id=c.get("name", name),
                arn=c.get("arn", ""),
                region=region,
                tags=c.get("tags", {}) or {},
                raw={"status": c.get("status"), "version": c.get("version")},
            )
        )
    logger.info("EKS: found %d cluster(s) in %s", len(resources), region)
    return resources


def fetch_rds_instances(session, region: str) -> list[AwsResource]:
    client = session.client("rds", region_name=region)
    resources: list[AwsResource] = []
    paginator = client.get_paginator("describe_db_instances")
    for page in paginator.paginate():
        for db in page.get("DBInstances", []):
            resources.append(
                AwsResource(
                    kind="rds_instance",
                    id=db["DBInstanceIdentifier"],
                    arn=db.get("DBInstanceArn", ""),
                    region=region,
                    tags=_tag_list_to_dict(db.get("TagList")),
                    raw={"engine": db.get("Engine"), "status": db.get("DBInstanceStatus")},
                )
            )
    logger.info("RDS: found %d instance(s) in %s", len(resources), region)
    return resources


def fetch_rds_clusters(session, region: str) -> list[AwsResource]:
    client = session.client("rds", region_name=region)
    resources: list[AwsResource] = []
    paginator = client.get_paginator("describe_db_clusters")
    for page in paginator.paginate():
        for db in page.get("DBClusters", []):
            resources.append(
                AwsResource(
                    kind="rds_cluster",
                    id=db["DBClusterIdentifier"],
                    arn=db.get("DBClusterArn", ""),
                    region=region,
                    tags=_tag_list_to_dict(db.get("TagList")),
                    raw={"engine": db.get("Engine"), "status": db.get("Status")},
                )
            )
    logger.info("RDS: found %d cluster(s) in %s", len(resources), region)
    return resources


# Register new kinds here -- the CLI's --kinds flag and `discover-all` both
# read from this map, so this is the one place you need to touch to plug in
# a new fetcher.
KIND_FETCHERS: dict[str, Callable] = {
    "ecs-clusters": fetch_ecs_clusters,
    "ecs-services": fetch_ecs_services,
    "eks-clusters": fetch_eks_clusters,
    "rds-instances": fetch_rds_instances,
    "rds-clusters": fetch_rds_clusters,
}


def discover(
    kinds: list[str], regions: list[str], profile: str | None = None
) -> list[AwsResource]:
    all_resources: list[AwsResource] = []
    for region in regions:
        session = _session(profile, region)
        for kind in kinds:
            fetcher = KIND_FETCHERS.get(kind)
            if not fetcher:
                logger.warning("Unknown AWS resource kind '%s' -- skipping. Known kinds: %s", kind, list(KIND_FETCHERS))
                continue
            try:
                all_resources.extend(fetcher(session, region))
            except Exception as exc:  # noqa: BLE001 -- surface any boto3/API error, keep going
                logger.error("Failed to fetch %s in %s: %s", kind, region, exc)
    return all_resources
