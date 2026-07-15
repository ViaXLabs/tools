#!/usr/bin/env python3
"""
Deployment Manifest Generator
==============================
Scans ECS + EKS clusters across configured AWS accounts/regions and
renders a single HTML report, in one of three modes:

  --mode current (default)
      What's deployed right now. Live API scan.

  --mode history --start-date YYYY-MM-DD --end-date YYYY-MM-DD
      What changed during a date range, reconstructed from each
      platform's own revision history (ECS task definition revisions,
      EKS ReplicaSet history). Defaults to the last 90 days if no dates
      are given.

  --mode asof --as-of YYYY-MM-DD
      A snapshot of what was live as of a specific past date, derived
      from the same history reconstruction as --mode history.

Usage:
    python generate_report.py --demo                                   # current, fake data
    python generate_report.py --demo --mode history                    # history, fake data
    python generate_report.py --demo --mode asof --as-of 2026-06-01     # asof, fake data
    python generate_report.py --config config.yaml                     # real run
    python generate_report.py --config config.yaml --mode history --start-date 2026-04-01 --end-date 2026-07-01
"""

import argparse
import datetime
import json
import os
import sys

import yaml

from discovery import common, ecs as ecs_discovery, eks as eks_discovery
from discovery import ecs_history, eks_history
import github_lookup
import harness_client
import newrelic_client
import jira_client
import team_registry
import enrichment
import report_renderer
import demo_data


def load_config(path):
    with open(path, 'r') as f:
        return yaml.safe_load(f) or {}


def parse_date(s):
    return datetime.datetime.strptime(s, '%Y-%m-%d').replace(tzinfo=datetime.timezone.utc)


def get_session(profile_cfg):
    import boto3  # imported lazily so --demo works without boto3 installed
    if profile_cfg.get('role_arn'):
        base = boto3.Session(profile_name=profile_cfg.get('base_profile'))
        sts = base.client('sts')
        creds = sts.assume_role(
            RoleArn=profile_cfg['role_arn'],
            RoleSessionName='deployment-manifest-report',
        )['Credentials']
        return boto3.Session(
            aws_access_key_id=creds['AccessKeyId'],
            aws_secret_access_key=creds['SecretAccessKey'],
            aws_session_token=creds['SessionToken'],
        )
    return boto3.Session(profile_name=profile_cfg.get('name'))


def _for_each_region(config, fn):
    """Call fn(session, region, label) for every configured AWS profile/region
    and flatten the results."""
    out = []
    for profile_cfg in config.get('aws', {}).get('profiles', []):
        label = profile_cfg.get('name', 'profile')
        session = get_session(profile_cfg)
        for region in profile_cfg.get('regions', []):
            out.extend(fn(session, region, label))
    return out


def collect_clusters(config):
    team_key = config.get('tags', {}).get('team_key', 'Team')
    env_key = config.get('tags', {}).get('environment_key', 'Environment')
    eks_cfg = config.get('eks', {}) or {}

    def scan(session, region, label):
        print(f'  scanning ECS in {label}/{region} ...', file=sys.stderr)
        result = ecs_discovery.discover(session, region, team_key, env_key)
        if eks_cfg.get('enabled'):
            print(f'  scanning EKS in {label}/{region} ...', file=sys.stderr)
            result += eks_discovery.discover(
                session, region, team_key, env_key, eks_cfg.get('kubeconfig_context_overrides', {}))
        return result

    return _for_each_region(config, scan)


def collect_history_clusters(config, start_time, end_time, is_present_scan=True):
    team_key = config.get('tags', {}).get('team_key', 'Team')
    env_key = config.get('tags', {}).get('environment_key', 'Environment')
    eks_cfg = config.get('eks', {}) or {}

    def scan(session, region, label):
        print(f'  reconstructing ECS history in {label}/{region} ...', file=sys.stderr)
        result = ecs_history.discover_history(
            session, region, team_key, env_key, start_time, end_time, is_present_scan)
        if eks_cfg.get('enabled'):
            print(f'  reconstructing EKS history in {label}/{region} ...', file=sys.stderr)
            result += eks_history.discover_history(
                session, region, team_key, env_key, start_time, end_time,
                eks_cfg.get('kubeconfig_context_overrides', {}), is_present_scan)
        return result

    return _for_each_region(config, scan)


