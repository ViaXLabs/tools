#!/usr/bin/env python3
"""
nexus_list_images.py

Lists every image:tag hosted in a Nexus Docker (hosted/proxy/group)
repository, using the standard Docker Registry HTTP API v2 -- the same
API Harbor, ECR, GHCR, etc. all implement, so this isn't Nexus-specific.

No third-party dependencies -- just the Python standard library, plus
whatever's already on the runner (nothing else needed for this script).

Env vars (required):
  NEXUS_REGISTRY   host[:port] of the registry endpoint, e.g. nexus.mycorp.com:8083
                    (the docker-connector port, not the Nexus web UI port)
  NEXUS_USER        registry username
  NEXUS_PASS        registry password or token
    -> set these as CI secrets. Never hardcode them into this file.

Env vars (optional):
  OUT_FILE   output file, default nexus-images.txt
  PAGE_SIZE  catalog page size, default 100

Output: OUT_FILE with one "repo:tag" per line, e.g.
  team/app-a:1.0.0
  team/app-a:latest
  infra/base-alpine:3.20
"""
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request

LINK_RE = re.compile(r'<([^>]+)>;\s*rel="next"')


def env(name, required=True, default=None):
    val = os.environ.get(name, default)
    if required and not val:
        sys.exit(f"Set {name} (see script header for details)")
    return val


def build_auth_header(user, password):
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return f"Basic {token}"


def get(registry, path, auth_header):
    """GET against the registry. Returns (parsed_json_body, response_headers)."""
    req = urllib.request.Request(
        f"https://{registry}{path}",
        headers={"Authorization": auth_header},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.load(resp)
        return body, resp.headers


def list_repositories(registry, auth_header, page_size):
    repos = []
    path = f"/v2/_catalog?n={page_size}"
    pages = 0
    while path:
        pages += 1
        if pages > 500:
            print("Stopping after 500 pages -- check PAGE_SIZE/pagination.", file=sys.stderr)
            break
        body, headers = get(registry, path, auth_header)
        repos.extend(body.get("repositories") or [])
        link = headers.get("Link", "") or ""
        match = LINK_RE.search(link)
        path = match.group(1) if match else None
    return repos


def list_tags(registry, repo, auth_header):
    try:
        body, _ = get(registry, f"/v2/{repo}/tags/list", auth_header)
        return body.get("tags") or []
    except (urllib.error.HTTPError, urllib.error.URLError) as e:
        print(f"  WARN: tag list failed for {repo}: {e}", file=sys.stderr)
        return []


def main():
    registry = env("NEXUS_REGISTRY")
    user = env("NEXUS_USER")
    password = env("NEXUS_PASS")
    out_file = env("OUT_FILE", required=False, default="nexus-images.txt")
    page_size = int(env("PAGE_SIZE", required=False, default="100"))

    auth_header = build_auth_header(user, password)

    print(f"Fetching repository catalog from {registry} ...")
    try:
        repos = list_repositories(registry, auth_header, page_size)
    except (urllib.error.HTTPError, urllib.error.URLError) as e:
        sys.exit(f"Catalog request failed: {e}")

    print(f"Found {len(repos)} repositories. Fetching tags for each ...")

    count = 0
    total = 0
    with open(out_file, "w") as f:
        for repo in repos:
            tags = list_tags(registry, repo, auth_header)
            if not tags:
                continue
            count += 1
            for tag in tags:
                f.write(f"{repo}:{tag}\n")
                total += 1

    print(f"Wrote {total} image:tag entries across {count} repositories to {out_file}")


if __name__ == "__main__":
    main()
