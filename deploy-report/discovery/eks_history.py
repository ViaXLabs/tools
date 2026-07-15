"""EKS history: reconstructs each Deployment's version timeline from its
ReplicaSet revision history. Kubernetes keeps old ReplicaSets around behind
every Deployment (that's how rollbacks work) -- each one is a timestamped
prior version of the pod template, including the image.

The catch: this is capped by `revisionHistoryLimit` (default 10 per
Deployment). A service that deploys many times a day can blow through that
within your requested window; when we can't find a revision from before
the window start AND we've hit the retention cap, we attach a `warning` to
that service so the report says so instead of silently showing a partial
picture.
"""

import subprocess

from . import common


def discover_history(session, region, team_key, environment_key, start_time, end_time,
                      kubeconfig_overrides=None, is_present_scan=True):
    kubeconfig_overrides = kubeconfig_overrides or {}
    eks = session.client('eks', region_name=region)

    names = []
    for page in eks.get_paginator('list_clusters').paginate():
        names.extend(page['clusters'])

    clusters = []
    for name in names:
        desc = eks.describe_cluster(name=name)['cluster']
        tags = desc.get('tags', {})
        services, cluster_warning = _service_histories(
            name, region, kubeconfig_overrides, start_time, end_time, is_present_scan)
        clusters.append({
            'platform': 'EKS',
            'name': name,
            'arn': desc['arn'],
            'region': region,
            'team': common.get_tag_ci(tags, team_key) or 'Unassigned',
            'environment': common.get_tag_ci(tags, environment_key) or 'Unknown',
            'services': services,
            'warning': cluster_warning,
            'console_url': f"https://{region}.console.aws.amazon.com/eks/home?region={region}#/clusters/{name}",
        })
    return clusters


def _service_histories(cluster_name, region, kubeconfig_overrides, start_time, end_time, is_present_scan):
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
        deployments = apps.list_deployment_for_all_namespaces().items
        replicasets = apps.list_replica_set_for_all_namespaces().items
    except Exception as e:
        return [], f'could not list workloads in {cluster_name} (check aws-auth / access entries): {e}'

    services = []
    for d in deployments:
        owned = [
            rs for rs in replicasets
            if any(o.kind == 'Deployment' and o.uid == d.metadata.uid for o in (rs.metadata.owner_references or []))
        ]
        owned.sort(key=lambda rs: rs.metadata.creation_timestamp)

        legs = []
        for rs in owned:
            created = rs.metadata.creation_timestamp
            if created > end_time:
                continue
            legs.append({'start': created, 'containers': _containers_from_replicaset(rs)})

        boundary = None
        in_window = []
        for leg in legs:
            if leg['start'] < start_time:
                boundary = leg  # keep overwriting -- we want the latest one before the window
            else:
                in_window.append(leg)
        final = ([boundary] if boundary else []) + in_window

        for idx, leg in enumerate(final):
            leg['end'] = final[idx + 1]['start'] if idx + 1 < len(final) else None
            leg['current'] = (idx == len(final) - 1) and is_present_scan

        limit = d.spec.revision_history_limit if d.spec.revision_history_limit is not None else 10
        warning = None
        if boundary is None and len(owned) >= limit:
            warning = (
                f'history may be incomplete: only the last {limit} ReplicaSet revision(s) are '
                'retained (revisionHistoryLimit) and all of them fall inside the requested window'
            )

        services.append({
            'name': f'{d.metadata.namespace}/{d.metadata.name}',
            'console_url': None,
            'timeline': final,
            'warning': warning,
        })
    return services, None


def _containers_from_replicaset(rs):
    out = []
    for c in rs.spec.template.spec.containers:
        last_segment = c.image.rsplit('/', 1)[-1]
        tag = last_segment.split(':', 1)[1] if ':' in last_segment else 'latest'
        out.append({'name': c.name, 'image': c.image, 'tag': tag})
    return out
