#!/usr/bin/env python3
"""
nexus_image_size_no_touch.py

Reports image:tag size info from a Nexus Docker repository WITHOUT
resetting Nexus's "last downloaded" clock -- the thing your cleanup
policy checks to decide whether an image is still "in use."

WHY THIS MATTERS
-----------------
Nexus updates an asset's "last downloaded" timestamp on any successful
(200/304) response from the actual registry content endpoints:
  GET /v2/<repo>/<image>/manifests/<tag>
  GET /v2/<repo>/<image>/blobs/<digest>
That's true whether the request comes from `docker pull`, `docker
manifest inspect`, `skopeo`, `syft` scanning a registry image, or a
plain `curl` -- and it's true for HEAD requests too, since Nexus's own
docs describe the trigger as "200 and 304 responses," not tied to any
one HTTP verb or client. So *any* tool that reads an image this way
looks identical to real usage, and quietly keeps that image from ever
rolling off.

Nexus's own metadata database is a separate code path that never goes
near that content-serving handler:
  GET /service/rest/v1/search/assets?repository=<repo>&format=docker
This returns lastModified, blobCreated, lastDownloaded, and the sha256
digest straight from Nexus's index -- zero download, zero effect on
"last downloaded." The only thing it *doesn't* give you is real image
size: the fileSize field on a manifest asset is the size of the small
manifest JSON itself (a few KB), not the compressed image.

THE APPROACH
------------
1. Pull all the safe metadata (dates, digest) from /search/assets --
   never touches the download clock, ever.
2. For real size: cache it by digest in a local JSON file. A digest's
   content never changes, so its size never changes -- meaning you
   only ever need to ask the registry once per unique image, the
   very first time you see that digest. Every run after that reads
   the cache, so images you've already sized are never touched again
   no matter how many times you re-run the report.
3. Only genuinely NEW digests (freshly pushed images) cost you one
   small GET of the manifest JSON (a few KB -- not a full pull, no
   layer bytes) to sum up config.size + each layer's size, which the
   manifest already lists. That one GET does bump "last downloaded"
   for that specific new image, once -- an acceptable, one-time cost,
   since you have to learn its size somehow. Old crusty images you've
   already recorded are never touched again.

CAVEATS WORTH KNOWING
----------------------
- Multi-arch tags: a GET on the tag manifest may return a manifest
  LIST (one descriptor per platform) rather than a single image
  manifest. This script detects that and follows into one platform's
  manifest (arch preference below) to get a representative size --
  which costs one more one-time GET, also cached by that sub-digest.
  If you need an exact combined size across every platform, sum all
  of them; each is still cached forever after its first fetch.
- This only solves the SIZE part of your report. If you're also
  running an SBOM/vulnerability scan straight against the registry
  (e.g. syft against `registry:host/image:tag`), that genuinely needs
  to unpack every layer's file contents, so there's no metadata-only
  substitute for it -- it will always look like real usage to Nexus.
  Worth deciding separately whether that scan needs to run against
  every image every time, or only on new pushes.

Env vars (required): NEXUS_REGISTRY, NEXUS_USER, NEXUS_PASS
Env vars (optional):  OUT_FILE (default nexus-image-sizes.csv)
                      CACHE_FILE (default nexus-size-cache.json)
                      PAGE_SIZE (default 100)
                      PREFERRED_ARCH (default linux/amd64)
"""
import base64
import csv
import json
import os
import re
import sys
import urllib.error
import urllib.request

LINK_RE = re.compile(r'<([^>]+)>;\s*rel="next"')

MANIFEST_ACCEPT = ", ".join([
    "application/vnd.docker.distribution.manifest.v2+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.oci.image.index.v1+json",
])


def env(name, required=True, default=None):
    val = os.environ.get(name, default)
    if required and not val:
        sys.exit(f"Set {name} (see script header for details)")
    return val


def auth_header(user, password):
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return f"Basic {token}"


def api_get(url, headers):
    """Plain metadata/content GET returning (json_body, response_headers)."""
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp), resp.headers


# ---------------------------------------------------------------------
# STEP 1: metadata only -- never touches "last downloaded"
# ---------------------------------------------------------------------
def list_manifest_assets(registry, repo, auth, page_size):
    """
    Every manifest asset in `repo`, via the Search/Assets metadata API.
    This is a pure DB query -- it never hits the registry's content
    endpoints, so it has no effect on Nexus's download tracking.
    """
    headers = {"Authorization": auth}
    path = f"/service/rest/v1/search/assets?repository={repo}&format=docker&maxItems={page_size}"
    assets = []
    while path:
        body, resp_headers = api_get(f"https://{registry}{path}", headers)
        for item in body.get("items", []):
            # Keep only manifest entries; skip blob/layer assets so we
            # get one row per tag, not one per layer.
            if "/manifests/" in item.get("path", ""):
                assets.append(item)
        token = body.get("continuationToken")
        if not token:
            path = None
        else:
            sep = "&" if "?" in path else "?"
            base_path = path.split("&continuationToken=")[0]
            path = f"{base_path}&continuationToken={token}"
    return assets


