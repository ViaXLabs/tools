#!/usr/bin/env python3
"""
apply_golden_repo.py

Creates (or configures) a GitHub repo to match a "golden" standard, in one of two modes:

  --mode config       Read desired settings from a JSON file (see golden-repo-config.example.json)
  --mode mirror       Introspect a live reference repo's settings and copy them onto the target

In both modes, if the target repo doesn't exist yet, it's created via GitHub's
"generate from template" API using --template-repo (defaults to --source-repo in mirror mode).

Requires a GITHUB_TOKEN env var with repo admin + org read scopes.

Examples:

  # Config-driven, brand new repo
  python apply_golden_repo.py \\
      --owner my-org \\
      --new-repo-name payments-service \\
      --team platform-team \\
      --mode config --config golden-repo-config.json \\
      --template-repo my-org/golden-repo-template

  # Mirror an existing reference repo's live settings exactly
  python apply_golden_repo.py \\
      --owner my-org \\
      --new-repo-name payments-service \\
      --team platform-team \\
      --mode mirror --source-repo my-org/golden-repo-template
"""

import argparse
import json
import os
import sys
import time
import requests

GITHUB_API = "https://api.github.com"


def gh_token():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("ERROR: GITHUB_TOKEN environment variable is required.")
    return token


def gh_request(method, path, token, json_body=None, ok_statuses=(200, 201, 204)):
    url = path if path.startswith("http") else f"{GITHUB_API}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    resp = requests.request(method, url, headers=headers, json=json_body, timeout=30)
    if resp.status_code not in ok_statuses:
        print(f"[WARN] {method} {url} -> {resp.status_code}: {resp.text}", file=sys.stderr)
    return resp


# ---------------------------------------------------------------------------
# Repo creation
# ---------------------------------------------------------------------------

def repo_exists(owner, repo, token):
    resp = gh_request("GET", f"/repos/{owner}/{repo}", token, ok_statuses=(200, 404))
    return resp.status_code == 200


def create_from_template(template_owner, template_repo, owner, new_name, private, token):
    print(f"Creating {owner}/{new_name} from template {template_owner}/{template_repo} ...")
    body = {
        "owner": owner,
        "name": new_name,
        "private": private,
        "include_all_branches": False,
    }
    resp = gh_request(
        "POST",
        f"/repos/{template_owner}/{template_repo}/generate",
        token,
        json_body=body,
    )
    if resp.status_code != 201:
        sys.exit(f"Failed to create repo from template: {resp.status_code} {resp.text}")

    # Newly generated repos take a moment to become fully addressable.
    for _ in range(10):
        if repo_exists(owner, new_name, token):
            return
        time.sleep(2)
    sys.exit("Repo was created but never became available via the API. Check GitHub status.")


# ---------------------------------------------------------------------------
# Settings: gather (mirror mode) and apply (both modes)
# ---------------------------------------------------------------------------

