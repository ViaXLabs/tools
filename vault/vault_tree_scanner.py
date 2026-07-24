#!/usr/bin/env python3
"""
vault_tree_scanner.py
======================

Walks the KV secret-engine "folder" hierarchy across multiple HashiCorp Vault
clusters and produces a structure report:

    vault -> mount -> path / path / ... -> secret -> [field names]

It never surfaces a secret VALUE anywhere: not on stdout, not in the log
output, not in the HTML/text report. Only path segments, secret names, and
the field (key) names inside each secret are collected.

SECURITY GUARANTEES (read this before changing the read/log code)
-------------------------------------------------------------------
1. The only Vault calls this script makes are LIST and READ. It never issues
   WRITE/DELETE, so it cannot alter vault content.
2. Every time a secret is read (`_read_secret_keys`), the response body is
   reduced to `sorted(data.keys())` in the same function, the original
   dict/response object is explicitly `del`-ed, and only the key list is
   ever returned or stored. No other function in this file ever sees a
   secret value.
3. Third-party HTTP libraries (`requests`, `urllib3`, `hvac`) can emit very
   verbose DEBUG logs that include full request/response bodies. This
   script forces those loggers to WARNING regardless of the verbosity flag
   passed on the CLI, so a well-intentioned `--verbose` in a pipeline step
   can't accidentally dump secret values into CI logs.
4. Vault auth tokens are read only from environment variables (named in the
   config file, never the token itself), never logged, never printed,
   never written to the output report.
5. Nothing in this script's own log statements interpolates a raw Vault
   response. Log statements interpolate only: vault name, mount name, path,
   and `type(exc).__name__` for errors.

Usage
-----
    python vault_tree_scanner.py --config config/vaults.yaml
    python vault_tree_scanner.py --config config/vaults.yaml --vaults prod-eu prod-us
    python vault_tree_scanner.py --demo                       # no network, sample data only

See README.md for the config file format, required Vault policy, and a
Harness pipeline step example.
"""

from __future__ import annotations

import argparse
import html
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

import yaml

try:
    import hvac
    import hvac.exceptions
except ImportError:  # allowed so --demo works without hvac installed
    hvac = None


# --------------------------------------------------------------------------
# Tree node markers
# --------------------------------------------------------------------------
SECRET_MARKER = "__secret__"
FIELDS_KEY = "__fields__"
ERROR_KEY = "__error__"
TRUNCATED_KEY = "__truncated__"


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
@dataclass
class VaultConfig:
    name: str
    address: str
    token_env_var: str
    namespace: Optional[str] = None
    verify_ssl: bool = True
    mounts: List[str] = field(default_factory=list)  # empty => auto-discover


@dataclass
class GlobalConfig:
    html_path: str = "vault_structure.html"
    text_path: str = "vault_structure.txt"
    title: str = "Vault Secret Structure"
    request_timeout: int = 10
    max_list_depth: int = 25
    max_workers: int = 4


def load_config(path: str):
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    out_cfg = raw.get("output", {}) or {}
    defaults = raw.get("defaults", {}) or {}
    gcfg = GlobalConfig(
        html_path=out_cfg.get("html_path", "vault_structure.html"),
        text_path=out_cfg.get("text_path", "vault_structure.txt"),
        title=out_cfg.get("title", "Vault Secret Structure"),
        request_timeout=defaults.get("request_timeout", 10),
        max_list_depth=defaults.get("max_list_depth", 25),
        max_workers=defaults.get("max_workers", 4),
    )

    default_verify = defaults.get("verify_ssl", True)

    vaults = []
    for entry in raw.get("vaults", []):
        vaults.append(
            VaultConfig(
                name=entry["name"],
                address=entry["address"],
                token_env_var=entry["token_env_var"],
                namespace=entry.get("namespace"),
                verify_ssl=entry.get("verify_ssl", default_verify),
                mounts=list(entry.get("mounts") or []),
            )
        )
    if not vaults:
        raise ValueError("config has no entries under 'vaults:'")
    return gcfg, vaults


# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------
def configure_logging(verbose: bool, quiet: bool) -> logging.Logger:
    if quiet:
        level = logging.WARNING
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )

    # Always keep third-party HTTP libraries quiet, no matter what verbosity
    # was requested for this script's own logger. See module docstring #3.
    for noisy in ("urllib3", "requests", "hvac"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    return logging.getLogger("vault_tree_scanner")


# --------------------------------------------------------------------------
# Vault client / discovery
# --------------------------------------------------------------------------
def build_client(vc: VaultConfig, timeout: int, logger: logging.Logger):
    if hvac is None:
        raise RuntimeError("hvac is not installed (pip install -r requirements.txt)")

    token = os.environ.get(vc.token_env_var)
    if not token:
        logger.error(
            "[%s] env var '%s' is not set - skipping this vault (no token value is ever logged)",
            vc.name,
            vc.token_env_var,
        )
        return None

    client = hvac.Client(
        url=vc.address,
        token=token,
        namespace=vc.namespace,
        verify=vc.verify_ssl,
        timeout=timeout,
    )
    token = None  # drop our local reference once the client holds it

    try:
        authed = client.is_authenticated()
    except Exception as exc:
        logger.error(
            "[%s] could not reach %s (%s) - skipping",
            vc.name,
            vc.address,
            type(exc).__name__,
        )
        return None

    if not authed:
        logger.error("[%s] token was rejected by Vault - skipping", vc.name)
        return None

    return client


def detect_kv_version(client, mount: str, vault_name: str, logger: logging.Logger) -> int:
    try:
        client.secrets.kv.v2.read_configuration(mount_point=mount)
        return 2
    except hvac.exceptions.InvalidPath:
        return 1
    except Exception:
        logger.warning(
            "[%s] could not determine KV version for mount '%s', assuming v1",
            vault_name,
            mount,
        )
        return 1


def discover_kv_mounts(client, vc: VaultConfig, logger: logging.Logger) -> Dict[str, int]:
    """Return {mount_path: kv_version}."""
    try:
        engines = client.sys.list_mounted_secrets_engines()["data"]
    except Exception as exc:
        logger.warning(
            "[%s] could not enumerate secrets engines (%s); "
            "falling back to the explicit 'mounts:' list in config",
            vc.name,
            type(exc).__name__,
        )
        engines = None

    mounts: Dict[str, int] = {}

    if engines is not None:
        for raw_path, info in engines.items():
            if info.get("type") != "kv":
                continue
            mount = raw_path.rstrip("/")
            if vc.mounts and mount not in vc.mounts:
                continue
            version = int(info.get("options", {}).get("version", "1") or "1")
            mounts[mount] = version
        return mounts

    # Token couldn't list engines (common with narrowly-scoped policies).
    # Fall back to probing each explicitly-configured mount individually.
    for mount in vc.mounts:
        mounts[mount] = detect_kv_version(client, mount, vc.name, logger)
    return mounts


# --------------------------------------------------------------------------
# Traversal
# --------------------------------------------------------------------------
def _read_secret_keys(client, vault_name: str, mount: str, path: str, kv_version: int, logger: logging.Logger) -> dict:
    """
    Read one secret ONLY to extract its field names.

    The value dict is created, reduced to a key list, and discarded within
    this function. Nothing but `field_names` (a list of strings) ever
    leaves this function - no value, no raw response, ever.
    """
    try:
        if kv_version == 2:
            resp = client.secrets.kv.v2.read_secret_version(path=path, mount_point=mount)
            data = resp["data"]["data"]
        else:
            resp = client.secrets.kv.v1.read_secret(path=path, mount_point=mount)
            data = resp["data"]

        field_names = sorted(data.keys())
        del data, resp  # drop the values as soon as we have the key list
        return {SECRET_MARKER: True, FIELDS_KEY: field_names}
    except Exception as exc:
        logger.warning(
            "[%s] could not read secret %s/%s (%s) - listing structure only",
            vault_name,
            mount,
            path,
            type(exc).__name__,
        )
        return {SECRET_MARKER: True, FIELDS_KEY: None, ERROR_KEY: type(exc).__name__}


def _walk(client, vault_name: str, mount: str, path: str, kv_version: int,
          node: dict, depth: int, max_depth: int, logger: logging.Logger) -> None:
    if depth > max_depth:
        node[TRUNCATED_KEY] = True
        logger.warning(
            "[%s] mount '%s' path '%s' hit max-list-depth=%d, stopping recursion here",
            vault_name, mount, path or "/", max_depth,
        )
        return

    try:
        if kv_version == 2:
            resp = client.secrets.kv.v2.list_secrets(path=path, mount_point=mount)
        else:
            resp = client.secrets.kv.v1.list_secrets(path=path, mount_point=mount)
        entries = resp["data"]["keys"]
    except hvac.exceptions.InvalidPath:
        entries = []  # empty folder, nothing to do
    except Exception as exc:
        node[ERROR_KEY] = type(exc).__name__
        logger.warning(
            "[%s] list failed at %s/%s (%s)",
            vault_name, mount, path or "/", type(exc).__name__,
        )
        return

    for entry in entries:
        full_path = f"{path}{entry}"
        if entry.endswith("/"):
            child: dict = {}
            node[entry] = child
            _walk(client, vault_name, mount, full_path, kv_version, child, depth + 1, max_depth, logger)
        else:
            node[entry] = _read_secret_keys(client, vault_name, mount, full_path, kv_version, logger)


def scan_mount(client, vault_name: str, mount: str, kv_version: int, max_depth: int, logger: logging.Logger) -> dict:
    root: dict = {}
    _walk(client, vault_name, mount, "", kv_version, root, 0, max_depth, logger)
    return root


def scan_one_vault(vc: VaultConfig, gcfg: GlobalConfig, logger: logging.Logger) -> tuple:
    logger.info("[%s] connecting to %s", vc.name, vc.address)
    client = build_client(vc, gcfg.request_timeout, logger)
    if client is None:
        return vc.name, {"status": "auth_failed", "mounts": {}}

    mounts = discover_kv_mounts(client, vc, logger)
    if not mounts:
        logger.warning("[%s] no KV mounts found or accessible", vc.name)
        return vc.name, {"status": "ok", "mounts": {}}

    result_mounts = {}
    for mount, version in sorted(mounts.items()):
        logger.info("[%s] scanning mount '%s' (kv v%d)", vc.name, mount, version)
        result_mounts[mount] = scan_mount(client, vc.name, mount, version, gcfg.max_list_depth, logger)

    return vc.name, {"status": "ok", "mounts": result_mounts}


def scan_all(vault_configs: List[VaultConfig], selected: Optional[List[str]],
             gcfg: GlobalConfig, logger: logging.Logger) -> dict:
    to_run = [vc for vc in vault_configs if not selected or vc.name in selected]
    if selected:
        missing = set(selected) - {vc.name for vc in to_run}
        for name in missing:
            logger.error("requested vault '%s' is not in the config file - skipping", name)

    results = {}
    with ThreadPoolExecutor(max_workers=max(1, gcfg.max_workers)) as pool:
        futures = {pool.submit(scan_one_vault, vc, gcfg, logger): vc.name for vc in to_run}
        for fut in as_completed(futures):
            name, res = fut.result()
            results[name] = res
    # preserve config order in the report rather than completion order
    ordered = {vc.name: results[vc.name] for vc in to_run if vc.name in results}
    return ordered


# --------------------------------------------------------------------------
# Text rendering
# --------------------------------------------------------------------------
def _count_node(node: dict) -> tuple:
    """Returns (folder_count, secret_count, field_count) for a subtree."""
    folders = secrets = fields = 0
    for name, child in node.items():
        if name.startswith("__"):
            continue
        if isinstance(child, dict) and child.get(SECRET_MARKER):
            secrets += 1
            fields += len(child.get(FIELDS_KEY) or [])
        elif isinstance(child, dict):
            folders += 1
            f, s, k = _count_node(child)
            folders += f
            secrets += s
            fields += k
    return folders, secrets, fields


def _render_node_text(node: dict, lines: List[str], prefix: str) -> None:
    entries = sorted((k, v) for k, v in node.items() if not k.startswith("__"))
    if not entries:
        lines.append(f"{prefix}(empty)")
        return
    for i, (name, child) in enumerate(entries):
        last = i == len(entries) - 1
        connector = "└── " if last else "├── "
        if isinstance(child, dict) and child.get(SECRET_MARKER):
            fields = child.get(FIELDS_KEY)
            if fields is None:
                err = child.get(ERROR_KEY, "unknown error")
                lines.append(f"{prefix}{connector}{name}  [read denied: {err}]")
            elif fields:
                lines.append(f"{prefix}{connector}{name}  [keys: {', '.join(fields)}]")
            else:
                lines.append(f"{prefix}{connector}{name}  [no fields]")
        else:
            lines.append(f"{prefix}{connector}{name}")
            extension = "    " if last else "│   "
            _render_node_text(child, lines, prefix + extension)
            if child.get(ERROR_KEY):
                lines.append(f"{prefix}{extension}  ! list error: {child[ERROR_KEY]}")
            if child.get(TRUNCATED_KEY):
                lines.append(f"{prefix}{extension}  ! max depth reached, truncated")


def render_text(results: dict, title: str) -> str:
    lines = [title, "=" * len(title), f"generated: {datetime.now(timezone.utc).isoformat()}", ""]
    for vault_name, vres in results.items():
        if vres["status"] != "ok":
            lines.append(f"VAULT: {vault_name}  [{vres['status']}]")
            lines.append("")
            continue
        f, s, k = 0, 0, 0
        for tree in vres["mounts"].values():
            fc, sc, kc = _count_node(tree)
            f += fc
            s += sc
            k += kc
        lines.append(f"VAULT: {vault_name}  ({len(vres['mounts'])} mounts, {f} folders, {s} secrets, {k} fields)")
        for mount, tree in sorted(vres["mounts"].items()):
            lines.append(f"  {mount}/")
            _render_node_text(tree, lines, prefix="    ")
        lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# HTML rendering
# --------------------------------------------------------------------------
def _render_node_html(node: dict, lines: List[str], prefix: str) -> None:
    entries = sorted((k, v) for k, v in node.items() if not k.startswith("__"))
    if not entries:
        lines.append(f'<div class="row"><span class="dim">{prefix}(empty)</span></div>')
        return
    for i, (name, child) in enumerate(entries):
        last = i == len(entries) - 1
        connector = "└── " if last else "├── "
        safe_name = html.escape(name)
        if isinstance(child, dict) and child.get(SECRET_MARKER):
            fields = child.get(FIELDS_KEY)
            if fields is None:
                err = html.escape(child.get(ERROR_KEY, "unknown error"))
                lines.append(
                    f'<div class="row"><span class="dim">{prefix}{connector}</span>'
                    f'<span class="secret">{safe_name}</span> '
                    f'<span class="err">read denied ({err})</span></div>'
                )
            else:
                if fields:
                    badges = "".join(f'<span class="badge">{html.escape(k)}</span>' for k in fields)
                else:
                    badges = '<span class="badge dim">no fields</span>'
                lines.append(
                    f'<div class="row"><span class="dim">{prefix}{connector}</span>'
                    f'<span class="secret">{safe_name}</span> {badges}</div>'
                )
        else:
            lines.append(
                f'<div class="row"><span class="dim">{prefix}{connector}</span>'
                f'<span class="folder">{safe_name}</span></div>'
            )
            extension = "    " if last else "│   "
            _render_node_html(child, lines, prefix + extension)
            if child.get(ERROR_KEY):
                err = html.escape(child[ERROR_KEY])
                lines.append(f'<div class="row"><span class="dim">{prefix}{extension}</span>'
                              f'<span class="err">list error: {err}</span></div>')
            if child.get(TRUNCATED_KEY):
                lines.append(f'<div class="row"><span class="dim">{prefix}{extension}</span>'
                              f'<span class="err">max depth reached, truncated</span></div>')


HTML_CSS = """
:root {
  --paper: #f5f3ee;
  --card: #ffffff;
  --border: #e3ddd0;
  --ink: #20242c;
  --dim: #a39c8c;
  --vault-bg: #1c2430;
  --vault-fg: #f2ede2;
  --folder: #8a6d2f;
  --secret: #33475b;
  --badge-bg: #eef1f4;
  --badge-fg: #45596e;
  --err: #a63d40;
  --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 32px 16px 64px;
  background: var(--paper);
  color: var(--ink);
  font-family: var(--sans);
}
.wrap { max-width: 920px; margin: 0 auto; }
h1 {
  font-size: 22px;
  font-weight: 650;
  letter-spacing: -0.01em;
  margin: 0 0 4px;
}
.meta {
  color: var(--dim);
  font-size: 13px;
  margin-bottom: 24px;
}
.summary {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
  margin-bottom: 28px;
}
.stat {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 16px;
  min-width: 90px;
}
.stat .n { font-family: var(--mono); font-size: 20px; font-weight: 600; }
.stat .l { font-size: 11px; color: var(--dim); text-transform: uppercase; letter-spacing: 0.04em; }
details.vault {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  margin-bottom: 14px;
  overflow: hidden;
}
details.vault > summary {
  cursor: pointer;
  list-style: none;
  background: var(--vault-bg);
  color: var(--vault-fg);
  padding: 12px 18px;
  font-family: var(--mono);
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: 10px;
}
details.vault > summary::-webkit-details-marker { display: none; }
details.vault > summary::marker { content: ""; }
details.vault > summary .caret { opacity: 0.6; font-size: 11px; }
details.vault > summary .vcount { margin-left: auto; opacity: 0.75; font-size: 12px; }
.mount-block { padding: 14px 18px; border-top: 1px solid var(--border); }
.mount-block:first-of-type { border-top: none; }
.mount-title { font-family: var(--mono); font-weight: 600; color: var(--folder); margin-bottom: 6px; }
.row { font-family: var(--mono); font-size: 13px; line-height: 1.65; white-space: pre; }
.dim { color: var(--dim); }
.folder { color: var(--folder); font-weight: 600; }
.secret { color: var(--secret); font-weight: 600; }
.badge {
  display: inline-block;
  background: var(--badge-bg);
  color: var(--badge-fg);
  border-radius: 4px;
  padding: 1px 6px;
  margin-left: 4px;
  font-size: 11px;
}
.badge.dim { color: var(--dim); background: transparent; border: 1px dashed var(--border); }
.err { color: var(--err); font-weight: 600; }
.status-bad { color: var(--err); font-family: var(--mono); font-size: 13px; padding: 4px 18px 14px; }
.footer { color: var(--dim); font-size: 12px; margin-top: 28px; }
"""


def render_html(results: dict, title: str) -> str:
    generated = datetime.now(timezone.utc).isoformat()

    total_vaults = len(results)
    total_mounts = total_secrets = total_fields = total_folders = 0
    vault_sections = []

    for vault_name, vres in results.items():
        if vres["status"] != "ok":
            vault_sections.append(
                f'<details class="vault"><summary>🔒 {html.escape(vault_name)} '
                f'<span class="vcount">{html.escape(vres["status"])}</span></summary>'
                f'<div class="status-bad">This vault could not be scanned '
                f'({html.escape(vres["status"])}). No structure to show.</div></details>'
            )
            continue

        mount_blocks = []
        v_folders = v_secrets = v_fields = 0
        for mount, tree in sorted(vres["mounts"].items()):
            fc, sc, kc = _count_node(tree)
            v_folders += fc
            v_secrets += sc
            v_fields += kc
            lines: List[str] = []
            _render_node_html(tree, lines, prefix="")
            body = "\n".join(lines) if lines else '<div class="row dim">(empty)</div>'
            mount_blocks.append(
                f'<div class="mount-block"><div class="mount-title">{html.escape(mount)}/</div>{body}</div>'
            )

        total_mounts += len(vres["mounts"])
        total_folders += v_folders
        total_secrets += v_secrets
        total_fields += v_fields

        body_html = "".join(mount_blocks) if mount_blocks else '<div class="status-bad">no KV mounts found</div>'
        vault_sections.append(
            f'<details class="vault" open><summary>🔒 {html.escape(vault_name)} '
            f'<span class="caret">▾</span>'
            f'<span class="vcount">{len(vres["mounts"])} mounts &middot; {v_secrets} secrets &middot; {v_fields} fields</span>'
            f'</summary>{body_html}</details>'
        )

    stats_html = "".join(
        f'<div class="stat"><div class="n">{n}</div><div class="l">{label}</div></div>'
        for n, label in [
            (total_vaults, "vaults"),
            (total_mounts, "mounts"),
            (total_folders, "folders"),
            (total_secrets, "secrets"),
            (total_fields, "fields"),
        ]
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>{HTML_CSS}</style>
</head>
<body>
<div class="wrap">
  <h1>{html.escape(title)}</h1>
  <div class="meta">generated {html.escape(generated)} &middot; structure and field names only, no secret values</div>
  <div class="summary">{stats_html}</div>
  {"".join(vault_sections)}
  <div class="footer">Field names shown next to each secret are the keys inside that KV entry (e.g. "username", "password") - never the values.</div>
</div>
</body>
</html>"""


# --------------------------------------------------------------------------
# Demo data (no network) - lets you preview output styling before wiring
# real vaults / credentials in.
# --------------------------------------------------------------------------
def build_demo_results() -> dict:
    return {
        "prod-eu": {
            "status": "ok",
            "mounts": {
                "secret": {
                    "app1/": {
                        "database": {SECRET_MARKER: True, FIELDS_KEY: ["username", "password", "host", "port"]},
                        "api-keys/": {
                            "stripe": {SECRET_MARKER: True, FIELDS_KEY: ["publishable_key", "secret_key"]},
                            "sendgrid": {SECRET_MARKER: True, FIELDS_KEY: ["api_key"]},
                        },
                    },
                    "app2/": {
                        "database": {SECRET_MARKER: True, FIELDS_KEY: ["username", "password"]},
                        "legacy-cert": {SECRET_MARKER: True, FIELDS_KEY: None, ERROR_KEY: "Forbidden"},
                    },
                },
                "app-configs": {
                    "shared/": {
                        "feature-flags": {SECRET_MARKER: True, FIELDS_KEY: ["new_checkout", "dark_mode"]},
                    }
                },
            },
        },
        "prod-us": {
            "status": "ok",
            "mounts": {
                "secret": {
                    "billing/": {
                        "stripe-webhook": {SECRET_MARKER: True, FIELDS_KEY: ["signing_secret"]},
                    },
                },
            },
        },
        "staging": {"status": "auth_failed", "mounts": {}},
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="Report Vault KV folder/secret/field structure, values never included.")
    parser.add_argument("--config", default="config/vaults.yaml", help="path to vaults.yaml")
    parser.add_argument("--vaults", nargs="+", default=None, help="subset of vault names from the config to scan (default: all)")
    parser.add_argument("--out-html", default=None, help="override output HTML path")
    parser.add_argument("--out-text", default=None, help="override output text path")
    parser.add_argument("--max-depth", type=int, default=None, help="override max recursion depth")
    parser.add_argument("--strict", action="store_true", help="exit non-zero if any vault failed to auth/scan")
    parser.add_argument("--quiet", action="store_true", help="only show warnings/errors")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging for this script (3rd-party HTTP libs stay quiet regardless)")
    parser.add_argument("--demo", action="store_true", help="skip Vault entirely and render sample data, for previewing report styling")
    args = parser.parse_args()

    logger = configure_logging(args.verbose, args.quiet)

    if args.demo:
        results = build_demo_results()
        gcfg = GlobalConfig()
    else:
        try:
            gcfg, vault_configs = load_config(args.config)
        except Exception as exc:
            logger.error("failed to load config '%s': %s", args.config, exc)
            return 2
        if args.max_depth is not None:
            gcfg.max_list_depth = args.max_depth
        results = scan_all(vault_configs, args.vaults, gcfg, logger)

    html_path = args.out_html or gcfg.html_path
    text_path = args.out_text or gcfg.text_path

    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(render_html(results, gcfg.title))
    with open(text_path, "w", encoding="utf-8") as fh:
        fh.write(render_text(results, gcfg.title))

    logger.info("wrote %s and %s", html_path, text_path)

    failed = [name for name, r in results.items() if r["status"] != "ok"]
    if failed:
        logger.warning("vaults not fully scanned: %s", ", ".join(failed))
        if args.strict:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
