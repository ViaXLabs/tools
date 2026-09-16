#!/usr/bin/env python3
"""
Nexus container image reporting — reference implementation.

Pulls Docker image tags from one or more Nexus Repository 3 hosted repos,
classifies each tag as "clean" (e.g. 21.2.3) or "dev_build" (e.g.
21.2.3-567GRE7), and writes two CSV reports:

    report_all_images.csv    -- every tag found
    report_clean_tags.csv    -- only the "clean" tags

See nexus_image_reporting_design.md for the reasoning behind every choice
made here (pagination, classification heuristic, why dates come from the
asset endpoint, the CSV color/links tradeoffs, common gotchas).

This is meant to be adapted, not run as-is: fill in NEXUS_BASE_URL,
NEXUS_REPOS, and the New Relic placeholders below, and wire credentials in
however your pipeline already handles them (this script assumes basic auth
via env vars, since you said Nexus connectivity is already solved on your
end -- swap in whatever auth your working pipeline already uses).
"""

from __future__ import annotations

import csv
import os
import re
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Iterator
from urllib.parse import quote

import requests  # pip install requests

# --------------------------------------------------------------------------
# Configuration -- fill these in for your environment
# --------------------------------------------------------------------------

NEXUS_BASE_URL = os.environ.get("NEXUS_BASE_URL", "https://nexus.example.com")
NEXUS_USER = os.environ.get("NEXUS_USER", "")
NEXUS_PASS = os.environ.get("NEXUS_PASS", "")

# The hosted docker repositories to report on. Point at the *hosted* repo
# name, not a group repo, unless you specifically want the group's merged
# view (see design doc, section 5, item 5).
NEXUS_REPOS = os.environ.get("NEXUS_REPOS", "docker-hosted").split(",")

# New Relic placeholders -- confirm the real attribute name your NR agent
# uses for the image reference, and your account ID, before relying on
# these links (see design doc, section 6).
NEW_RELIC_ACCOUNT_ID = os.environ.get("NEW_RELIC_ACCOUNT_ID", "REPLACE_ME")
NEW_RELIC_ATTRIBUTE = os.environ.get("NEW_RELIC_ATTRIBUTE", "containerImage")

OUTPUT_DIR = os.environ.get("REPORT_OUTPUT_DIR", ".")

# --------------------------------------------------------------------------
# Tag classification (see design doc, section 2)
# --------------------------------------------------------------------------

DEV_SUFFIX_RE = re.compile(r"^(?P<base>.+)-(?P<suffix>[A-Za-z0-9]{5,12})$")

KNOWN_QUALIFIERS = {
    "slim", "alpine", "jre", "jdk", "windows", "nanoserver",
    "bullseye", "bookworm", "focal", "jammy",
}


def classify_tag(tag: str) -> str:
    """Return 'clean' or 'dev_build'. Tune KNOWN_QUALIFIERS and the length
    bounds in DEV_SUFFIX_RE against a real tag dump before trusting this in
    production -- see design doc section 2.2."""
    m = DEV_SUFFIX_RE.match(tag)
    if not m:
        return "clean"
    suffix = m.group("suffix")
    if suffix.lower() in KNOWN_QUALIFIERS:
        return "clean"
    has_digit = any(c.isdigit() for c in suffix)
    has_alpha = any(c.isalpha() for c in suffix)
    return "dev_build" if (has_digit and has_alpha) else "clean"


# --------------------------------------------------------------------------
# Nexus API access
# --------------------------------------------------------------------------

@dataclass
class ImageRow:
    repository: str
    image_name: str
    tag: str
    classification: str
    digest: str
    created: str          # blobCreated
    last_updated: str      # lastModified
    last_pulled: str       # lastDownloaded, often empty
    size_kb: float
    age_days: float
    nexus_link: str
    new_relic_link: str


def _session() -> requests.Session:
    s = requests.Session()
    if NEXUS_USER:
        s.auth = (NEXUS_USER, NEXUS_PASS)
    return s


def iter_docker_assets(session: requests.Session, repository: str) -> Iterator[dict]:
    """Yields raw asset dicts from Nexus's asset-search endpoint, paginating
    via continuationToken until exhausted. This is the endpoint that
    actually carries lastModified/blobCreated/fileSize -- see design doc
    section 1.2 for why we use /search/assets rather than /search."""
    url = f"{NEXUS_BASE_URL}/service/rest/v1/search/assets"
    token = None
    while True:
        params = {"repository": repository, "format": "docker"}
        if token:
            params["continuationToken"] = token
        resp = session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("items", []):
            yield item
        token = data.get("continuationToken")
        if not token:
            break
        time.sleep(0.05)  # be polite to Nexus on large catalogs


def parse_manifest_path(path: str) -> tuple[str, str] | None:
    """Given an asset path like 'v2/platform/corretto-java/manifests/21.2.3',
    return (image_name, tag). Returns None for non-manifest paths (e.g.
    blob layers), which we deliberately skip -- see design doc section 5.3
    on why we report per-tag, not per-asset."""
    m = re.match(r"^v2/(?P<name>.+)/manifests/(?P<tag>[^/]+)$", path)
    if not m:
        return None
    return m.group("name"), m.group("tag")