def gather_settings_from_source(source_owner, source_repo, token):
    """Introspect a live repo and build the same settings dict shape as the config file."""
    repo_data = gh_request("GET", f"/repos/{source_owner}/{source_repo}", token).json()

    default_branch = repo_data.get("default_branch", "main")

    protection = {}
    prot_resp = gh_request(
        "GET",
        f"/repos/{source_owner}/{source_repo}/branches/{default_branch}/protection",
        token,
        ok_statuses=(200, 404),
    )
    if prot_resp.status_code == 200:
        p = prot_resp.json()
        reviews = p.get("required_pull_request_reviews", {}) or {}
        checks = p.get("required_status_checks", {}) or {}
        protection = {
            "branch": default_branch,
            "required_approving_review_count": reviews.get("required_approving_review_count", 1),
            "require_code_owner_reviews": reviews.get("require_code_owner_reviews", False),
            "enforce_admins": (p.get("enforce_admins") or {}).get("enabled", False),
            "required_linear_history": (p.get("required_linear_history") or {}).get("enabled", False),
            "allow_force_pushes": (p.get("allow_force_pushes") or {}).get("enabled", False),
            "allow_deletions": (p.get("allow_deletions") or {}).get("enabled", False),
            "required_status_checks": {
                "strict": checks.get("strict", False),
                "contexts": checks.get("contexts", []),
            },
        }

    topics_resp = gh_request("GET", f"/repos/{source_owner}/{source_repo}/topics", token)
    topics = topics_resp.json().get("names", []) if topics_resp.status_code == 200 else []

    labels_resp = gh_request("GET", f"/repos/{source_owner}/{source_repo}/labels?per_page=100", token)
    labels = []
    if labels_resp.status_code == 200:
        for lbl in labels_resp.json():
            labels.append({
                "name": lbl["name"],
                "color": lbl["color"],
                "description": lbl.get("description") or "",
            })

    teams_resp = gh_request("GET", f"/repos/{source_owner}/{source_repo}/teams?per_page=100", token)
    team_overrides = {}
    if teams_resp.status_code == 200:
        for t in teams_resp.json():
            team_overrides[t["slug"]] = t.get("permission", "pull")

    hooks_resp = gh_request("GET", f"/repos/{source_owner}/{source_repo}/hooks", token)
    webhooks = []
    if hooks_resp.status_code == 200:
        for h in hooks_resp.json():
            webhooks.append({
                "url": h.get("config", {}).get("url", ""),
                "content_type": h.get("config", {}).get("content_type", "json"),
                "events": h.get("events", []),
                "active": h.get("active", True),
            })

    return {
        "repo_settings": {
            "has_wiki": repo_data.get("has_wiki", False),
            "has_issues": repo_data.get("has_issues", True),
            "has_projects": repo_data.get("has_projects", False),
            "has_downloads": repo_data.get("has_downloads", True),
            "allow_squash_merge": repo_data.get("allow_squash_merge", True),
            "allow_merge_commit": repo_data.get("allow_merge_commit", False),
            "allow_rebase_merge": repo_data.get("allow_rebase_merge", False),
            "delete_branch_on_merge": repo_data.get("delete_branch_on_merge", True),
            "allow_auto_merge": repo_data.get("allow_auto_merge", False),
            "visibility": repo_data.get("visibility", "private"),
            "default_branch": default_branch,
        },
        "branch_protection": protection,
        "topics": topics,
        "labels": labels,
        "team_permissions": {"default": "push", "overrides": team_overrides},
        "webhooks": webhooks,
    }


def apply_repo_settings(owner, repo, settings, token):
    print("Applying repo-level settings ...")
    gh_request("PATCH", f"/repos/{owner}/{repo}", token, json_body=settings)


def apply_branch_protection(owner, repo, protection, token):
    if not protection:
        return
    branch = protection.get("branch", "main")
    print(f"Applying branch protection on '{branch}' ...")
    body = {
        "required_status_checks": protection.get("required_status_checks") or None,
        "enforce_admins": protection.get("enforce_admins", False),
        "required_pull_request_reviews": {
            "required_approving_review_count": protection.get("required_approving_review_count", 1),
            "require_code_owner_reviews": protection.get("require_code_owner_reviews", False),
        },
        "restrictions": None,
        "required_linear_history": protection.get("required_linear_history", False),
        "allow_force_pushes": protection.get("allow_force_pushes", False),
        "allow_deletions": protection.get("allow_deletions", False),
    }
    gh_request("PUT", f"/repos/{owner}/{repo}/branches/{branch}/protection", token, json_body=body)


def apply_topics(owner, repo, topics, token):
    if not topics:
        return
    print(f"Applying topics: {topics}")
    gh_request("PUT", f"/repos/{owner}/{repo}/topics", token, json_body={"names": topics})


def apply_labels(owner, repo, labels, token):
    if not labels:
        return
    print(f"Applying {len(labels)} label(s) ...")
    for lbl in labels:
        resp = gh_request(
            "POST", f"/repos/{owner}/{repo}/labels", token,
            json_body={"name": lbl["name"], "color": lbl["color"], "description": lbl.get("description", "")},
            ok_statuses=(200, 201, 422),  # 422 = already exists
        )
        if resp.status_code == 422:
            gh_request(
                "PATCH", f"/repos/{owner}/{repo}/labels/{lbl['name']}", token,
                json_body={"color": lbl["color"], "description": lbl.get("description", "")},
            )


