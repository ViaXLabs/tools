"""Harness NextGen API client -- pulls pipeline execution history so it can
be cross-referenced against the ECS/EKS-derived deployment timeline.

Verified against Harness's public API docs for the request shape (auth
header, endpoint, body): POST to
  {base_url}/gateway/pipeline/api/pipelines/execution/summary
with an `x-api-key` header and a JSON body filtering by
`moduleProperties.cd.serviceIdentifiers` / `environmentIdentifiers`.

What ISN'T fully verified: the exact nested field names inside each
execution summary object can vary a bit by which CD module version and
stage types your pipelines use. `_parse_execution` below is the one place
to adjust if your account's response looks different -- run
`--dump-harness-sample SERVICE_ID` first to see a real example and confirm
the paths before trusting the parsed output.
"""

import datetime

import requests

DEFAULT_BASE_URL = 'https://app.harness.io'
_EXECUTION_PATH = '/gateway/pipeline/api/pipelines/execution/summary'


def fetch_executions(base_url, account_id, org_id, project_id, api_key, start_time, end_time,
                      service_id=None, environment_id=None, page_size=100, max_pages=20, timeout=30):
    """Returns parsed execution dicts (newest first) that fall inside
    [start_time, end_time]. Filters client-side on startTs regardless of
    what the server-side time filter does, as a safety net."""
    url = f'{base_url}{_EXECUTION_PATH}'
    headers = {'x-api-key': api_key, 'Content-Type': 'application/json'}
    module_props = {'cd': {}}
    if service_id:
        module_props['cd']['serviceIdentifiers'] = [service_id]
    if environment_id:
        module_props['cd']['environmentIdentifiers'] = [environment_id]
    body = {'filterType': 'PipelineExecution', 'moduleProperties': module_props}

    out = []
    page = 0
    while page < max_pages:
        params = {
            'routingId': account_id, 'accountIdentifier': account_id,
            'orgIdentifier': org_id, 'projectIdentifier': project_id,
            'page': page, 'size': page_size, 'sort': 'startTs,DESC',
        }
        resp = requests.post(url, headers=headers, params=params, json=body, timeout=timeout)
        resp.raise_for_status()
        content = (resp.json().get('data') or {}).get('content') or []
        if not content:
            break

        stop = False
        for item in content:
            parsed = _parse_execution(item, base_url, account_id, org_id, project_id)
            if parsed is None:
                continue
            started = parsed.get('started_at')
            if started and started < start_time:
                stop = True  # sorted DESC -- everything after this is even older
                continue
            if started and started > end_time:
                continue
            out.append(parsed)

        if stop or len(content) < page_size:
            break
        page += 1
    return out


def fetch_raw_sample(base_url, account_id, org_id, project_id, api_key, service_id=None, size=3, timeout=30):
    """Fetch a few raw execution records, unparsed, for troubleshooting --
    see --dump-harness-sample in generate_report.py."""
    url = f'{base_url}{_EXECUTION_PATH}'
    headers = {'x-api-key': api_key, 'Content-Type': 'application/json'}
    module_props = {'cd': {}}
    if service_id:
        module_props['cd']['serviceIdentifiers'] = [service_id]
    body = {'filterType': 'PipelineExecution', 'moduleProperties': module_props}
    params = {
        'routingId': account_id, 'accountIdentifier': account_id,
        'orgIdentifier': org_id, 'projectIdentifier': project_id,
        'page': 0, 'size': size, 'sort': 'startTs,DESC',
    }
    resp = requests.post(url, headers=headers, params=params, json=body, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _parse_execution(item, base_url, account_id, org_id, project_id):
    try:
        start_ms = item.get('startTs')
        started_at = (
            datetime.datetime.fromtimestamp(start_ms / 1000, tz=datetime.timezone.utc)
            if start_ms else None
        )

        cd_info = (item.get('moduleInfo') or {}).get('cd') or {}
        service_infos = cd_info.get('serviceInfoList') or []
        if not service_infos and cd_info.get('serviceInfo'):
            service_infos = [cd_info['serviceInfo']]

        service_names, artifact_versions = [], []
        for svc in service_infos:
            if not svc:
                continue
            name = svc.get('displayName') or svc.get('identifier')
            if name:
                service_names.append(name)
            artifact = svc.get('artifactInfo') or {}
            version = artifact.get('tag') or artifact.get('version')
            display = artifact.get('displayName') or (
                f"{artifact.get('imagePath', '')}:{version}" if version else None)
            if display:
                artifact_versions.append(display)

        plan_execution_id = item.get('planExecutionId')
        pipeline_id = item.get('pipelineIdentifier')
        execution_url = None
        if plan_execution_id and pipeline_id:
            execution_url = (
                f'{base_url}/ng/account/{account_id}/cd/orgs/{org_id}/projects/{project_id}'
                f'/pipelines/{pipeline_id}/executions/{plan_execution_id}/pipeline'
            )

        trigger_info = item.get('executionTriggerInfo') or {}
        triggered_by = (trigger_info.get('triggeredBy') or {}).get('identifier')

        return {
            'pipeline_name': item.get('name') or pipeline_id,
            'status': item.get('status'),
            'started_at': started_at,
            'service_names': service_names,
            'artifact_versions': artifact_versions,
            'triggered_by': triggered_by,
            'execution_url': execution_url,
        }
    except Exception:
        # Don't let one oddly-shaped record take down the whole report --
        # skip it. If this keeps happening, --dump-harness-sample and fix
        # the field paths above.
        return None
