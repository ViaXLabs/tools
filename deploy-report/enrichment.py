"""Optional cross-checks against Harness (pipeline execution history) and
New Relic (deployment markers), layered onto the ECS/EKS-derived timeline
in --mode history. Both are independent and best-effort: a lookup failure
for one service just leaves a note on that service rather than failing
the whole report, and neither is required for the ECS/EKS timeline itself
to work.
"""

import os

import harness_client
import newrelic_client
import nexus_client
from discovery import common


def attach_nexus_info(clusters, config):
    """Applies to both --mode current/asof (services have `containers`)
    and --mode history (services have `timeline`), since a link to the
    image in Nexus is useful regardless of which report mode you're in."""
    cfg = config.get('nexus', {}) or {}
    if not cfg.get('enabled'):
        return clusters

    base_url = (cfg.get('base_url') or '').rstrip('/')
    username = os.environ.get(cfg.get('username_env_var', 'NEXUS_USERNAME')) or None
    password = os.environ.get(cfg.get('password_env_var', 'NEXUS_PASSWORD')) or None
    registry_map = cfg.get('registry_repository_map', {}) or {}
    detect_base = cfg.get('detect_base_image', False)

    def enrich(container):
        registry_host, image_path, tag = common.split_image_reference(container.get('image'))
        if not registry_host or registry_host not in registry_map or not base_url:
            return
        repository = registry_map[registry_host]
        info = nexus_client.links_for_image(base_url, username, password, repository, image_path, tag)
        if detect_base:
            info['base_image'] = nexus_client.detect_base_image(registry_host, username, password, image_path, tag)
        container['nexus'] = info

    for cluster in clusters:
        for service in cluster.get('services', []):
            for container in service.get('containers', []):
                enrich(container)
            for leg in service.get('timeline', []):
                for container in leg.get('containers', []):
                    enrich(container)
    return clusters


def attach_harness_history(clusters, config, start_time, end_time):
    cfg = config.get('harness', {}) or {}
    if not cfg.get('enabled'):
        return clusters

    key_var = cfg.get('api_key_env_var', 'HARNESS_API_KEY')
    api_key = os.environ.get(key_var)
    if not api_key:
        print(f'  Harness is enabled in config but ${key_var} is not set -- skipping Harness lookups.')
        return clusters

    base_url = cfg.get('base_url', harness_client.DEFAULT_BASE_URL)
    account_id = cfg.get('account_id')
    scopes = cfg.get('scopes') or []
    service_overrides = cfg.get('service_id_overrides', {}) or {}
    env_overrides = cfg.get('environment_id_overrides', {}) or {}

    for cluster in clusters:
        env_id = env_overrides.get(cluster.get('environment'), cluster.get('environment'))
        for service in cluster.get('services', []):
            service_id = service_overrides.get(service['name'], service['name'])
            executions, errors = [], []
            for scope in scopes:
                try:
                    executions.extend(harness_client.fetch_executions(
                        base_url, account_id, scope.get('org_id'), scope.get('project_id'),
                        api_key, start_time, end_time,
                        service_id=service_id, environment_id=env_id,
                    ))
                except Exception as e:
                    errors.append(str(e))
            executions.sort(key=lambda e: e.get('started_at') or start_time, reverse=True)
            service['harness_executions'] = executions
            if errors and not executions:
                service['harness_error'] = '; '.join(errors)
    return clusters


def attach_newrelic_markers(clusters, config, start_time, end_time):
    cfg = config.get('newrelic', {}) or {}
    if not cfg.get('enabled'):
        return clusters

    key_var = cfg.get('api_key_env_var', 'NEW_RELIC_API_KEY')
    api_key = os.environ.get(key_var)
    if not api_key:
        print(f'  New Relic is enabled in config but ${key_var} is not set -- skipping New Relic lookups.')
        return clusters

    account_id = cfg.get('account_id')
    overrides = cfg.get('entity_name_overrides', {}) or {}
    event_type = cfg.get('event_type', 'Deployment')
    entity_attribute = cfg.get('entity_attribute', 'entity.name')
    region = cfg.get('region', 'us')

    for cluster in clusters:
        for service in cluster.get('services', []):
            override_key = f"{service['name']}/{cluster.get('environment')}"
            entity_name = overrides.get(override_key, service['name'])
            try:
                markers, errors = newrelic_client.fetch_markers(
                    account_id, api_key, entity_name, start_time, end_time,
                    event_type=event_type, entity_attribute=entity_attribute, region=region,
                )
                service['newrelic_markers'] = markers
                if errors:
                    service['newrelic_error'] = str(errors)
            except Exception as e:
                service['newrelic_markers'] = []
                service['newrelic_error'] = str(e)
    return clusters