def apply_team_permissions(owner, repo, team_permissions, requesting_team, token):
    if not team_permissions:
        return
    overrides = team_permissions.get("overrides", {})
    default_perm = team_permissions.get("default", "push")

    # Always give the requesting team access, using an override if one exists for them.
    perm_for_requester = overrides.get(requesting_team, default_perm)
    print(f"Granting team '{requesting_team}' permission '{perm_for_requester}' ...")
    gh_request(
        "PUT", f"/orgs/{owner}/teams/{requesting_team}/repos/{owner}/{repo}", token,
        json_body={"permission": perm_for_requester},
    )

    # Apply any other explicitly-listed team overrides too (e.g. security-team: pull for all repos)
    for team_slug, perm in overrides.items():
        if team_slug == requesting_team:
            continue
        print(f"Granting team '{team_slug}' permission '{perm}' ...")
        gh_request(
            "PUT", f"/orgs/{owner}/teams/{team_slug}/repos/{owner}/{repo}", token,
            json_body={"permission": perm},
        )


def apply_webhooks(owner, repo, webhooks, token):
    if not webhooks:
        return
    print(f"Applying {len(webhooks)} webhook(s) ...")
    for hook in webhooks:
        gh_request(
            "POST", f"/repos/{owner}/{repo}/hooks", token,
            json_body={
                "name": "web",
                "active": hook.get("active", True),
                "events": hook.get("events", ["push"]),
                "config": {
                    "url": hook["url"],
                    "content_type": hook.get("content_type", "json"),
                },
            },
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Create/configure a repo to match golden standards.")
    parser.add_argument("--owner", required=True, help="Org/owner the new repo lives under")
    parser.add_argument("--new-repo-name", required=True)
    parser.add_argument("--team", required=True, help="Requesting team's GitHub team slug")
    parser.add_argument("--mode", choices=["config", "mirror"], required=True)
    parser.add_argument("--config", help="Path to JSON config file (required for --mode config)")
    parser.add_argument("--source-repo", help="owner/repo to mirror settings from (required for --mode mirror)")
    parser.add_argument("--template-repo", help="owner/repo to use for 'generate from template' (defaults to --source-repo)")
    parser.add_argument("--skip-create", action="store_true", help="Repo already exists; only apply settings")
    args = parser.parse_args()

    token = gh_token()

    if args.mode == "config":
        if not args.config:
            sys.exit("--config is required in --mode config")
        with open(args.config) as f:
            settings = json.load(f)
        template_repo = args.template_repo
    else:
        if not args.source_repo:
            sys.exit("--source-repo is required in --mode mirror")
        source_owner, source_repo = args.source_repo.split("/")
        settings = gather_settings_from_source(source_owner, source_repo, token)
        template_repo = args.template_repo or args.source_repo

    if not args.skip_create and not repo_exists(args.owner, args.new_repo_name, token):
        if not template_repo:
            sys.exit("Repo doesn't exist and no --template-repo (or --source-repo) given to generate it from.")
        t_owner, t_repo = template_repo.split("/")
        private = settings.get("repo_settings", {}).get("visibility", "private") != "public"
        create_from_template(t_owner, t_repo, args.owner, args.new_repo_name, private, token)
    else:
        print(f"{args.owner}/{args.new_repo_name} already exists, skipping creation.")

    apply_repo_settings(args.owner, args.new_repo_name, settings.get("repo_settings", {}), token)
    apply_branch_protection(args.owner, args.new_repo_name, settings.get("branch_protection", {}), token)
    apply_topics(args.owner, args.new_repo_name, settings.get("topics", []), token)
    apply_labels(args.owner, args.new_repo_name, settings.get("labels", []), token)
    apply_team_permissions(args.owner, args.new_repo_name, settings.get("team_permissions", {}), args.team, token)
    apply_webhooks(args.owner, args.new_repo_name, settings.get("webhooks", []), token)

    print(f"\nDone. {args.owner}/{args.new_repo_name} is configured per {'config file' if args.mode == 'config' else 'source repo ' + args.source_repo}.")


if __name__ == "__main__":
    main()
