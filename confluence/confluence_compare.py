#!/usr/bin/env python3
"""
confluence_compare.py

Compares the page trees produced by confluence_export.py — either two
spaces head-to-head, or one or more spaces against a reference
("greenfield") structure — and reports what's missing, extra, or drifted.

--------------------------------------------------------------------------
TWO SPACES, HEAD-TO-HEAD
    python confluence_compare.py --a GREENFIELD_tree.json --b TEAMA_tree.json

ONE REFERENCE AGAINST SEVERAL TARGETS (the audit use case)
    python confluence_compare.py --reference GREENFIELD_tree.json \
        --target TEAMA_tree.json --target TEAMB_tree.json --target TEAMC_tree.json

SKIP NOISY PAGES FROM THE COMPARISON (e.g. dated meeting notes)
    python confluence_compare.py --reference GREENFIELD_tree.json --target TEAMA_tree.json \
        --ignore-regex "Meeting Notes/.*"
--------------------------------------------------------------------------

Matching is by page PATH (titles from root, whitespace/case-normalized),
not by page ID — IDs are space-specific and meaningless across spaces.
A renamed page will show up as one "missing" path and one "extra" path;
that's intentional — it tells you exactly what changed, not just that
something did.
"""

import argparse
import json
import re
import sys


def load_tree(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Tolerate either a full confluence_export.py output file, or a bare
    # list of root nodes.
    return data.get("tree", data) if isinstance(data, dict) else data


def normalize(title):
    return " ".join(title.strip().lower().split())


def flatten(nodes, prefix=()):
    """Yield a path tuple for every node in the tree, root pages included."""
    for n in nodes:
        path = prefix + (normalize(n["title"]),)
        yield path
        yield from flatten(n.get("children", []), path)


def compare(reference_nodes, target_nodes, ignore_regex=None):
    ref_paths = set(flatten(reference_nodes))
    tgt_paths = set(flatten(target_nodes))

    if ignore_regex:
        pattern = re.compile(ignore_regex, re.IGNORECASE)

        def keep(path):
            return not pattern.search(" / ".join(path))

        ref_paths = {p for p in ref_paths if keep(p)}
        tgt_paths = {p for p in tgt_paths if keep(p)}

    missing = sorted(ref_paths - tgt_paths)
    extra = sorted(tgt_paths - ref_paths)
    matched = ref_paths & tgt_paths
    conformance = (len(matched) / len(ref_paths) * 100) if ref_paths else 100.0

    return {
        "reference_page_count": len(ref_paths),
        "target_page_count": len(tgt_paths),
        "matched_count": len(matched),
        "conformance_pct": round(conformance, 1),
        "missing": [" / ".join(p) for p in missing],
        "extra": [" / ".join(p) for p in extra],
    }


def print_report(name, result):
    print(f"\n=== {name} ===")
    print(
        f"Reference pages: {result['reference_page_count']}   "
        f"Target pages: {result['target_page_count']}   "
        f"Conformance: {result['conformance_pct']}%"
    )
    if result["missing"]:
        print(f"\nMissing ({len(result['missing'])}) -- in reference, not in target:")
        for p in result["missing"]:
            print(f"  - {p}")
    if result["extra"]:
        print(f"\nExtra ({len(result['extra'])}) -- in target, not in reference:")
        for p in result["extra"]:
            print(f"  + {p}")
    if not result["missing"] and not result["extra"]:
        print("Structure matches the reference exactly.")


def main():
    parser = argparse.ArgumentParser(description="Compare Confluence space page trees.")
    parser.add_argument("--a", help="First tree JSON (head-to-head mode)")
    parser.add_argument("--b", help="Second tree JSON (head-to-head mode)")
    parser.add_argument("--reference", help="Reference/greenfield tree JSON (audit mode)")
    parser.add_argument("--target", action="append", default=[], help="Target tree JSON, repeatable (audit mode)")
    parser.add_argument("--ignore-regex", help="Skip paths matching this regex from the comparison")
    parser.add_argument("--json-out", help="Also write machine-readable results to this file")
    args = parser.parse_args()

    results = {}

    if args.a and args.b:
        ref, tgt = load_tree(args.a), load_tree(args.b)
        result = compare(ref, tgt, args.ignore_regex)
        print_report(f"{args.a}  vs  {args.b}", result)
        results[args.b] = result

    elif args.reference and args.target:
        ref = load_tree(args.reference)
        for t in args.target:
            tgt = load_tree(t)
            result = compare(ref, tgt, args.ignore_regex)
            print_report(f"{args.reference}  vs  {t}", result)
            results[t] = result

        if len(args.target) > 1:
            print("\n=== Summary ===")
            for t, r in results.items():
                print(
                    f"  {t:<30} {r['conformance_pct']:>5}% conformance   "
                    f"({r['matched_count']}/{r['reference_page_count']} pages, "
                    f"{len(r['extra'])} extra)"
                )
    else:
        parser.error("Provide either --a and --b, or --reference and one or more --target.")
        return

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"\nWrote machine-readable results to {args.json_out}")


if __name__ == "__main__":
    main()
