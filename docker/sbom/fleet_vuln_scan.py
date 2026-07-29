#!/usr/bin/env python3
"""
fleet_vuln_scan.py

Runs Grype against every SBOM already produced by fleet_sbom_scan.py --
it rescans the archived SBOM, not the registry, so this is fast and
doesn't need registry credentials at all. Rolls CVE counts by severity
into one summary CSV, with the full per-image vulnerability report
(every CVE ID, package, fix version) archived alongside the SBOMs.

Requires on PATH: grype (https://github.com/anchore/grype#installation)

Usage:
  ./fleet_vuln_scan.py fleet-versions.csv

Env vars (optional):
  VULN_DIR           where full per-image vulnerability reports are archived,
                     default "vulns"
  VULN_SUMMARY_CSV    consolidated report path, default "fleet-vulns-summary.csv"

This is a reporting tool only -- it never fails the pipeline on findings.
"""
import csv
import json
import os
import subprocess
import sys

SEVERITY_ORDER = ["negligible", "low", "medium", "high", "critical"]


def env(name, required=True, default=None):
    val = os.environ.get(name, default)
    if required and not val:
        sys.exit(f"Set {name} (see script header for details)")
    return val


def scan_one(sbom_path, vuln_dir):
    base = os.path.splitext(os.path.basename(sbom_path))[0]
    out_path = os.path.join(vuln_dir, f"{base}.vulns.json")
    result = subprocess.run(
        ["grype", f"sbom:{sbom_path}", "-o", "json"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None, result.stderr.strip()
    with open(out_path, "w") as f:
        f.write(result.stdout)
    return out_path, None


def summarize(vuln_json_path):
    with open(vuln_json_path) as f:
        data = json.load(f)
    matches = data.get("matches") or []
    counts = {s: 0 for s in SEVERITY_ORDER}
    cve_ids = []
    for m in matches:
        vuln = m.get("vulnerability") or {}
        sev = (vuln.get("severity") or "unknown").lower()
        if sev in counts:
            counts[sev] += 1
        cve_ids.append(vuln.get("id", ""))
    return counts, cve_ids


def main():
    if len(sys.argv) != 2:
        sys.exit(f"Usage: {sys.argv[0]} <fleet-versions.csv>")
    versions_csv = sys.argv[1]

    vuln_dir = env("VULN_DIR", required=False, default="vulns")
    summary_csv = env("VULN_SUMMARY_CSV", required=False, default="fleet-vulns-summary.csv")

    os.makedirs(vuln_dir, exist_ok=True)

    with open(versions_csv, newline="") as f:
        rows = list(csv.DictReader(f))

    header = (
        ["repository", "tag"]
        + [f"{s}_count" for s in SEVERITY_ORDER]
        + ["total_cves", "vuln_report_path", "cve_ids"]
    )

    total = 0
    failed = 0

    with open(summary_csv, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(header)

        for row in rows:
            repo, tag = row["repository"], row["tag"]
            sbom_path = row.get("sbom_path", "")

            if not sbom_path:
                # Syft already failed on this image -- nothing to scan.
                writer.writerow([repo, tag] + ["n/a"] * len(SEVERITY_ORDER) + ["n/a", "", ""])
                continue

            total += 1
            print(f"[{total}] Vulnerability scan: {repo}:{tag} ...")
            vuln_json_path, error = scan_one(sbom_path, vuln_dir)

            if error:
                print(f"  FAILED -- {error}", file=sys.stderr)
                failed += 1
                writer.writerow([repo, tag] + ["scan-failed"] * len(SEVERITY_ORDER) + ["scan-failed", "", ""])
                continue

            counts, cve_ids = summarize(vuln_json_path)
            writer.writerow(
                [repo, tag]
                + [counts[s] for s in SEVERITY_ORDER]
                + [sum(counts.values()), vuln_json_path, ";".join(cve_ids)]
            )

    print(f"\nDone: {total} images scanned for vulnerabilities, {failed} failed.")
    print(f"Summary:      {summary_csv}")
    print(f"Full reports: {vuln_dir}/")


if __name__ == "__main__":
    main()
