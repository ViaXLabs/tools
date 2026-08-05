#!/usr/bin/env python3
"""
Image Introspection / Verification
===================================

Nexus (or any registry) tells you a tag exists — it does NOT guarantee the
image behind that tag actually contains what the tag implies. A rebuild off
a stale cache, a re-tag, or a copy-paste error in a Dockerfile can leave you
with `node-service:20-alpine` that's actually running Node 18 inside. This
script pulls the real manifest + image config from the registry (the same
data `docker inspect` would show you, fetched directly via the Docker
Registry HTTP API — no docker daemon needed) and checks what's REALLY in
there, then flags any disagreement with the tag before it reaches the EOL
report.

How it finds the real version, per product (config/introspection_rules.yaml):
  1. ENV vars baked into the image config — most official upstream base
     images set one (NODE_VERSION, RUBY_VERSION, TOMCAT_VERSION, etc.), and
     it survives into your image if your Dockerfile builds FROM it without
     stripping ENV.
  2. OCI labels (org.opencontainers.image.version), if your CI sets one at
     build time — this is the single best thing you could add to your
     Dockerfiles to make every future check exact rather than best-effort.
  3. For Ubuntu/Alpine base images specifically, neither of the above
     usually exists — the only ground truth is /etc/os-release inside the
     image's filesystem layers. That requires downloading layer data, so
     it's opt-in via --scan-os-release (real bandwidth cost; skipped by
     default and reported as "unverifiable" instead).

Where the registry disagrees with the tag, this script prefers the VERIFIED
value for the downstream EOL check — the tag being wrong is exactly the
failure mode we're guarding against, and a wrong tag is usually optimistic
(closer to EOL than believed), not the other way round.

Usage:
    python image_introspect.py \\
        --in config/images.yaml \\
        --registry-url https://docker.nexus.internal.example.com \\
        --out config/images.verified.yaml \\
        --report verification_report.html \\
        --scan-os-release        # optional, costs bandwidth — see above

    python image_introspect.py --demo   # no network — bundled sample data

Exit codes: 0 = everything matched or was at least not contradicted,
2 = at least one image's tag was contradicted by what's actually inside it.
"""

import argparse
import io
import os
import re
import sys
import tarfile
from datetime import datetime
from pathlib import Path

import yaml

try:
    import requests
except ImportError:
    print("This script needs the 'requests' package: pip install -r requirements.txt",
          file=sys.stderr)
    sys.exit(1)

MANIFEST_ACCEPT = ", ".join([
    "application/vnd.docker.distribution.manifest.v2+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.oci.image.index.v1+json",
])


# --------------------------------------------------------------------------
# Registry access
# --------------------------------------------------------------------------

def build_session(insecure=False):
    session = requests.Session()
    token = os.environ.get("NEXUS_TOKEN") or os.environ.get("REGISTRY_TOKEN")
    username = os.environ.get("NEXUS_USERNAME") or os.environ.get("REGISTRY_USERNAME")
    password = os.environ.get("NEXUS_PASSWORD") or os.environ.get("REGISTRY_PASSWORD")
    if token:
        session.headers.update({"Authorization": f"Bearer {token}"})
    elif username and password:
        session.auth = (username, password)
    session.verify = not insecure
    return session


def fetch_manifest(registry_url, name, ref, session, demo_fixtures):
    if demo_fixtures is not None:
        return demo_fixtures["manifests"].get((name, ref))
    resp = session.get(f"{registry_url.rstrip('/')}/v2/{name}/manifests/{ref}",
                        headers={"Accept": MANIFEST_ACCEPT}, timeout=30)
    if resp.status_code != 200:
        return None
    return resp.json()


def fetch_blob_json(registry_url, name, digest, session, demo_fixtures):
    if not digest:
        return None
    if demo_fixtures is not None:
        b = demo_fixtures["blobs"].get(digest)
        return b if isinstance(b, dict) else None
    resp = session.get(f"{registry_url.rstrip('/')}/v2/{name}/blobs/{digest}", timeout=30)
    if resp.status_code != 200:
        return None
    return resp.json()


def fetch_layer_stream(registry_url, name, digest, session, demo_fixtures):
    if demo_fixtures is not None:
        b = demo_fixtures["blobs"].get(digest)
        return io.BytesIO(b) if isinstance(b, (bytes, bytearray)) else None
    resp = session.get(f"{registry_url.rstrip('/')}/v2/{name}/blobs/{digest}",
                        timeout=120, stream=True)
    if resp.status_code != 200:
        return None
    resp.raw.decode_content = True
    return resp.raw