def attach_commit_info(clusters, config):
    """Resolves tag -> commit for every container we found, whether it's
    hanging off a current-state `containers` list or a history `timeline`.
    Also extracts any Jira issue keys (e.g. TEAM-1856) out of the commit
    message and attaches links, if jira.base_url is configured."""
    gh_cfg = config.get('github', {}) or {}
    default_org = gh_cfg.get('default_org')
    overrides = gh_cfg.get('repo_overrides', {}) or {}
    sha_pattern = gh_cfg.get('tag_sha_pattern')
    token = os.environ.get(gh_cfg.get('token_env_var', 'GITHUB_TOKEN'), '') or None

    jira_cfg = config.get('jira', {}) or {}
    jira_base_url = jira_cfg.get('base_url') if jira_cfg.get('enabled') else None
    jira_email = os.environ.get(jira_cfg.get('email_env_var', 'JIRA_EMAIL')) or None
    jira_token = os.environ.get(jira_cfg.get('api_token_env_var', 'JIRA_API_TOKEN')) or None

    def resolve_container(container):
        sha = common.extract_sha(container.get('tag'), sha_pattern)
        repo_name = common.guess_repo_name(container.get('image'))
        repo_full = overrides.get(repo_name) or (
            f'{default_org}/{repo_name}' if default_org and repo_name else None
        )
        container['github_repo'] = repo_full
        commit = github_lookup.resolve(repo_full, sha, token) if (repo_full and sha) else None
        container['commit'] = commit

        if commit and jira_base_url:
            jira_items = []
            for key in jira_client.extract_keys(commit.get('message')):
                item = {'key': key, 'url': jira_client.browse_url(jira_base_url, key)}
                if jira_cfg.get('fetch_details') and jira_email and jira_token:
                    details = jira_client.fetch_issue(jira_base_url, jira_email, jira_token, key)
                    if details:
                        item.update(details)
                jira_items.append(item)
            commit['jira'] = jira_items

    for cluster in clusters:
        for service in cluster.get('services', []):
            for container in service.get('containers', []):
                resolve_container(container)
            for leg in service.get('timeline', []):
                for container in leg.get('containers', []):
                    resolve_container(container)
    return clusters


def snapshot_from_history(history_clusters):
    """Collapse each service's timeline down to its last (most recent as of
    the requested date) leg, in the same shape --mode current uses, so it
    can go through the same report_renderer.render()."""
    snapshot = []
    for c in history_clusters:
        services = []
        for s in c.get('services', []):
            timeline = s.get('timeline') or []
            if not timeline:
                continue
            last = timeline[-1]
            services.append({
                'name': s['name'],
                'console_url': s.get('console_url'),
                'desired_count': None,
                'running_count': None,
                'containers': last['containers'],
            })
        snapshot.append({
            'platform': c['platform'], 'name': c['name'], 'region': c.get('region'),
            'team': c['team'], 'environment': c['environment'],
            'console_url': c.get('console_url'), 'warning': c.get('warning'),
            'services': services,
        })
    return snapshot


