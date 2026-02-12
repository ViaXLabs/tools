#!/usr/bin/env python3
"""
Local test harness (no New Relic calls).

This helps you sanity-check:
  - derived team mapping
  - missing required tags proposals
  - invalid tags flagged
  - replacements only proposed when enabled

Run:
  python local_test_policy.py --policy tag_policy.json
"""

import argparse
import json

from tag_policy import evaluate_entity, load_policy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", required=True)
    args = parser.parse_args()

    policy = load_policy(args.policy)

    samples = [
        {
            "guid": "GUID-1",
            "name": "my-service SAVE something",
            "domain": "APM",
            "entityType": "APM-APPLICATION",
            "tags": [{"key": "owner", "values": ["bob"]}, {"key": "something", "values": ["Save"]}],
        },
        {
            "guid": "GUID-2",
            "name": "pet-processor",
            "domain": "APM",
            "entityType": "APM-APPLICATION",
            "tags": [{"key": "team", "values": ["already-set"]}, {"key": "system", "values": ["BADVALUE"]}],
        },
        {
            "guid": "GUID-3",
            "name": "unknown-service",
            "domain": "INFRA",
            "entityType": "HOST",
            "tags": [{"key": "system", "values": ["Verifications/SVS"]}],
        },
    ]

    print("=== DEFAULT (no replacements proposed) ===")
    for s in samples:
        r = evaluate_entity(s, policy, propose_replacements=False)
        print(json.dumps(r, indent=2))

    print("\n=== WITH replacements proposed ===")
    for s in samples:
        r = evaluate_entity(s, policy, propose_replacements=True)
        print(json.dumps(r, indent=2))


if __name__ == "__main__":
    main()