# --------------------------------------------------------------------------
# Extracting the real version
# --------------------------------------------------------------------------

def extract_from_config(config_json, rule):
    cfg = (config_json or {}).get("config") or {}
    env_map = {}
    for item in cfg.get("Env") or []:
        if "=" in item:
            k, v = item.split("=", 1)
            env_map[k] = v
    labels = cfg.get("Labels") or {}

    for var in rule.get("env_vars", []):
        if env_map.get(var, "").strip():
            return env_map[var].strip(), f"env:{var}"
    for label in rule.get("labels", []):
        if labels.get(label, "").strip():
            return labels[label].strip(), f"label:{label}"
    return None, None


def _extract_os_release_from_layer_stream(fileobj):
    try:
        with tarfile.open(fileobj=fileobj, mode="r|*") as tar:
            for member in tar:
                if member.name.lstrip("./") == "etc/os-release":
                    f = tar.extractfile(member)
                    if f:
                        return f.read().decode("utf-8", errors="replace")
    except tarfile.TarError:
        return None
    return None


def parse_os_release_version(text):
    values = {}
    for line in text.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip().strip('"')
    return values.get("VERSION_ID")


def _numeric_parts(v):
    return re.findall(r"\d+", str(v))


def compare_versions(tag_claimed, verified):
    """Compare at the precision of whichever value is less specific, so a tag
    of '20' matches an image reporting '20.17.0' (both agree on what they
    share), but '20' vs '18.20.4' correctly disagrees."""
    a, b = _numeric_parts(tag_claimed), _numeric_parts(verified)
    n = min(len(a), len(b))
    if n == 0:
        return False
    return a[:n] == b[:n]


# --------------------------------------------------------------------------
# Per-image introspection
# --------------------------------------------------------------------------

def introspect_entry(entry, rules, registry_url, session, demo_fixtures,
                      scan_os_release, platform):
    name = entry["name"]
    product = entry["product"]
    tag_claimed = entry["current_version"]
    tag = entry.get("tag", tag_claimed)
    rule = rules.get(product, {})

    result = dict(entry)
    result["tag_claimed_version"] = tag_claimed
    result["image_verified_version"] = None
    result["verified_source"] = None

    manifest = fetch_manifest(registry_url, name, tag, session, demo_fixtures)
    if manifest is None:
        result["verification"] = "unverifiable"
        result["verification_detail"] = "Could not fetch a manifest for this image/tag from the registry."
        return result

    media_type = manifest.get("mediaType", "")
    if "manifest.list" in media_type or "image.index" in media_type:
        candidates = manifest.get("manifests", [])
        sub = next(
            (m for m in candidates
             if f"{m.get('platform', {}).get('os')}/{m.get('platform', {}).get('architecture')}" == platform),
            candidates[0] if candidates else None,
        )
        if sub is None:
            result["verification"] = "unverifiable"
            result["verification_detail"] = "Manifest list had no usable platform entries."
            return result
        manifest = fetch_manifest(registry_url, name, sub["digest"], session, demo_fixtures)
        if manifest is None:
            result["verification"] = "unverifiable"
            result["verification_detail"] = "Could not fetch the platform-specific manifest."
            return result

    config_digest = (manifest.get("config") or {}).get("digest")
    config_json = fetch_blob_json(registry_url, name, config_digest, session, demo_fixtures)

    verified_version, verified_source = (None, None)
    if config_json:
        verified_version, verified_source = extract_from_config(config_json, rule)

    if verified_version is None and rule.get("os_release") and scan_os_release:
        last_found = None
        for layer in manifest.get("layers", []):
            digest = layer.get("digest")
            if not digest:
                continue
            fileobj = fetch_layer_stream(registry_url, name, digest, session, demo_fixtures)
            if fileobj is None:
                continue
            content = _extract_os_release_from_layer_stream(fileobj)
            if content:
                last_found = content  # later layers win if the file was ever overwritten
        if last_found:
            verified_version = parse_os_release_version(last_found)
            verified_source = "etc/os-release"

    result["image_verified_version"] = verified_version
    result["verified_source"] = verified_source

    if verified_version is None:
        result["verification"] = "unverifiable"
        if rule.get("os_release") and not scan_os_release:
            result["verification_detail"] = (
                "No env var/label carries this product's version — for OS base images that's "
                "normal. Re-run with --scan-os-release to check /etc/os-release directly, or add "
                "a version label at build time to make this exact and cheap to check going forward."
            )
        else:
            result["verification_detail"] = (
                "No matching env var or label found in the image config. Consider adding "
                "`LABEL org.opencontainers.image.version=\"...\"` at build time."
            )
        result["current_version"] = tag_claimed
    elif compare_versions(tag_claimed, verified_version):
        result["verification"] = "match"
        result["verification_detail"] = f"Confirmed via {verified_source}: {verified_version}"
        result["current_version"] = verified_version
    else:
        result["verification"] = "mismatch"
        result["verification_detail"] = (
            f"Registry tag implies {tag_claimed}, but {verified_source} inside the image itself "
            f"reports {verified_version}. Treating the tag as authoritative here would be WRONG — "
            f"investigate this image."
        )
        result["current_version"] = verified_version

    return result


