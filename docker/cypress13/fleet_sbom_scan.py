#!/usr/bin/env python3
"""
fleet_sbom_scan.py

Takes the image list from nexus_list_images.py, generates a real SBOM
(CycloneDX JSON, via Syft) for every image directly against the
registry -- no docker pull / no local daemon needed -- then rolls a
curated subset of package versions into one consolidated CSV, and
archives the full SBOM per image alongside it.

Requires on PATH: docker (just for `docker login`, to hand Syft working
                  registry credentials via the standard Docker config)
                  syft (https://github.com/anchore/syft#installation)

Usage:
  ./fleet_sbom_scan.py <images-file>

Env vars (required):
  NEXUS_REGISTRY, NEXUS_USER, NEXUS_PASS

Env vars (optional):
  INTERESTED_PACKAGES  space-separated package names to pull into their
                       own CSV columns. Default: "node npm cypress python python3"
  SBOM_DIR              where full per-image SBOMs are archived, default "sboms"
  SUMMARY_CSV            consolidated report path, default "fleet-versions.csv"
"""
import csv
import json
import os
import subprocess
import sys


def env(name, required=True, default=None):
    val = os.environ.get(name, default)
    if required and not val:
        sys.exit(f"Set {name} (see script header for details)")
    return val


def docker_login(registry, user, password):
    print(f"Logging in to {registry} (so syft can reuse the Docker credential store) ...")
    subprocess.run(
        ["docker", "login", registry, "-u", user, "--password-stdin"],
        input=password, text=True, check=True,
    )


def scan_one(registry, repo, tag, sbom_dir):
    safe_name = repo.replace("/", "_").replace(":", "_")
    sbom_file = os.path.join(sbom_dir, f"{safe_name}_{tag}.cdx.json")
    result = subprocess.run(
        [
            "syft", "scan", f"registry:{registry}/{repo}:{tag}",
            "-o", f"cyclonedx-json={sbom_file}",
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None, result.stderr.strip()
    return sbom_file, None


def extract_versions(sbom_file, packages):
    with open(sbom_file) as f:
        sbom = json.load(f)
    components = sbom.get("components") or []
    versions = []
    for pkg in packages:
        match = next((c for c in components if c.get("name") == pkg), None)
        versions.append(match["version"] if match else "not found")
    return versions


def main():
    if len(sys.argv) != 2:
        sys.exit(f"Usage: {sys.argv[0]} <images-file>")
    images_file = sys.argv[1]

    registry = env("NEXUS_REGISTRY")
    user = env("NEXUS_USER")
    password = env("NEXUS_PASS")
    packages = env(
        "INTERESTED_PACKAGES", required=False,
        default="node npm cypress python python3",
    ).split()
    sbom_dir = env("SBOM_DIR", required=False, default="sboms")
    summary_csv = env("SUMMARY_CSV", required=False, default="fleet-versions.csv")

    os.makedirs(sbom_dir, exist_ok=True)
    docker_login(registry, user, password)

    with open(images_file) as f:
        lines = [line.strip() for line in f if line.strip()]

    header = ["repository", "tag"] + [f"{p}_version" for p in packages] + ["sbom_path"]

    total = 0
    failed = 0
    with open(summary_csv, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(header)

        for line in lines:
            total += 1
            repo, _, tag = line.rpartition(":")

            print(f"[{total}] Scanning {repo}:{tag} ...")
            sbom_file, error = scan_one(registry, repo, tag, sbom_dir)

            if error:
                print(f"  FAILED -- {error}", file=sys.stderr)
                failed += 1
                writer.writerow([repo, tag] + ["scan-failed"] * len(packages) + [""])
                continue

            versions = extract_versions(sbom_file, packages)
            writer.writerow([repo, tag] + versions + [sbom_file])

    print(f"\nDone: {total} images scanned, {failed} failed.")
    print(f"Summary:    {summary_csv}")
    print(f"Full SBOMs: {sbom_dir}/")


if __name__ == "__main__":
    main()
