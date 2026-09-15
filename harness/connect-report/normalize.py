#!/usr/bin/env python3
"""Combine everything in ./fetched/*.json into one normalized deployment record."""
import json, glob, os, sys
from datetime import datetime, timezone

FETCH_DIR = os.environ.get("FETCH_DIR", "./fetched")
OUT_PATH = os.environ.get("NORMALIZED_PATH", "./normalized/record.json")

def load_envelopes():
    envelopes = {}
    for path in glob.glob(os.path.join(FETCH_DIR, "*.json")):
        with open(path) as f:
            data = json.load(f)
        envelopes[data["source_system"]] = data
    return envelopes

def build_record(envelopes):
    harness = envelopes.get("harness", {}).get("payload", {})
    github = envelopes.get("github", {}).get("payload", {})
    aws = envelopes.get("aws", {})
    argocd = envelopes.get("argocd", {}).get("payload", {})
    jira = envelopes.get("jira", {}).get("payload", {})
    confluence = envelopes.get("confluence", {}).get("payload", {})
    newrelic = envelopes.get("newrelic", {}).get("payload", {})
    newrelic_nerdgraph = newrelic.get("nerdgraph") or {}
    newrelic_insights = newrelic.get("insights") or {}
    newrelic_results = (
        newrelic_nerdgraph.get("data", {}).get("actor", {}).get("account", {}).get("nrql", {}).get("results", [])
        or newrelic_insights.get("results", [])
    )
    nexus = envelopes.get("nexus", {}).get("payload", {})

    service = next((e["service"] for e in envelopes.values() if e.get("service") and e["service"] != "unknown"), "unknown")
    environment = next((e["environment"] for e in envelopes.values() if e.get("environment") and e["environment"] != "unknown"), "unknown")

    record = {
        "service": service,
        "environment": environment,
        "reported_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "commit_sha": github.get("commit", {}).get("sha"),
            "commit_message": github.get("commit", {}).get("commit", {}).get("message"),
            "pull_requests": [pr.get("number") for pr in github.get("pull_requests", [])],
        },
        "build": {
            "pipeline_execution_id": harness.get("executionId") or harness.get("id"),
            "status": harness.get("status"),
        },
        "infra": {
            "cluster_type": aws.get("cluster_type"),
            "cluster_details": aws.get("payload"),
        },
        "rollout": {
            "sync_status": argocd.get("status", {}).get("sync", {}).get("status"),
            "health_status": argocd.get("status", {}).get("health", {}).get("status"),
        },
        "tickets": [
            {"key": i.get("key"), "status": i.get("fields", {}).get("status", {}).get("name")}
            for i in jira.get("issues", [])
        ],
        "docs": [
            {
                "title": page.get("title"),
                "url": page.get("_links", {}).get("webui"),
                "last_updated": page.get("version", {}).get("when"),
            }
            for page in confluence.get("results", [])
        ],
        "artifact": {
            "nexus": [
                {
                    "name": item.get("name"),
                    "version": item.get("version"),
                    "assets": [
                        {"path": a.get("path"), "checksum_sha1": a.get("checksum", {}).get("sha1")}
                        for a in item.get("assets", [])
                    ],
                }
                for item in nexus.get("items", [])
            ],
        },
        "security": {},   # not tracked yet - Nexus IQ / SonarQube / Checkmarx would land here
        "health": {
            "newrelic": newrelic_results,
        },
    }
    return record

def main():
    envelopes = load_envelopes()
    if not envelopes:
        print("No fetched data found in", FETCH_DIR, file=sys.stderr)
        sys.exit(1)
    record = build_record(envelopes)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(record, f, indent=2)
    print("Wrote", OUT_PATH)

if __name__ == "__main__":
    main()
