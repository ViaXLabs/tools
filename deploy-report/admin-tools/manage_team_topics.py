#!/usr/bin/env python3
"""
Team Topic Manager (admin tool -- separate from the deploy report generator)
==============================================================================
Applies `team-<name>` topics to GitHub repos based on a static teams.json
registry (the same format the report generator's `team_registry.py` reads
in "static" mode: {"Payments": ["org/repo", ...], ...}).

The point: once your repos carry the right topics, you can flip the main
report tool's config from `team_registry.mode: static` to `mode:
github_topics` and stop maintaining teams.json by hand -- GitHub itself
becomes the source of truth. This script is how you get there (and how you
keep topics in sync if you keep maintaining teams.json as the master
list).

SAFE BY DEFAULT: without --apply, this only prints and reports what would
change. Nothing is written to GitHub until you pass --apply explicitly.

Usage:
    python manage_team_topics.py --teams-file teams.json                       # dry run
    python manage_team_topics.py --teams-file teams.json --apply               # apply for real
    python manage_team_topics.py --teams-file teams.json --apply --report out.json
"""

import argparse
import json
import os
import sys

import requests

API = 'https://api.github.com'
HEADERS_BASE = {'Accept': 'application/vnd.github+json'}


def get_topics(owner, repo, token):
    resp = requests.get(
        f'{API}/repos/{owner}/{repo}/topics',
        headers={**HEADERS_BASE, 'Authorization': f'Bearer {token}'},
        timeout=20,
    )
    if resp.status_code == 404:
        return None  # doesn't exist, was renamed, or the token can't see it
    resp.raise_for_status()
    return resp.json().get('names', [])


def set_topics(owner, repo, token, topics):
    resp = requests.put(
        f'{API}/repos/{owner}/{repo}/topics',
        headers={**HEADERS_BASE, 'Authorization': f'Bearer {token}'},
        json={'names': topics},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json().get('names', [])


def slugify(team_name):
    """GitHub topics must be lowercase alphanumeric + hyphens. Good enough
    for typical team names ("Customer Experience" -> "customer-experience");
    anything with other punctuation, adjust by hand in teams.json or via
    --topic-overrides."""
    return '-'.join(team_name.strip().lower().split())


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--teams-file', default='teams.json', help='Path to the team -> [repo, ...] JSON file')
    parser.add_argument('--team-topic-prefix', default='team-')
    parser.add_argument('--token-env-var', default='GITHUB_TOKEN')
    parser.add_argument('--apply', action='store_true', help='Actually write topics to GitHub (default: dry run)')
    parser.add_argument('--report', default=None, help='Optional path to write a JSON summary of what happened')
    args = parser.parse_args()

    token = os.environ.get(args.token_env_var)
    if not token:
        sys.exit(f'Set ${args.token_env_var} to a GitHub token with repo write access first.')

    with open(args.teams_file) as f:
        teams = json.load(f)

    # A repo could (rarely) be listed under more than one team -- collect
    # every team topic it should end up with.
    desired = {}
    for team_name, repos in teams.items():
        topic = args.team_topic_prefix + slugify(team_name)
        for full_name in repos:
            desired.setdefault(full_name, set()).add(topic)

    print(f'{"DRY RUN -- " if not args.apply else ""}Checking {len(desired)} repo(s) from {args.teams_file}...\n')

    results = []
    for full_name, new_team_topics in sorted(desired.items()):
        owner, sep, repo = full_name.partition('/')
        if not sep:
            print(f'  [error] "{full_name}" -- expected "owner/repo"')
            results.append({'repo': full_name, 'status': 'error', 'detail': 'expected owner/repo format'})
            continue

        current = get_topics(owner, repo, token)
        if current is None:
            print(f'  [not found] {full_name} -- check the name, or that your token can see it')
            results.append({'repo': full_name, 'status': 'not_found'})
            continue

        kept = [t for t in current if not t.startswith(args.team_topic_prefix)]
        final = sorted(set(kept) | new_team_topics)
        added = sorted(new_team_topics - set(current))
        removed = sorted((set(current) - set(kept)) - new_team_topics)

        if not added and not removed:
            print(f'  [unchanged] {full_name}')
            results.append({'repo': full_name, 'status': 'unchanged', 'topics': final})
            continue

        verb = 'applying' if args.apply else 'would apply'
        print(f'  [{verb}] {full_name}: +{added or "none"}  -{removed or "none"}')

        if args.apply:
            try:
                set_topics(owner, repo, token, final)
                results.append({'repo': full_name, 'status': 'applied', 'added': added, 'removed': removed})
            except requests.HTTPError as e:
                print(f'    ERROR: {e}')
                results.append({'repo': full_name, 'status': 'error', 'detail': str(e)})
        else:
            results.append({'repo': full_name, 'status': 'dry_run', 'added': added, 'removed': removed})

    if args.report:
        with open(args.report, 'w') as f:
            json.dump(results, f, indent=2)
        print(f'\nWrote report: {args.report}')

    if not args.apply:
        print('\nDry run only -- nothing was changed on GitHub. Re-run with --apply to write these topics.')


if __name__ == '__main__':
    main()
