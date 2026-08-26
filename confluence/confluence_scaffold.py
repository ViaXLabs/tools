#!/usr/bin/env python3
"""
confluence_scaffold.py

Creates a standardized ("greenfield") Confluence Data Center/Server space
from a manifest + page templates, in one command. Variables you define in
the manifest (team name, point of contact, repo URL, environment names,
whatever your program needs) are collected once at the start -- via
--var flags, a --vars-file, or interactive prompts for anything not
already supplied -- and are substituted into every page's title and body
before it's created. That's the "customization at inception" piece: one
run, a few answers, a fully populated space that isn't just an empty
skeleton.

Requires: confluence_export.py in the same directory (reuses its HTTP
session / pagination helpers) and `pip install requests`.

--------------------------------------------------------------------------
PREVIEW WHAT WOULD BE CREATED (no network calls, no auth needed)
    python confluence_scaffold.py --manifest greenfield_example/manifest.json \
        --base-url https://confluence.example.gov --dry-run \
        --var space_key=TEAMC --var team_name="Team C" \
        --var poc_name="Jane Doe" --var poc_email=jane.doe@agency.gov

ACTUALLY CREATE IT (prompts for any variable not passed via --var/--vars-file)
    python confluence_scaffold.py --manifest greenfield_example/manifest.json \
        --base-url https://confluence.example.gov --token $CONFLUENCE_PAT

RE-RUN SAFELY
    Re-running against a space that already has some of these pages skips
    ones that already exist (matched by title) rather than duplicating
    them -- so you can re-run after fixing a template without cleanup.
--------------------------------------------------------------------------

MANIFEST FORMAT (see greenfield_example/manifest.json for a full example)
    {
      "space": {"key": "{{space_key}}", "name": "{{team_name}} team space", "description": "..."},
      "variables": {
        "space_key": {"prompt": "Space key", "required": true},
        "team_name": {"prompt": "Team name", "required": true},
        "repo_url":  {"prompt": "Source repo URL", "required": false, "default": "TBD"}
      },
      "pages": [
        {"title": "{{team_name}} home", "template": "templates/home.html", "children": [
          {"title": "Onboarding", "template": "templates/onboarding.html", "children": [...]},
          {"title": "Runbooks", "template": "templates/runbooks.html", "children": [
            {"title": "Deploy", "template": "templates/runbook_deploy.html"}
          ]}
        ]}
      ]
    }

    Templates are files (relative to the manifest's own directory)
    containing Confluence storage-format markup with {{variable}}
    placeholders. A page can use "body": "..." inline instead of
    "template" for very short content.

PERMISSIONS
    Creating a space normally requires Confluence Administrator (site
    admin) rights. In most orgs -- especially federal programs -- that
    argues for running this from a service account behind a request/
    approval step, not handing it out as a fully open self-service button.
"""

import argparse
import json
import os
import re
import sys

from confluence_export import get_session, paginated_get  # noqa: reuse auth/pagination

PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def render(text, variables):
    return PLACEHOLDER_RE.sub(lambda m: str(variables.get(m.group(1), m.group(0))), text or "")


def find_unrendered(text):
    return PLACEHOLDER_RE.findall(text or "")


def collect_variables(manifest_vars, cli_vars, vars_file, non_interactive):
    values = {}
    if vars_file:
        with open(vars_file, "r", encoding="utf-8") as f:
            values.update(json.load(f))
    values.update(cli_vars)  # CLI flags win over the vars file

    for name, spec in (manifest_vars or {}).items():
        if values.get(name):
            continue
        default = spec.get("default")
        required = spec.get("required", False)
        prompt_text = spec.get("prompt", name)

        if non_interactive:
            if default is not None:
                values[name] = default
            elif required:
                raise SystemExit(
                    f"Missing required variable '{name}' "
                    f"(pass --var {name}=... or put it in --vars-file)"
                )
            else:
                values[name] = ""
        else:
            suffix = f" [{default}]" if default is not None else ""
            entered = input(f"{prompt_text}{suffix}: ").strip()
            while required and not entered and not default:
                entered = input(f"  (required) {prompt_text}{suffix}: ").strip()
            values[name] = entered or (default or "")
    return values


def resolve_template_paths(nodes, manifest_dir):
    for node in nodes:
        if "template" in node:
            node["_template_path"] = os.path.join(manifest_dir, node["template"])
        resolve_template_paths(node.get("children", []), manifest_dir)


def render_page_node(node, variables):
    title = render(node["title"], variables)
    if "_template_path" in node:
        with open(node["_template_path"], "r", encoding="utf-8") as f:
            body = render(f.read(), variables)
    else:
        body = render(node.get("body", ""), variables)
    return title, body


