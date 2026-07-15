"""New Relic NerdGraph client -- runs an NRQL query for deployment markers
on one entity, to cross-reference against the ECS/EKS-derived timeline.

Verified against New Relic's NerdGraph docs for the request shape:
POST https://api.newrelic.com/graphql (or api.eu.newrelic.com for EU
accounts), header `Api-Key: <user key>`, body `{"query": "{ actor {
account(id: ...) { nrql(query: \"...\") { results } } } }"}`.

What ISN'T fully verified: which event type your deployment markers
actually land in. New Relic has two generations of this feature --
the classic `Deployment` event type, and the newer `changeTrackingEvent`
type. `newrelic.event_type` in config defaults to `Deployment` (the more
common meaning of "deployment markers"); switch it if your account uses
change tracking events instead. Same goes for which attribute holds the
entity name (`entity.name` vs the older `appName`) -- both are
configurable rather than hardcoded, and `--dump-newrelic-sample` will
show you a real record to confirm against.
"""

import datetime

import requests

REGION_ENDPOINTS = {
    'us': 'https://api.newrelic.com/graphql',
    'eu': 'https://api.eu.newrelic.com/graphql',
}


def _build_nrql(entity_name, start_time, end_time, event_type, entity_attribute, limit=200):
    since = start_time.strftime('%Y-%m-%d %H:%M:%S UTC')
    until = end_time.strftime('%Y-%m-%d %H:%M:%S UTC')
    safe_name = entity_name.replace("'", "\\'")
    return (
        f"SELECT * FROM {event_type} WHERE {entity_attribute} = '{safe_name}' "
        f"SINCE '{since}' UNTIL '{until}' LIMIT {limit}"
    )


def _run_nrql(account_id, api_key, nrql, region='us', timeout=30):
    url = REGION_ENDPOINTS.get(region, REGION_ENDPOINTS['us'])
    nrql_escaped = nrql.replace('"', '\\"')
    graphql_query = (
        '{ actor { account(id: %d) { nrql(query: "%s") { results } } } }' % (account_id, nrql_escaped)
    )
    resp = requests.post(
        url,
        headers={'Api-Key': api_key, 'Content-Type': 'application/json'},
        json={'query': graphql_query},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_markers(account_id, api_key, entity_name, start_time, end_time,
                   event_type='Deployment', entity_attribute='entity.name', region='us', timeout=30):
    """Returns (markers, errors). `errors` is None on success, or the raw
    GraphQL error list if NerdGraph returned one (bad NRQL, no access to
    the account, etc.) -- markers will be [] in that case."""
    nrql = _build_nrql(entity_name, start_time, end_time, event_type, entity_attribute)
    data = _run_nrql(account_id, api_key, nrql, region=region, timeout=timeout)
    if data.get('errors'):
        return [], data['errors']
    results = (((data.get('data') or {}).get('actor') or {}).get('account') or {}).get('nrql', {}).get('results', [])
    return [_parse_marker(r) for r in results], None


def fetch_raw_sample(account_id, api_key, entity_name, event_type='Deployment',
                      entity_attribute='entity.name', region='us', timeout=30):
    """Fetch a few raw results, unparsed, for troubleshooting -- see
    --dump-newrelic-sample in generate_report.py."""
    nrql = (
        f"SELECT * FROM {event_type} WHERE {entity_attribute} = '{entity_name.replace(chr(39), chr(92)+chr(39))}' "
        f"SINCE 1 month ago LIMIT 5"
    )
    return _run_nrql(account_id, api_key, nrql, region=region, timeout=timeout)


def _parse_marker(raw):
    ts = raw.get('timestamp')
    when = (
        datetime.datetime.fromtimestamp(ts / 1000, tz=datetime.timezone.utc)
        if isinstance(ts, (int, float)) else None
    )
    version = raw.get('version') or raw.get('revision') or raw.get('commit')
    return {
        'timestamp': when,
        'version': version,
        'user': raw.get('user'),
        'deep_link': raw.get('deepLink'),
        'deployment_id': raw.get('deploymentId'),
    }