def main():
    parser = argparse.ArgumentParser(description='Generate an HTML deployment manifest across ECS + EKS.')
    parser.add_argument('--config', default='config.yaml', help='Path to config YAML (default: config.yaml)')
    parser.add_argument('--output', default=None, help='Output HTML path (default depends on --mode)')
    parser.add_argument('--demo', action='store_true', help='Use fake sample data instead of calling AWS/GitHub')
    parser.add_argument('--mode', choices=['current', 'history', 'asof'], default='current')
    parser.add_argument('--start-date', help='YYYY-MM-DD -- history mode (default: 90 days before --end-date)')
    parser.add_argument('--end-date', help='YYYY-MM-DD -- history mode (default: today)')
    parser.add_argument('--as-of', help='YYYY-MM-DD -- required for asof mode')
    parser.add_argument('--lookback-days', type=int, default=None,
                         help='asof mode: how far before --as-of to search for the last change (default: 90, '
                              'or history.default_lookback_days from config)')
    parser.add_argument('--dump-harness-sample', metavar='SERVICE_ID',
                         help='Fetch a few raw Harness executions for one service id, write to '
                              'harness-sample.json, and exit (for checking/adjusting harness_client.py '
                              'against your account\'s actual response shape)')
    parser.add_argument('--dump-newrelic-sample', metavar='ENTITY_NAME',
                         help='Fetch a few raw New Relic NRQL results for one entity name, write to '
                              'newrelic-sample.json, and exit (for checking event_type / entity_attribute '
                              'in config against your account)')
    args = parser.parse_args()

    config = {} if args.demo else load_config(args.config)
    now = datetime.datetime.now(datetime.timezone.utc)
    default_lookback_days = (config.get('history', {}) or {}).get('default_lookback_days', 90)

    if args.dump_harness_sample:
        cfg = config.get('harness', {}) or {}
        api_key = os.environ.get(cfg.get('api_key_env_var', 'HARNESS_API_KEY'))
        scope = (cfg.get('scopes') or [{}])[0]
        raw = harness_client.fetch_raw_sample(
            cfg.get('base_url', harness_client.DEFAULT_BASE_URL), cfg.get('account_id'),
            scope.get('org_id'), scope.get('project_id'), api_key,
            service_id=args.dump_harness_sample,
        )
        with open('harness-sample.json', 'w') as f:
            json.dump(raw, f, indent=2, default=str)
        print('Wrote harness-sample.json -- inspect it and adjust harness_client._parse_execution if the '
              'field paths differ from what your account returns.')
        return

    if args.dump_newrelic_sample:
        cfg = config.get('newrelic', {}) or {}
        api_key = os.environ.get(cfg.get('api_key_env_var', 'NEW_RELIC_API_KEY'))
        raw = newrelic_client.fetch_raw_sample(
            cfg.get('account_id'), api_key, args.dump_newrelic_sample,
            event_type=cfg.get('event_type', 'Deployment'),
            entity_attribute=cfg.get('entity_attribute', 'entity.name'),
            region=cfg.get('region', 'us'),
        )
        with open('newrelic-sample.json', 'w') as f:
            json.dump(raw, f, indent=2, default=str)
        print('Wrote newrelic-sample.json -- check event_type / entity_attribute in config against '
              'the fields you see here.')
        return

    if args.demo:
        team_repos = demo_data.get_demo_team_repos()
    else:
        gh_cfg = config.get('github', {}) or {}
        github_token = os.environ.get(gh_cfg.get('token_env_var', 'GITHUB_TOKEN')) or None
        team_repos = team_registry.load_team_repos(config, github_token)

    if args.mode == 'current':
        if args.demo:
            clusters = demo_data.get_demo_clusters()
        else:
            print('Discovering current state...', file=sys.stderr)
            clusters = collect_clusters(config)
            print('Resolving commits against GitHub...', file=sys.stderr)
            clusters = attach_commit_info(clusters, config)
            print('Looking up images in Nexus...', file=sys.stderr)
            clusters = enrichment.attach_nexus_info(clusters, config)
        output_path = args.output or (config.get('output', {}) or {}).get('path', 'deploy-report.html')
        report_renderer.render(clusters, output_path, team_repos=team_repos)

    elif args.mode == 'history':
        end_time = parse_date(args.end_date) if args.end_date else now
        start_time = parse_date(args.start_date) if args.start_date else end_time - datetime.timedelta(days=default_lookback_days)
        is_present = end_time.date() >= now.date()

        if args.demo:
            clusters = demo_data.get_demo_history_clusters(start_time, end_time, is_present)
            clusters = demo_data.attach_demo_enrichment(clusters, start_time, end_time)
        else:
            print(f'Reconstructing history {start_time.date()} -> {end_time.date()} ...', file=sys.stderr)
            clusters = collect_history_clusters(config, start_time, end_time, is_present)
            print('Resolving commits against GitHub...', file=sys.stderr)
            clusters = attach_commit_info(clusters, config)
            print('Cross-checking against Harness...', file=sys.stderr)
            clusters = enrichment.attach_harness_history(clusters, config, start_time, end_time)
            print('Cross-checking against New Relic...', file=sys.stderr)
            clusters = enrichment.attach_newrelic_markers(clusters, config, start_time, end_time)
            print('Looking up images in Nexus...', file=sys.stderr)
            clusters = enrichment.attach_nexus_info(clusters, config)

        output_path = args.output or 'deploy-history-report.html'
        report_renderer.render_history(clusters, output_path, start_time, end_time, is_present, team_repos=team_repos)

    elif args.mode == 'asof':
        if not args.as_of:
            parser.error('--as-of YYYY-MM-DD is required when --mode asof')
        as_of_date = parse_date(args.as_of)
        lookback_days = args.lookback_days if args.lookback_days is not None else default_lookback_days
        start_time = as_of_date - datetime.timedelta(days=lookback_days)

        if args.demo:
            history_clusters = demo_data.get_demo_history_clusters(start_time, as_of_date, is_present_scan=False)
        else:
            print(f'Reconstructing state as of {as_of_date.date()} ...', file=sys.stderr)
            history_clusters = collect_history_clusters(config, start_time, as_of_date, is_present_scan=False)
            print('Resolving commits against GitHub...', file=sys.stderr)
            history_clusters = attach_commit_info(history_clusters, config)
            print('Looking up images in Nexus...', file=sys.stderr)
            history_clusters = enrichment.attach_nexus_info(history_clusters, config)

        clusters = snapshot_from_history(history_clusters)
        output_path = args.output or 'deploy-asof-report.html'
        report_renderer.render(clusters, output_path, snapshot_label=f'As of {as_of_date.date()}', team_repos=team_repos)

    print(f'\nWrote report: {output_path}  ({len(clusters)} clusters)')


if __name__ == '__main__':
    main()
