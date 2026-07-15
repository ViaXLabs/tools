"""Jira integration -- two independent pieces:

1. Extracting a Jira issue key (e.g. TEAM-1856) from a commit message and
   linking to it. This needs no API access at all, just your Jira base
   URL, since the browse link format ({base_url}/browse/{key}) is
   universal and always correct.

2. Optionally fetching the issue's live summary/status via the Jira REST
   API, if you want more than a bare link. Off by default since it needs
   credentials and an extra request per unique issue referenced.

   Auth as written uses Atlassian Cloud's convention (Basic auth with your
   account email + an API token from id.atlassian.com). If you're on Jira
   Server/Data Center instead, swap the `auth=` line in fetch_issue() for
   a Bearer personal access token -- one line to change, called out again
   in the README.
"""

import re

import requests

_KEY_RE = re.compile(r'\b([A-Z][A-Z0-9]{1,9}-\d+)\b')

_cache = {}


def extract_keys(text):
    """Returns Jira issue keys found in `text`, in order, deduplicated."""
    if not text:
        return []
    seen = []
    for m in _KEY_RE.finditer(text):
        key = m.group(1)
        if key not in seen:
            seen.append(key)
    return seen


def browse_url(base_url, key):
    return f"{base_url.rstrip('/')}/browse/{key}"


def fetch_issue(base_url, email, api_token, key, timeout=15):
    """Returns {'summary': ..., 'status': ...} or None on failure. Cached
    per issue key for the run, since the same ticket often gets
    referenced by several deploys."""
    if key in _cache:
        return _cache[key]
    try:
        resp = requests.get(
            f"{base_url.rstrip('/')}/rest/api/3/issue/{key}",
            params={'fields': 'summary,status'},
            auth=(email, api_token),  # Atlassian Cloud; see module docstring for Data Center
            timeout=timeout,
        )
        if resp.status_code != 200:
            _cache[key] = None
            return None
        data = resp.json()
        fields = data.get('fields') or {}
        result = {
            'summary': fields.get('summary'),
            'status': (fields.get('status') or {}).get('name'),
        }
    except requests.RequestException:
        result = None
    _cache[key] = result
    return result
