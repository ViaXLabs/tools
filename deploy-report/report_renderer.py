"""Turns the flat list of cluster dicts produced by discovery/ into the
grouped structure the template needs, plus a search blob per cluster for
the in-page filter box, then renders report_template.html to disk.
"""

import datetime
from collections import defaultdict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = Path(__file__).parent / 'templates'


def _deployed_repos(clusters_for_team):
    repos = set()
    for cluster in clusters_for_team:
        for svc in cluster.get('services', []):
            for c in svc.get('containers', []):
                if c.get('github_repo'):
                    repos.add(c['github_repo'])
            for leg in svc.get('timeline', []):
                for c in leg.get('containers', []):
                    if c.get('github_repo'):
                        repos.add(c['github_repo'])
    return repos


def _lookup_team_repos(team_repos, team_name):
    if not team_repos:
        return None
    if team_name in team_repos:
        return team_repos[team_name]
    lower_map = {k.lower(): v for k, v in team_repos.items()}
    return lower_map.get((team_name or '').lower())


def compute_coverage(team_name, team_repos, clusters_for_team):
    """None if this team isn't in the registry at all (nothing to compare
    against); otherwise a dict of registered/deployed counts plus the two
    kinds of gaps worth a human's attention."""
    registered = _lookup_team_repos(team_repos, team_name)
    if registered is None:
        return None
    registered_set = set(registered)
    deployed = _deployed_repos(clusters_for_team)
    return {
        'registered_count': len(registered_set),
        'deployed_count': len(deployed & registered_set),
        'missing': sorted(registered_set - deployed),
        'unregistered': sorted(deployed - registered_set),
    }


def env_class(name):
    """Map an environment name to a CSS class for consistent color-coding,
    regardless of exactly how each team spells it (dev/development,
    systest/sit/test, qa/staging, prod/production, ...)."""
    n = (name or '').lower()
    if 'prod' in n:
        return 'env-prod'
    if 'qa' in n or 'stag' in n:
        return 'env-qa'
    if 'sys' in n or 'sit' in n or 'test' in n:
        return 'env-systest'
    if 'dev' in n:
        return 'env-dev'
    return 'env-other'


def _search_blob(cluster):
    parts = [cluster.get('team', ''), cluster.get('environment', ''),
              cluster.get('platform', ''), cluster.get('name', '')]
    for s in cluster.get('services', []):
        parts.append(s.get('name', ''))
        for c in s.get('containers', []):
            parts.append(c.get('tag', ''))
            commit = c.get('commit')
            if commit:
                parts.append(commit.get('short_sha') or '')
                parts.append(commit.get('message') or '')
                parts.append(commit.get('author') or '')
                for j in commit.get('jira', []) or []:
                    parts.append(j.get('key') or '')
                    parts.append(j.get('summary') or '')
    return ' '.join(str(p) for p in parts if p).lower()


def group_by_team(clusters):
    grouped = defaultdict(lambda: defaultdict(list))
    for c in clusters:
        grouped[c['team']][c['environment']].append(c)
    # Stable, alphabetical ordering so re-runs produce a diffable report.
    return {
        team: dict(sorted(envs.items()))
        for team, envs in sorted(grouped.items())
    }


def compute_totals(clusters):
    total_services = 0
    drifted = 0
    for c in clusters:
        for s in c.get('services', []):
            total_services += 1
            if s.get('desired_count') is not None and s.get('running_count') is not None:
                if s['desired_count'] != s['running_count']:
                    drifted += 1
    return {'clusters': len(clusters), 'services': total_services, 'drifted': drifted}


def render(clusters, output_path, snapshot_label=None, team_repos=None):
    for c in clusters:
        c['_search'] = _search_blob(c)

    grouped = group_by_team(clusters)
    totals = compute_totals(clusters)
    coverage = {
        team: compute_coverage(team, team_repos, [c for envs in team_envs.values() for c in envs])
        for team, team_envs in grouped.items()
    } if team_repos else {}

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    env.globals['env_class'] = env_class
    template = env.get_template('report_template.html')

    html = template.render(
        grouped=grouped,
        totals=totals,
        generated_at=datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'),
        snapshot_label=snapshot_label,
        coverage=coverage,
    )

    out = Path(output_path)
    out.write_text(html, encoding='utf-8')
    return str(out)


def _search_blob_history(cluster):
    parts = [cluster.get('team', ''), cluster.get('environment', ''),
              cluster.get('platform', ''), cluster.get('name', '')]
    for s in cluster.get('services', []):
        parts.append(s.get('name', ''))
        for leg in s.get('timeline', []):
            for c in leg.get('containers', []):
                parts.append(c.get('tag', ''))
                commit = c.get('commit')
                if commit:
                    parts.append(commit.get('short_sha') or '')
                    parts.append(commit.get('message') or '')
                    parts.append(commit.get('author') or '')
                    for j in commit.get('jira', []) or []:
                        parts.append(j.get('key') or '')
                        parts.append(j.get('summary') or '')
        for ex in s.get('harness_executions', []) or []:
            parts.append(ex.get('pipeline_name') or '')
            parts.extend(ex.get('artifact_versions') or [])
        for m in s.get('newrelic_markers', []) or []:
            parts.append(m.get('version') or '')
    return ' '.join(str(p) for p in parts if p).lower()


def compute_history_totals(clusters):
    services = 0
    legs = 0
    for c in clusters:
        for s in c.get('services', []):
            services += 1
            legs += len(s.get('timeline', []))
    return {'clusters': len(clusters), 'services': services, 'legs': legs}


def _format_leg_labels(leg, start_time, end_time, is_present_scan):
    if leg['start'] < start_time:
        start_label = f"before {start_time.strftime('%Y-%m-%d')}"
    else:
        start_label = leg['start'].strftime('%Y-%m-%d')
    if leg.get('end') is None:
        end_label = 'current' if leg.get('current') else end_time.strftime('%Y-%m-%d')
    else:
        end_label = leg['end'].strftime('%Y-%m-%d')
    return start_label, end_label


def render_history(clusters, output_path, start_time, end_time, is_present_scan=True, team_repos=None):
    for c in clusters:
        c['_search'] = _search_blob_history(c)
        for s in c.get('services', []):
            for leg in s.get('timeline', []):
                leg['start_label'], leg['end_label'] = _format_leg_labels(
                    leg, start_time, end_time, is_present_scan)
            for ex in s.get('harness_executions', []) or []:
                ex['started_at_label'] = (
                    ex['started_at'].strftime('%Y-%m-%d %H:%M UTC') if ex.get('started_at') else 'unknown time'
                )
            for m in s.get('newrelic_markers', []) or []:
                m['timestamp_label'] = (
                    m['timestamp'].strftime('%Y-%m-%d %H:%M UTC') if m.get('timestamp') else 'unknown time'
                )

    grouped = group_by_team(clusters)
    totals = compute_history_totals(clusters)
    coverage = {
        team: compute_coverage(team, team_repos, [c for envs in team_envs.values() for c in envs])
        for team, team_envs in grouped.items()
    } if team_repos else {}
    range_label = f"{start_time.strftime('%Y-%m-%d')} \u2192 {end_time.strftime('%Y-%m-%d')}"

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    env.globals['env_class'] = env_class
    template = env.get_template('history_template.html')

    html = template.render(grouped=grouped, totals=totals, range_label=range_label, coverage=coverage)

    out = Path(output_path)
    out.write_text(html, encoding='utf-8')
    return str(out)
