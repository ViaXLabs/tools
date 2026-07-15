"""Loads the team -> [repo, ...] registry that the report cross-checks
deployed images against, to surface coverage gaps (registered repos never
seen deployed, or deployed repos that aren't registered to any team).

Two modes, set via config `github.team_registry.mode`:

  static (default): read a plain JSON file you maintain by hand --
    {"Payments": ["myorg/payments-api", ...], ...}
    See teams.example.json for the format.

  github_topics: derive it dynamically by listing every repo in a GitHub
    org and bucketing repos by a `team-<name>` topic (GitHub's repo-level
    tags) -- no file to keep in sync, since the source of truth becomes
    whatever topics are actually applied on GitHub. See
    admin-tools/manage_team_topics.py for a separate script that applies
    those topics based on today's static file, so you can migrate from
    one mode to the other without a big-bang cutover.
"""

import json

import requests

_API = 'https://api.github.com'


def load_team_repos(config, github_token=None):
    cfg = (config.get('github', {}) or {}).get('team_registry', {}) or {}
    mode = cfg.get('mode', 'static')
    if mode == 'github_topics':
        return _load_from_github_topics(cfg, github_token)
    return _load_from_static_file(cfg)


def _load_from_static_file(cfg):
    path = cfg.get('static_file')
    if not path:
        return {}
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f'  team registry file not found: {path} -- skipping repo coverage.')
        return {}
    except json.JSONDecodeError as e:
        print(f'  team registry file {path} is not valid JSON ({e}) -- skipping repo coverage.')
        return {}


def _load_from_github_topics(cfg, github_token):
    org = cfg.get('org')
    if not org:
        print('  github_topics team registry needs github.team_registry.org set -- skipping.')
        return {}
    prefix = cfg.get('team_topic_prefix', 'team-')
    required_topic = cfg.get('required_topic')
    name_overrides = cfg.get('team_name_overrides', {}) or {}

    headers = {'Accept': 'application/vnd.github+json'}
    if github_token:
        headers['Authorization'] = f'Bearer {github_token}'

    registry = {}
    page = 1
    while True:
        resp = requests.get(
            f'{_API}/orgs/{org}/repos',
            headers=headers, params={'per_page': 100, 'page': page, 'type': 'all'}, timeout=30,
        )
        resp.raise_for_status()
        repos = resp.json()
        if not repos:
            break
        for repo in repos:
            topics = repo.get('topics') or []
            if required_topic and required_topic not in topics:
                continue
            for topic in topics:
                if not topic.startswith(prefix):
                    continue
                team_name = name_overrides.get(topic) or _titleize(topic[len(prefix):])
                registry.setdefault(team_name, []).append(repo['full_name'])
        page += 1
    return registry


def _titleize(topic_suffix):
    return ' '.join(word.capitalize() for word in topic_suffix.replace('_', '-').split('-'))
