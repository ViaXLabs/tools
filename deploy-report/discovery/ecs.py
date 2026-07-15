"""ECS discovery: walk every cluster in a region, every service in each
cluster, and read the container image actually deployed by the service's
PRIMARY deployment (i.e. what's live now, not a stuck/rolling-back one).

Nothing here imports boto3 directly -- callers pass in an already-created
boto3 Session so this module works the same whether you're using a plain
profile or an assumed cross-account role.
"""

from . import common


def discover(session, region, team_key, environment_key):
    """Return a list of ECS cluster dicts for one region."""
    ecs = session.client('ecs', region_name=region)
    clusters = []

    cluster_arns = []
    for page in ecs.get_paginator('list_clusters').paginate():
        cluster_arns.extend(page['clusterArns'])
    if not cluster_arns:
        return clusters

    for i in range(0, len(cluster_arns), 100):  # describe_clusters caps at 100
        batch = cluster_arns[i:i + 100]
        resp = ecs.describe_clusters(clusters=batch, include=['TAGS'])
        for c in resp['clusters']:
            tags = {t['key']: t['value'] for t in c.get('tags', [])}
            clusters.append({
                'platform': 'ECS',
                'name': c['clusterName'],
                'arn': c['clusterArn'],
                'region': region,
                'team': common.get_tag_ci(tags, team_key) or 'Unassigned',
                'environment': common.get_tag_ci(tags, environment_key) or 'Unknown',
                'services': _discover_services(ecs, c['clusterName'], region),
                'console_url': (
                    f"https://{region}.console.aws.amazon.com/ecs/v2/clusters/"
                    f"{c['clusterName']}/services?region={region}"
                ),
            })
    return clusters


def _discover_services(ecs, cluster_name, region):
    service_arns = []
    for page in ecs.get_paginator('list_services').paginate(cluster=cluster_name):
        service_arns.extend(page['serviceArns'])

    services = []
    task_def_cache = {}
    for i in range(0, len(service_arns), 10):  # describe_services caps at 10
        batch = service_arns[i:i + 10]
        resp = ecs.describe_services(cluster=cluster_name, services=batch, include=['TAGS'])
        for svc in resp['services']:
            # Use the PRIMARY deployment's task def -- this is what's actually
            # serving traffic right now, even mid-rollout.
            primary = next((d for d in svc.get('deployments', []) if d.get('status') == 'PRIMARY'), None)
            task_def_arn = (primary or {}).get('taskDefinition') or svc.get('taskDefinition')

            if task_def_arn not in task_def_cache:
                task_def_cache[task_def_arn] = _describe_task_def(ecs, task_def_arn)
            containers = task_def_cache[task_def_arn]

            services.append({
                'name': svc['serviceName'],
                'task_definition_arn': task_def_arn,
                'desired_count': svc.get('desiredCount'),
                'running_count': svc.get('runningCount'),
                'containers': containers,  # [{name, image, tag}, ...]
                'console_url': (
                    f"https://{region}.console.aws.amazon.com/ecs/v2/clusters/"
                    f"{cluster_name}/services/{svc['serviceName']}/health?region={region}"
                ),
            })
    return services


def _describe_task_def(ecs, task_def_arn):
    if not task_def_arn:
        return []
    resp = ecs.describe_task_definition(taskDefinition=task_def_arn)
    return common.containers_from_task_def(resp['taskDefinition'])