def build_nexus_link(repository: str, image_name: str, tag: str) -> str:
    return (
        f"{NEXUS_BASE_URL}/#browse/browse:{repository}:"
        f"{quote(image_name, safe='')}%2F{quote(tag, safe='')}"
    )


def build_new_relic_link(image_name: str, tag: str) -> str:
    """Template link into New Relic's query builder, filtered by image:tag.
    Confirm NEW_RELIC_ATTRIBUTE matches what your NR integration actually
    populates before relying on this -- see design doc section 6."""
    nrql = (
        f"SELECT * FROM K8sContainerSample "
        f"WHERE {NEW_RELIC_ATTRIBUTE} LIKE '%{image_name}:{tag}%' "
        f"SINCE 1 day ago"
    )
    return (
        f"https://one.newrelic.com/nrql-console?"
        f"accountId={NEW_RELIC_ACCOUNT_ID}&query={quote(nrql)}"
    )


def age_in_days(iso_ts: str) -> float:
    if not iso_ts:
        return -1.0
    ts = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    return round((datetime.now(timezone.utc) - ts).total_seconds() / 86400, 1)


def collect_rows() -> list[ImageRow]:
    session = _session()
    rows: list[ImageRow] = []
    for repo in NEXUS_REPOS:
        repo = repo.strip()
        for asset in iter_docker_assets(session, repo):
            parsed = parse_manifest_path(asset.get("path", ""))
            if not parsed:
                continue  # skip blob/layer assets, keep only manifests
            image_name, tag = parsed
            checksum = asset.get("checksum", {}) or {}
            last_modified = asset.get("lastModified") or ""
            rows.append(ImageRow(
                repository=repo,
                image_name=image_name,
                tag=tag,
                classification=classify_tag(tag),
                digest=checksum.get("sha256", ""),
                created=asset.get("blobCreated") or "",
                last_updated=last_modified,
                last_pulled=asset.get("lastDownloaded") or "",
                size_kb=round((asset.get("fileSize") or 0) / 1024, 1),
                age_days=age_in_days(last_modified),
                nexus_link=build_nexus_link(repo, image_name, tag),
                new_relic_link=build_new_relic_link(image_name, tag),
            ))
    return rows


# --------------------------------------------------------------------------
# CSV output (Option A from the design doc -- plain CSV + a Classification
# column that Confluence-side conditional formatting can key off of)
# --------------------------------------------------------------------------

CSV_FIELDS = [
    "repository", "image_name", "tag", "classification", "digest",
    "created", "last_updated", "last_pulled", "size_kb", "age_days",
    "nexus_link", "new_relic_link",
]


def write_csv(rows: list[ImageRow], filename: str) -> None:
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))
    print(f"wrote {len(rows)} rows -> {path}")


# --------------------------------------------------------------------------
# Optional: Confluence storage-format HTML table (Option B from the design
# doc) -- real background colors and real <a href> links, no dependency on
# which Confluence macros are installed. Only use this if your Harness
# Confluence step can accept a raw page body rather than a CSV attachment.
# --------------------------------------------------------------------------

ROW_COLORS = {
    "clean": "#E3F2E1",       # light green
    "dev_build": "#FFF4E0",   # light amber
}


def build_confluence_storage_table(rows: list[ImageRow], title: str) -> str:
    header_cells = "".join(f"<th>{h}</th>" for h in [
        "Repository", "Image", "Tag", "Status", "Created",
        "Last Updated", "Age (days)", "Nexus", "New Relic",
    ])
    body_rows = []
    for r in rows:
        color = ROW_COLORS.get(r.classification, "#FFFFFF")
        body_rows.append(
            f'<tr style="background-color:{color};">'
            f"<td>{r.repository}</td>"
            f"<td>{r.image_name}</td>"
            f"<td>{r.tag}</td>"
            f"<td>{r.classification}</td>"
            f"<td>{r.created}</td>"
            f"<td>{r.last_updated}</td>"
            f"<td>{r.age_days}</td>"
            f'<td><a href="{r.nexus_link}">view</a></td>'
            f'<td><a href="{r.new_relic_link}">view</a></td>'
            f"</tr>"
        )
    return (
        f"<h2>{title}</h2>"
        f"<table><thead><tr>{header_cells}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody></table>"
    )


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> int:
    rows = collect_rows()
    if not rows:
        print("no image rows collected -- check repository names / auth / "
              "connectivity before assuming the classification logic is at "
              "fault", file=sys.stderr)
        return 1

    clean_rows = [r for r in rows if r.classification == "clean"]

    write_csv(rows, "report_all_images.csv")
    write_csv(clean_rows, "report_clean_tags.csv")

    # Uncomment if you're going with Option B (direct Confluence publish
    # instead of/alongside CSV attachments):
    #
    # html = build_confluence_storage_table(rows, "All Images")
    # with open(os.path.join(OUTPUT_DIR, "all_images_table.html"), "w") as f:
    #     f.write(html)

    counts = {}
    for r in rows:
        counts[r.classification] = counts.get(r.classification, 0) + 1
    print(f"classification breakdown: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
