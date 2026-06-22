#!/usr/bin/env python3
"""
security_revert.py — Swap tokens back to original values in bot responses.
===========================================================================

After getting a response from your gov chatbot, run this to replace every
[TOKEN-NNNN] back to its original sensitive value.

USAGE:
  python security_revert.py --tag <tag> --response-file bot_answer.txt
  python security_revert.py --tag <tag> --response "the [SSN-0001] field…"
  python security_revert.py --tag <tag> --response-file answer.txt --out reverted.txt

ARGUMENTS:
  --tag             The same tag you used with repo_scan.py
  --response        Bot response as a quoted string
  --response-file   File containing the bot response

OPTIONS:
  --map             Path to *_map.json  (auto-detected from --tag if omitted)
  --out             Write reverted output to this file  (default: print to stdout)
  --verbose         Show each token → original swap

⚠  The output of this script contains REAL sensitive data.
   Do NOT paste it back into any AI chat.
"""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    from _scanner.warnings import REVERT_BANNER, YELLOW, BOLD, RESET
except ImportError:
    REVERT_BANNER = "\n⚠  REVERT TOOL — output contains real sensitive data.\n"
    YELLOW = BOLD = RESET = ""

DEFAULTS = {
    "map_base": "./repo_scans",
}


def find_map(tag: str, explicit_map: str | None) -> Path:
    if explicit_map:
        p = Path(explicit_map)
        if not p.exists():
            print(f"[ERROR] Map file not found: {p}")
            sys.exit(1)
        return p
    auto = Path(DEFAULTS["map_base"]) / tag / f"{tag}_map.json"
    if auto.exists():
        return auto
    print(f"[ERROR] Cannot find substitution map.")
    print(f"  Looked for: {auto}")
    print(f"  Use --map /path/to/{tag}_map.json to specify it explicitly.")
    sys.exit(1)


def load_map(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("token_to_original", {})


def revert_text(text: str, token_map: dict[str, str], verbose: bool) -> tuple[str, list]:
    if not token_map:
        return text, []

    sorted_tokens = sorted(token_map.keys(), key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(t) for t in sorted_tokens))
    swaps = []

    def replacer(m: re.Match) -> str:
        tok  = m.group(0)
        orig = token_map[tok]
        swaps.append({"token": tok, "original": orig, "pos": m.start()})
        return orig

    reverted = pattern.sub(replacer, text)

    if verbose:
        print(f"\n  {YELLOW}Tokens swapped: {len(swaps)}{RESET}", file=sys.stderr)
        for s in swaps:
            disp = s["original"][:60] + "…" if len(s["original"]) > 60 else s["original"]
            print(f"  {BOLD}{s['token']:<24}{RESET}→  {disp}", file=sys.stderr)

    return reverted, swaps


def parse_args():
    p = argparse.ArgumentParser(
        prog="security_revert.py",
        description="Swap tokens back to original values in gov chatbot responses.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--tag",           required=True,
                   help="Tag used when running repo_scan.py")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--response",      type=str,
                       help="Bot response as a quoted string")
    group.add_argument("--response-file", type=Path,
                       help="File containing the bot response")
    p.add_argument("--map",           default=None,
                   help="Path to *_map.json  (auto-detected from --tag if omitted)")
    p.add_argument("--out",           type=Path, default=None,
                   help="Write output to this file  (default: print to stdout)")
    p.add_argument("--verbose",       action="store_true",
                   help="Print each token → original swap")
    return p.parse_args()


def main():
    args = parse_args()

    print(REVERT_BANNER, file=sys.stderr)

    map_path  = find_map(args.tag, args.map)
    token_map = load_map(map_path)
    print(f"[revert] Map loaded: {len(token_map)} tokens  ({map_path})", file=sys.stderr)

    if args.response:
        text = args.response
    else:
        rf = args.response_file
        if not rf.exists():
            print(f"[ERROR] Response file not found: {rf}")
            sys.exit(1)
        text = rf.read_text(encoding="utf-8", errors="replace")

    print(f"[revert] Response: {len(text):,} chars", file=sys.stderr)

    reverted, swaps = revert_text(text, token_map, args.verbose)

    not_in_response = [t for t in token_map if t not in text]
    print(f"[revert] Tokens in response    : {len(swaps)}", file=sys.stderr)
    print(f"[revert] Tokens NOT referenced : {len(not_in_response)}", file=sys.stderr)

    if len(swaps) == 0:
        print(f"\n[revert] ⚠  No tokens found in response.", file=sys.stderr)
        print(f"         Check you are using the correct tag: --tag {args.tag}", file=sys.stderr)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(reverted, encoding="utf-8")
        print(f"[revert] ✓ Written → {args.out}", file=sys.stderr)
    else:
        print(reverted)


if __name__ == "__main__":
    main()