# --------------------------------------------------------------------------
# HTML report
# --------------------------------------------------------------------------

STATUS_ORDER = ["mismatch", "unverifiable", "match"]
STATUS_LABEL = {"mismatch": "Tag mismatch", "unverifiable": "Unverifiable", "match": "Confirmed"}


def render_verification_html(results, generated_at):
    counts = {s: 0 for s in STATUS_ORDER}
    for r in results:
        counts[r["verification"]] += 1

    def row(r):
        badge = r["verification"]
        return f"""
        <tr>
          <td><div class="img-name">{r['name']}</div><div class="img-sub">{r['product']}</div></td>
          <td class="mono">{r.get('tag_claimed_version', '—')}</td>
          <td class="mono">{r.get('image_verified_version') or '—'}</td>
          <td class="mono">{r.get('verified_source') or '—'}</td>
          <td><span class="badge badge-{badge}">{STATUS_LABEL[badge]}</span>
              <div class="note">{r.get('verification_detail', '')}</div></td>
        </tr>"""

    sections = ""
    for status in STATUS_ORDER:
        rows = [r for r in results if r["verification"] == status]
        if not rows:
            continue
        sections += f"""
        <section>
          <h2>{STATUS_LABEL[status]} <span class="count">{len(rows)}</span></h2>
          <table>
            <thead><tr><th>Image</th><th>Tag claims</th><th>Image actually reports</th>
            <th>Verified via</th><th>Status</th></tr></thead>
            <tbody>{''.join(row(r) for r in rows)}</tbody>
          </table>
        </section>"""

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Image Verification Report — {generated_at}</title>
<style>
  :root {{
    --bg:#F6F5F2; --panel:#FFFFFF; --ink:#1B1E23; --ink-soft:#5B6270; --line:#E4E2DC;
    --bad:#B23A32; --bad-bg:#FBEAE8; --warn:#C07E11; --warn-bg:#FBF1DD;
    --good:#2E6B4F; --good-bg:#E8F2EC;
    --mono: ui-monospace, SFMono-Regular, "SF Mono", Consolas, monospace;
    --sans: "Iowan Old Style", "Palatino Linotype", Georgia, serif;
    --ui: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink); font-family:var(--ui); font-size:14px; }}
  header {{ background:var(--ink); color:#F6F5F2; padding:28px 40px; }}
  header h1 {{ font-family:var(--sans); font-size:24px; margin:0 0 4px; }}
  header .sub {{ color:#B9BDC6; font-size:13px; }}
  main {{ padding:8px 40px 60px; max-width:1100px; margin:0 auto; }}
  section {{ margin-top:30px; }}
  section h2 {{ font-family:var(--sans); font-size:16px; margin:0 0 10px; }}
  section h2 .count {{ font-family:var(--mono); font-size:13px; color:var(--ink-soft); font-weight:400; }}
  table {{ width:100%; border-collapse:collapse; background:var(--panel); border:1px solid var(--line); border-radius:10px; }}
  thead th {{ text-align:left; font-size:11px; text-transform:uppercase; letter-spacing:.05em; color:var(--ink-soft); padding:10px 14px; border-bottom:1px solid var(--line); }}
  tbody td {{ padding:12px 14px; border-bottom:1px solid var(--line); vertical-align:top; }}
  tbody tr:last-child td {{ border-bottom:none; }}
  .mono {{ font-family:var(--mono); font-size:12.5px; }}
  .img-name {{ font-weight:600; }}
  .img-sub {{ font-size:12px; color:var(--ink-soft); }}
  .badge {{ display:inline-block; padding:3px 10px; border-radius:999px; font-size:11.5px; font-weight:600; white-space:nowrap; }}
  .badge-mismatch {{ background:var(--bad-bg); color:var(--bad); }}
  .badge-unverifiable {{ background:var(--warn-bg); color:var(--warn); }}
  .badge-match {{ background:var(--good-bg); color:var(--good); }}
  .note {{ font-size:12px; color:var(--ink-soft); margin-top:6px; max-width:420px; }}
</style></head>
<body>
<header><h1>Image Verification Report</h1>
<div class="sub">Generated {generated_at} · checks what's actually inside each image, not just its registry tag</div></header>
<main>{sections}</main>
</body></html>"""


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Verify Docker image tags against real embedded versions.")
    ap.add_argument("--in", dest="in_path", default="config/images.yaml")
    ap.add_argument("--out", default="config/images.verified.yaml")
    ap.add_argument("--report", default="verification_report.html")
    ap.add_argument("--registry-url")
    ap.add_argument("--platform", default="linux/amd64")
    ap.add_argument("--rules", default="config/introspection_rules.yaml")
    ap.add_argument("--scan-os-release", action="store_true",
                     help="Also confirm OS base images via /etc/os-release (downloads layer data)")
    ap.add_argument("--insecure", action="store_true")
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()

    if not args.demo and not args.registry_url:
        print("Error: --registry-url is required unless --demo is set.", file=sys.stderr)
        sys.exit(1)

    config = yaml.safe_load(Path(args.in_path).read_text()) or {}
    rules = (yaml.safe_load(Path(args.rules).read_text()) or {}).get("rules", {})
    session = build_session(args.insecure)

    demo_fixtures = None
    if args.demo:
        from registry_demo_fixtures import MANIFESTS, BLOBS
        demo_fixtures = {"manifests": MANIFESTS, "blobs": BLOBS}

    results = []
    for entry in config.get("images", []):
        try:
            r = introspect_entry(entry, rules, args.registry_url or "https://demo.invalid",
                                  session, demo_fixtures, args.scan_os_release, args.platform)
        except Exception as exc:  # never let one bad image kill the whole run
            r = dict(entry)
            r["tag_claimed_version"] = entry.get("current_version")
            r["image_verified_version"] = None
            r["verified_source"] = None
            r["verification"] = "unverifiable"
            r["verification_detail"] = f"Unexpected error during introspection: {exc}"
            r["current_version"] = entry.get("current_version")
        results.append(r)

    out_images = []
    for r in results:
        e = {
            "name": r["name"], "product": r["product"], "base_os": r.get("base_os", "n/a"),
            "source": r["source"], "current_version": r.get("current_version", r.get("tag_claimed_version")),
        }
        if r.get("github_repo"):
            e["github_repo"] = r["github_repo"]
        if r.get("warn_days"):
            e["warn_days"] = r["warn_days"]
        out_images.append(e)

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    output = {"defaults": config.get("defaults", {"warn_days": 180}), "images": out_images}
    Path(args.out).write_text(
        f"# Auto-generated by image_introspect.py on {generated_at}\n"
        f"# current_version here is the VERIFIED value from inside each image where confirmable —\n"
        f"# not just the registry tag. See {Path(args.report).name} for the full picture per image.\n\n"
        + yaml.dump(output, sort_keys=False, default_flow_style=False)
    )
    Path(args.report).write_text(render_verification_html(results, generated_at))

    mismatches = [r for r in results if r["verification"] == "mismatch"]
    unverifiable = [r for r in results if r["verification"] == "unverifiable"]
    matches = [r for r in results if r["verification"] == "match"]

    print(f"Verified {len(results)} image(s): {len(matches)} confirmed, "
          f"{len(mismatches)} MISMATCH, {len(unverifiable)} unverifiable")
    if mismatches:
        print("\nTag mismatches — the registry tag does NOT reflect what's actually in the image:")
        for r in mismatches:
            print(f"  - {r['name']}: tag says {r['tag_claimed_version']}, "
                  f"image actually reports {r['image_verified_version']}")
    print(f"\nWrote verified config to {args.out}")
    print(f"Wrote verification report to {args.report}")

    sys.exit(2 if mismatches else 0)


if __name__ == "__main__":
    main()