# ---------------------------------------------------------------------
# STEP 2: real size, cached forever per digest
# ---------------------------------------------------------------------
def load_cache(cache_file):
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            return json.load(f)
    return {}


def save_cache(cache_file, cache):
    tmp = cache_file + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cache, f, indent=2, sort_keys=True)
    os.replace(tmp, cache_file)


def fetch_manifest_size_bytes(registry, repo, image_name, ref, auth, preferred_arch):
    """
    ONE small GET of manifest JSON (a few KB) -- not a full pull, no
    layer bytes transferred. Sums config.size + each layer's size,
    which the manifest already lists. This DOES count as a real
    registry hit and will bump "last downloaded" for `ref` -- but it
    is only ever called for a digest the cache hasn't seen before.
    """
    headers = {"Authorization": auth, "Accept": MANIFEST_ACCEPT}
    url = f"https://{registry}/v2/{repo}/{image_name}/manifests/{ref}"
    body, _ = api_get(url, headers)

    media_type = body.get("mediaType", "")
    if "manifest.list" in media_type or "image.index" in media_type:
        # Multi-arch: follow into one platform's manifest by digest.
        manifests = body.get("manifests", [])
        want_os, want_arch = preferred_arch.split("/")
        chosen = next(
            (m for m in manifests
             if m.get("platform", {}).get("os") == want_os
             and m.get("platform", {}).get("architecture") == want_arch),
            manifests[0] if manifests else None,
        )
        if chosen is None:
            return 0
        return fetch_manifest_size_bytes(
            registry, repo, image_name, chosen["digest"], auth, preferred_arch
        )

    config_size = body.get("config", {}).get("size", 0)
    layers_size = sum(layer.get("size", 0) for layer in body.get("layers", []))
    return config_size + layers_size


def main():
    registry = env("NEXUS_REGISTRY")
    user = env("NEXUS_USER")
    password = env("NEXUS_PASS")
    out_file = env("OUT_FILE", required=False, default="nexus-image-sizes.csv")
    cache_file = env("CACHE_FILE", required=False, default="nexus-size-cache.json")
    page_size = int(env("PAGE_SIZE", required=False, default="100"))
    preferred_arch = env("PREFERRED_ARCH", required=False, default="linux/amd64")
    repo = env("NEXUS_DOCKER_REPO", required=False, default=None)

    if not repo:
        sys.exit("Set NEXUS_DOCKER_REPO to the hosted docker repository name")

    auth = auth_header(user, password)
    cache = load_cache(cache_file)

    print(f"Fetching manifest metadata for {repo} ... (metadata-only, no download impact)")
    assets = list_manifest_assets(registry, repo, auth, page_size)
    print(f"Found {len(assets)} tags.")

    rows = []
    cache_hits = 0
    fresh_fetches = 0

    for asset in assets:
        digest = asset.get("checksum", {}).get("sha256", "")
        path = asset["path"]  # e.g. v2/platform/corretto-java/manifests/21.2.3-567GRE7
        m = re.match(r"v2/(.+)/manifests/(.+)$", path)
        image_name, tag = (m.group(1), m.group(2)) if m else (path, "")

        if digest and digest in cache:
            size_bytes = cache[digest]
            cache_hits += 1
        else:
            # New digest we've never sized before -- one real, one-time hit.
            size_bytes = fetch_manifest_size_bytes(
                registry, repo, image_name, tag, auth, preferred_arch
            )
            if digest:
                cache[digest] = size_bytes
            fresh_fetches += 1

        rows.append({
            "repository": repo,
            "image_name": image_name,
            "tag": tag,
            "digest": digest,
            "size_mb": round(size_bytes / 1e6, 2),
            "last_modified": asset.get("lastModified"),
            "blob_created": asset.get("blobCreated"),
            "last_downloaded": asset.get("lastDownloaded"),
        })

    save_cache(cache_file, cache)

    with open(out_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {out_file}")
    print(f"Cache hits (zero registry contact): {cache_hits}")
    print(f"New digests fetched this run (one-time registry hit each): {fresh_fetches}")
    print(f"Cache saved to {cache_file} -- keep this file between runs.")


if __name__ == "__main__":
    main()
