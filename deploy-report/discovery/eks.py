"""EKS discovery: clusters -> Kubernetes Deployments -> container images.

Two extra prerequisites vs. ECS, because EKS workloads live in the
Kubernetes API, not the AWS API:

  1. The AWS CLI v2 must be on PATH -- we shell out to
     `aws eks update-kubeconfig` so you don't have to pre-populate
     kubeconfig contexts for every cluster by hand.
  2. The `kubernetes` Python package must be installed, and the IAM
     identity running this script must be mapped in each cluster's
     aws-auth ConfigMap (or EKS access entries) with at least read
     access to Deployments cluster-wide (a `view`-style ClusterRole is
     enough).

If either of those isn't in place for a given cluster, discovery for
that one cluster fails gracefully -- it still shows up in the report
with a warning instead of aborting the whole run.
"""

import subprocess

from . import common


def discover(session, region, team_key, environment_key, kubeconfig_overrides=None):
    kubeconfig_overrides = kubeconfig_overrides or {}
    eks = session.client('eks', region_name=region)

    names = []
    for page in eks.get_paginator('list_clusters').paginate():
        names.extend(page['clusters'])

    clusters = []
    for name in names:
        desc = eks.describe_cluster(name=name)['cluster']
        tags = desc.get('tags', {})
        deployments, warning = _discover_deployments(name, region, kubeconfig_overrides)
        clusters.append({
            'platform': 'EKS',
            'name': name,
            'arn': desc['arn'],
            'region': region,
            'team': common.get_tag_ci(tags, team_key) or 'Unassigned',
            'environment': common.get_tag_ci(tags, environment_key) or 'Unknown',
            'services': deployments,
            'warning': warning,
            'console_url': (
                f"https://{region}.console.aws.amazon.com/eks/home?region={region}#/clusters/{name}"
            ),
        })
    return clusters


def _discover_deployments(cluster_name, region, kubeconfig_overrides):
    try:
        from kubernetes import client, config as kube_config
    except ImportError:
        return [], ('the "kubernetes" package is not installed; run '
                     '`pip install kubernetes` to enable EKS workload discovery')

    context_alias = kubeconfig_overrides.get(cluster_name, cluster_name)
    try:
        subprocess.run(
            ['aws', 'eks', 'update-kubeconfig', '--name', cluster_name,
             '--region', region, '--alias', context_alias],
            check=True, capture_output=True, timeout=30,
        )
        kube_config.load_kube_config(context=context_alias)
    except Exception as e:
        return [], f'could not load kubeconfig for {cluster_name}: {e}'

    try:
        apps = client.AppsV1Api()
        deployments = apps.list_deployment_for_all_namespaces()
    except Exception as e:
        return [], f'could not list deployments in {cluster_name} (check aws-auth / access entries): {e}'

    services = []
    for d in deployments.items:
        containers = []
        for c in d.spec.template.spec.containers:
            last_segment = c.image.rsplit('/', 1)[-1]
            tag = last_segment.split(':', 1)[1] if ':' in last_segment else 'latest'
            containers.append({'name': c.name, 'image': c.image, 'tag': tag})
        services.append({
            'name': f'{d.metadata.namespace}/{d.metadata.name}',
            'desired_count': d.spec.replicas,
            'running_count': d.status.available_replicas or 0,
            'containers': containers,
            'console_url': None,  # no single-object EKS console deep link
        })
    return services, None
