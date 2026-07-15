"""ECS history: reconstructs each service's version timeline from its task
definition family's revision history.

ECS keeps every revision it has ever registered for a family -- active or
deregistered -- indefinitely, each stamped with `registeredAt`. That's a
built-in changelog we can walk without any extra permissions or a
CloudTrail trail.

The one assumption this makes: `registeredAt` is a good proxy for "this
went live". That holds in the overwhelmingly common CI/CD pattern where a
pipeline registers a new revision and immediately deploys it, but it isn't
a hard guarantee -- a revision registered but never deployed would still
show up as a "leg" here. If that turns out to matter for your team, the
next step up in precision is CloudTrail's UpdateService call history,
which is a documented enhancement, not implemented here.
"""

from . import common


def discover_history(session, region, team_key, environment_key, start_time, end_time,
                      is_present_scan=True):
    """Return ECS cluster dicts whose services carry a `timeline` (oldest
    to newest) instead of a single current `containers` list."""
    ecs = session.client('ecs', region_name=region)
    clusters = []

    cluster_arns = []
    for page in ecs.get_paginator('list_clusters').paginate():
        cluster_arns.extend(page['clusterArns'])
    if not cluster_arns:
        return clusters

    for i in range(0, len(cluster_arns), 100):
        batch = cluster_arns[i:i + 100]
        resp = ecs.describe_clusters(clusters=batch, include=['TAGS'])
        for c in resp['clusters']:
            tags = {t['key']: t['value'] for t in c.get('tags', [])}
            cluster_name = c['clusterName']
            clusters.append({
                'platform': 'ECS',
                'name': cluster_name,
                'arn': c['clusterArn'],
                'region': region,
                'team': common.get_tag_ci(tags, team_key) or 'Unassigned',
                'environment': common.get_tag_ci(tags, environment_key) or 'Unknown',
                'services': _service_histories(ecs, cluster_name, region, start_time, end_time, is_present_scan),
                'console_url': (
                    f"https://{region}.console.aws.amazon.com/ecs/v2/clusters/{cluster_name}/services?region={region}"
                ),
            })
    return clusters


def _service_histories(ecs, cluster_name, region, start_time, end_time, is_present_scan):
    service_arns = []
    for page in ecs.get_paginator('list_services').paginate(cluster=cluster_name):
        service_arns.extend(page['serviceArns'])

    services = []
    family_cache = {}
    for i in range(0, len(service_arns), 10):
        batch = service_arns[i:i + 10]
        resp = ecs.describe_services(cluster=cluster_name, services=batch)
        for svc in resp['services']:
            current_arn = svc.get('taskDefinition')
            if not current_arn:
                continue
            family = current_arn.rsplit('/', 1)[-1].rsplit(':', 1)[0]

            if family not in family_cache:
                family_cache[family] = _family_timeline(ecs, family, start_time, end_time)
            legs = [dict(leg) for leg in family_cache[family]]  # per-service copy before we annotate end/current

            for idx, leg in enumerate(legs):
                leg['end'] = legs[idx + 1]['start'] if idx + 1 < len(legs) else None
                leg['current'] = (idx == len(legs) - 1) and is_present_scan

            services.append({
                'name': svc['serviceName'],
                'console_url': (
                    f"https://{region}.console.aws.amazon.com/ecs/v2/clusters/"
                    f"{cluster_name}/services/{svc['serviceName']}/health?region={region}"
                ),
                'timeline': legs,
            })
    return services


def _family_timeline(ecs, family, start_time, end_time):
    """Walk a task definition family's revisions, newest first, describing
    just enough of them to cover [start_time, end_time] plus one boundary
    revision from before start_time (the state the window started in)."""
    arns = []
    for status in ('ACTIVE', 'INACTIVE'):
        for page in ecs.get_paginator('list_task_definitions').paginate(
            familyPrefix=family, status=status, sort='DESC'
        ):
            arns.extend(page['taskDefinitionArns'])
    arns.sort(key=lambda a: int(a.rsplit(':', 1)[-1]), reverse=True)

    legs = []
    for arn in arns:
        resp = ecs.describe_task_definition(taskDefinition=arn)
        td = resp['taskDefinition']
        reg_at = td.get('registeredAt')
        if reg_at is None:
            continue
        if reg_at > end_time:
            continue  # newer than the window we care about; keep scanning older revisions
        legs.append({'start': reg_at, 'containers': common.containers_from_task_def(td)})
        if reg_at < start_time:
            break  # this is the boundary revision; anything older isn't needed
    legs.reverse()  # chronological, oldest first
    return legs