def find_existing_page(session, root, space_key, title):
    params = {"spaceKey": space_key, "title": title, "type": "page", "status": "current"}
    results = list(paginated_get(session, root, "/rest/api/content", params))
    return results[0] if results else None


def create_page(session, root, space_key, title, body, parent_id=None):
    payload = {
        "type": "page",
        "title": title,
        "space": {"key": space_key},
        "status": "current",
        "body": {"storage": {"value": body, "representation": "storage"}},
    }
    if parent_id:
        payload["ancestors"] = [{"id": parent_id}]
    resp = session.post(root + "/rest/api/content", json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def ensure_space(session, root, space_key, space_name, space_description):
    resp = session.get(root + f"/rest/api/space/{space_key}", timeout=30)
    if resp.status_code == 200:
        return resp.json(), False
    if resp.status_code != 404:
        resp.raise_for_status()
    payload = {
        "key": space_key,
        "name": space_name,
        "description": {"plain": {"value": space_description or "", "representation": "plain"}},
    }
    resp = session.post(root + "/rest/api/space", json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json(), True


def walk_and_create(session, root, space_key, nodes, variables, parent_id, dry_run, indent=0):
    for node in nodes:
        title, body = render_page_node(node, variables)

        leftovers = sorted(set(find_unrendered(title)) | set(find_unrendered(body)))
        if leftovers:
            print(f"{'  ' * indent}! unresolved placeholder(s) in '{title}': {leftovers}", file=sys.stderr)

        if dry_run:
            tmpl = f"  (template: {node['template']})" if "template" in node else ""
            print(f"{'  ' * indent}would create: {title}{tmpl}")
            walk_and_create(session, root, space_key, node.get("children", []), variables,
                             parent_id=f"dryrun:{title}", dry_run=True, indent=indent + 1)
            continue

        existing = find_existing_page(session, root, space_key, title)
        if existing:
            print(f"{'  ' * indent}skip (already exists): {title}")
            page_id = existing["id"]
        else:
            created = create_page(session, root, space_key, title, body, parent_id)
            page_id = created["id"]
            print(f"{'  ' * indent}created: {title}  (id={page_id})")

        walk_and_create(session, root, space_key, node.get("children", []), variables,
                         parent_id=page_id, dry_run=False, indent=indent + 1)


def main():
    parser = argparse.ArgumentParser(
        description="Create a standardized Confluence space from a manifest, with variables filled in at creation time."
    )
    parser.add_argument("--base-url", required=True, help="e.g. https://confluence.example.gov")
    parser.add_argument("--manifest", required=True, help="Path to manifest JSON")
    parser.add_argument("--var", action="append", default=[], dest="cli_vars_raw",
                         help="key=value, repeatable: --var team_name='Team C' --var space_key=TEAMC")
    parser.add_argument("--vars-file", help="JSON file of variable values, e.g. {\"team_name\": \"Team C\"}")
    parser.add_argument("--non-interactive", action="store_true",
                         help="Never prompt; use defaults and fail on missing required variables")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan; make no API calls")
    parser.add_argument("--token", default=os.environ.get("CONFLUENCE_PAT"), help="Personal access token")
    parser.add_argument("--username", default=os.environ.get("CONFLUENCE_USER"))
    parser.add_argument("--password", default=os.environ.get("CONFLUENCE_PASSWORD"))
    parser.add_argument("--no-verify-ssl", dest="verify_ssl", action="store_false", default=True)
    args = parser.parse_args()

    cli_vars = {}
    for raw in args.cli_vars_raw:
        if "=" not in raw:
            parser.error(f"--var must be key=value, got: {raw}")
        k, v = raw.split("=", 1)
        cli_vars[k] = v

    manifest_path = os.path.abspath(args.manifest)
    manifest_dir = os.path.dirname(manifest_path)
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    resolve_template_paths(manifest.get("pages", []), manifest_dir)
    variables = collect_variables(manifest.get("variables", {}), cli_vars, args.vars_file, args.non_interactive)

    space_key = render(manifest["space"]["key"], variables)
    space_name = render(manifest["space"].get("name", space_key), variables)
    space_description = render(manifest["space"].get("description", ""), variables)
    root = args.base_url.rstrip("/")

    if args.dry_run:
        print(f"[dry run] space: {space_key}  \"{space_name}\"\n")
        walk_and_create(None, root, space_key, manifest.get("pages", []), variables,
                         parent_id=None, dry_run=True)
        return

    session = get_session(token=args.token, username=args.username, password=args.password,
                           verify_ssl=args.verify_ssl)

    space, was_created = ensure_space(session, root, space_key, space_name, space_description)
    print(("created" if was_created else "using existing") + f" space: {space_key}  \"{space_name}\"\n")

    walk_and_create(session, root, space_key, manifest.get("pages", []), variables,
                     parent_id=None, dry_run=False)
    print("\nDone.")


if __name__ == "__main__":
    main()
