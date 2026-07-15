"""Resolve a commit SHA pulled from an image tag into real GitHub commit
metadata (message, author, date, canonical URL).

Works with no token at all (60 requests/hour, unauthenticated), but set
the env var named in config (GITHUB_TOKEN by default) to a personal
access token with repo read access to raise that to 5,000/hour --
worth doing once you have more than a handful of services.
"""

import requests

_cache = {}


def resolve(repo_full_name, sha, token=None, timeout=10):
    """Returns a dict with sha/short_sha/url/message/author/date/verified,
    or None if there's no repo or no sha to look up at all.

    On API failure (rate-limited, private repo without a token, network
    error, etc.) this still returns a usable dict -- verified=False --
    with a best-guess commit URL so the report link still works even
    though we couldn't confirm the commit exists or fetch its message.
    """
    if not repo_full_name or not sha:
        return None

    cache_key = (repo_full_name, sha)
    if cache_key in _cache:
        return _cache[cache_key]

    fallback = {
        'sha': sha,
        'short_sha': sha[:7],
        'url': f'https://github.com/{repo_full_name}/commit/{sha}',
        'message': None,
        'author': None,
        'date': None,
        'verified': False,
    }

    headers = {'Accept': 'application/vnd.github+json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'

    try:
        resp = requests.get(
            f'https://api.github.com/repos/{repo_full_name}/commits/{sha}',
            headers=headers, timeout=timeout,
        )
        if resp.status_code == 200:
            data = resp.json()
            result = {
                'sha': data['sha'],
                'short_sha': data['sha'][:7],
                'url': data['html_url'],
                'message': data['commit']['message'].splitlines()[0][:120],
                'author': data['commit']['author']['name'],
                'date': data['commit']['author']['date'],
                'verified': True,
            }
        else:
            result = fallback
    except requests.RequestException:
        result = fallback

    _cache[cache_key] = result
    return result
