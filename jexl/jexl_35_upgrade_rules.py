#!/usr/bin/env python3
"""
jexl_35_upgrade_rules.py

Rule set + reporting for the Harness JEXL 3.0 -> 3.5 upgrade. Imports
jexl_scanner.py for the generic "find repos, find .harness YAML, extract
JEXL expressions" work, and adds on top of it:

  - the four known breaking patterns for this specific upgrade
  - a concrete suggested fix/rewrite for each hit (not just a description)
  - JSON + Markdown report generation

Background (Harness release notes, self-managed & SaaS CD/CI):
  Harness is upgrading the expression engine from JEXL 3.0 to 3.5 to
  tighten security. Four categories of expressions are affected:

    R1  Reflection-based expressions are blocked outright
        e.g. <+''.getClass().forName("java.lang.Runtime")>
    R2  Nested subscript ([...] inside [...]) must be rewritten
    R3  Global variable assignment (bare `=`, not `==`) is disallowed
    R4  Ternary immediately followed by `[` breaks: `?[` is now parsed
        as the null-safe array-access operator, swallowing the rest of
        the ternary.
        e.g. <+pipeline.variables.BUILD_ENVS=="dev"?[""]:"qa">
        Fix: add a space (`? [`) or wrap the array in parens.

To add a new rule (e.g. once Harness publishes more migration guidance),
add a Rule instance to RULES below - nothing in jexl_scanner.py needs to
change.

USAGE
  python3 jexl_35_upgrade_rules.py --repos-root /path/to/checked-out-repos
  python3 jexl_35_upgrade_rules.py --repo-list repos.txt
  python3 jexl_35_upgrade_rules.py --repos-root . --out-json report.json --out-md report.md
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from typing import Callable, List, Optional

import jexl_scanner


# ---------------------------------------------------------------------------
# Rule definitions
# ---------------------------------------------------------------------------

@dataclass
class RuleHit:
    rule_id: str
    label: str
    detail: str
    suggestion: str


@dataclass
class Rule:
    rule_id: str
    label: str
    description: str
    # check(expr) -> detail string if it fires, else None
    check: Callable[[str], Optional[str]]
    # suggest(expr) -> concrete suggested fix/rewrite text
    suggest: Callable[[str], str]


REFLECTION_RE = re.compile(
    r"\b(getClass|forName|getMethod|getDeclaredMethod|getDeclaredField|"
    r"getField|newInstance|invoke|Class\s*\.\s*forName)\s*\(",
)

# bare '=' that is not part of ==, !=, <=, >=, =~
ASSIGNMENT_RE = re.compile(r"(?<![=!<>~])=(?!=)")

# ternary '?' immediately followed by '[' (no whitespace)
TERNARY_BRACKET_RE = re.compile(r"\?\[")


def _check_reflection(expr: str) -> Optional[str]:
    m = REFLECTION_RE.search(expr)
    if not m:
        return None
    return f"matched call: {m.group(0)}"


def _suggest_reflection(expr: str) -> str:
    return (
        "Remove the reflection-based call - JEXL 3.5 blocks it outright, "
        "there is no rewrite that preserves it. Replace with a Harness "
        "built-in expression if one covers the same data, or move the "
        "logic into a Shell Script / Run step where you have a real "
        "scripting language instead of an expression."
    )


def _check_nested_subscript(expr: str) -> Optional[str]:
    """True if expr contains '[' ... '[' ... ']' ... ']' nesting, i.e. a
    subscript accessor nested directly inside another subscript accessor.
    Chained subscripts like list[0][1] are NOT nested and are fine."""
    depth = 0
    max_depth = 0
    for ch in expr:
        if ch == "[":
            depth += 1
            max_depth = max(max_depth, depth)
        elif ch == "]":
            depth = max(0, depth - 1)
    if max_depth >= 2:
        return "found a subscript accessor nested directly inside another subscript accessor"
    return None


def _suggest_nested_subscript(expr: str) -> str:
    return (
        "Rewrite so the inner subscript is resolved first, rather than "
        "nested inline. Concretely: pull the inner index/key expression "
        "out into its own resolved value (e.g. a prior step's output "
        "variable or a pipeline variable) and reference that value in "
        "the outer subscript, instead of writing one [...] directly "
        "inside another [...]. There is no automatic string rewrite "
        "for this one - it depends on what the inner expression resolves to."
    )


def _check_assignment(expr: str) -> Optional[str]:
    matches = list(ASSIGNMENT_RE.finditer(expr))
    if not matches:
        return None
    offsets = [m.start() for m in matches]
    return f"{len(matches)} bare '=' occurrence(s) at char offset(s) {offsets}"


def _suggest_assignment(expr: str) -> str:
    fixed = ASSIGNMENT_RE.sub("==", expr)
    if fixed != expr:
        return (
            f"If this was meant as a comparison, use '==' instead of '=': "
            f"suggested rewrite: `{fixed}`. If this was meant as an actual "
            f"variable assignment (e.g. `var foo = 'abc'`), JEXL 3.5 "
            f"disallows that entirely in Harness expressions - move that "
            f"logic into a Shell Script step instead."
        )
    return (
        "Use '==' for comparisons; JEXL 3.5 disallows bare '=' "
        "(global variable assignment). If this is an actual assignment, "
        "move it to a Shell Script step."
    )


def _check_ternary_bracket(expr: str) -> Optional[str]:
    if TERNARY_BRACKET_RE.search(expr):
        return "matched pattern: ?["
    return None


def _suggest_ternary_bracket(expr: str) -> str:
    fixed = TERNARY_BRACKET_RE.sub("? [", expr)
    return (
        f"Add a space after '?' (or wrap the array literal in parens) so "
        f"the parser doesn't read '?[' as the null-safe array-access "
        f"operator. Suggested rewrite: `{fixed}`"
    )


RULES: List[Rule] = [
    Rule(
        "R1_REFLECTION",
        "Reflection blocked",
        "Reflection-based expressions (getClass/forName/invoke/etc.) are "
        "rejected outright in JEXL 3.5.",
        _check_reflection,
        _suggest_reflection,
    ),
    Rule(
        "R2_NESTED_SUBSCRIPT",
        "Nested subscript",
        "A [...] accessor nested directly inside another [...] must be "
        "rewritten.",
        _check_nested_subscript,
        _suggest_nested_subscript,
    ),
    Rule(
        "R3_ASSIGNMENT",
        "Bare assignment (=)",
        "Bare '=' (assignment) is disallowed; use '==' for comparisons.",
        _check_assignment,
        _suggest_assignment,
    ),
    Rule(
        "R4_TERNARY_BRACKET",
        "Ternary + [ (?[)",
        "A ternary immediately followed by '[' is parsed as the null-safe "
        "array-access operator in 3.5, breaking the ternary.",
        _check_ternary_bracket,
        _suggest_ternary_bracket,
    ),
]

RULE_LABELS = {r.rule_id: r.label for r in RULES}


def evaluate_expression(expr: str) -> List[RuleHit]:
    """Run every rule in RULES against a single JEXL expression string."""
    hits = []
    for rule in RULES:
        detail = rule.check(expr)
        if detail is not None:
            hits.append(RuleHit(
                rule_id=rule.rule_id,
                label=rule.label,
                detail=detail,
                suggestion=rule.suggest(expr),
            ))
    return hits


# ---------------------------------------------------------------------------
# Findings: a scanner occurrence + its rule hits
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    repo: str
    file: str
    start_line: int
    end_line: int
    expression: str
    rule_hits: list

    def to_dict(self):
        return {
            "repo": self.repo,
            "file": self.file,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "expression": self.expression,
            "rule_hits": [asdict(h) for h in self.rule_hits],
        }


def build_findings(occurrences) -> List[Finding]:
    findings = []
    for occ in occurrences:
        hits = evaluate_expression(occ.expression)
        findings.append(Finding(
            repo=occ.repo,
            file=occ.file,
            start_line=occ.start_line,
            end_line=occ.end_line,
            expression=occ.expression,
            rule_hits=hits,
        ))
    return findings


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def write_json_report(findings, warnings, path, scanned_repos, scanned_files):
    at_risk = [f for f in findings if f.rule_hits]
    payload = {
        "summary": {
            "scanned_repos": scanned_repos,
            "scanned_files": scanned_files,
            "total_jexl_expressions_found": len(findings),
            "expressions_at_risk": len(at_risk),
            "warnings_count": len(warnings),
        },
        "warnings": warnings,
        "findings": [f.to_dict() for f in findings],
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)


def write_md_report(findings, warnings, path, scanned_repos, scanned_files):
    at_risk = [f for f in findings if f.rule_hits]

    by_rule = {}
    for f in at_risk:
        for h in f.rule_hits:
            by_rule.setdefault(h.rule_id, []).append((f, h))

    lines = []
    lines.append("# Harness JEXL 3.5 upgrade impact report\n")
    lines.append(
        "Scans `.harness/**/*.yaml` pipelines for JEXL usage and flags "
        "expressions matching known JEXL 3.0 -> 3.5 breaking patterns, "
        "with a suggested fix for each.\n"
    )
    lines.append(f"- Repos scanned: **{scanned_repos}**")
    lines.append(f"- Pipeline YAML files scanned: **{scanned_files}**")
    lines.append(f"- Total JEXL expressions found: **{len(findings)}**")
    lines.append(f"- Expressions flagged at risk: **{len(at_risk)}**")
    lines.append(f"- Warnings (e.g. missing .harness, sparse-checkout gaps): **{len(warnings)}**\n")

    if warnings:
        lines.append("## Warnings\n")
        for w in warnings:
            lines.append(f"- {w}")
        lines.append("")

    lines.append("## At-risk expressions, by rule\n")
    if not at_risk:
        lines.append("None found.\n")
    for rule in RULES:
        group = by_rule.get(rule.rule_id, [])
        lines.append(f"### {rule.label} (`{rule.rule_id}`) — {len(group)} occurrence(s)\n")
        lines.append(f"_{rule.description}_\n")
        if not group:
            lines.append("_none found_\n")
            continue
        for f, h in group:
            lines.append(f"- `{f.repo}` / `{f.file}:{f.start_line}`")
            lines.append(f"  - expression: `{f.expression}`")
            lines.append(f"  - detail: {h.detail}")
            lines.append(f"  - suggested fix: {h.suggestion}")
        lines.append("")

    lines.append("## All JEXL usage (full inventory)\n")
    lines.append("| Repo | File | Line | Expression | Flags |")
    lines.append("|---|---|---|---|---|")
    for f in findings:
        flags = ", ".join(h.label for h in f.rule_hits) or "-"
        expr_display = f.expression.replace("|", "\\|")
        if len(expr_display) > 120:
            expr_display = expr_display[:117] + "..."
        lines.append(f"| {f.repo} | {f.file} | {f.start_line} | `{expr_display}` | {flags} |")

    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--repos-root", help="Directory containing many repo checkouts as subdirectories (or a single repo).")
    parser.add_argument("--repo-list", help="Text file, one repo path per line.")
    parser.add_argument("--out-json", default="jexl_report.json", help="Path to write JSON report.")
    parser.add_argument("--out-md", default="jexl_report.md", help="Path to write Markdown report.")
    args = parser.parse_args()

    if not args.repos_root and not args.repo_list:
        parser.error("must supply --repos-root and/or --repo-list")

    scan_result = jexl_scanner.scan_repos(args.repos_root, args.repo_list)
    findings = build_findings(scan_result.occurrences)

    write_json_report(findings, scan_result.warnings, args.out_json,
                       scan_result.scanned_repos, scan_result.scanned_files)
    write_md_report(findings, scan_result.warnings, args.out_md,
                     scan_result.scanned_repos, scan_result.scanned_files)

    at_risk = [f for f in findings if f.rule_hits]
    print(f"Scanned {scan_result.scanned_repos} repos, {scan_result.scanned_files} pipeline YAML files.")
    print(f"Found {len(findings)} JEXL expressions total, {len(at_risk)} flagged at risk.")
    if scan_result.warnings:
        print(f"{len(scan_result.warnings)} warning(s) - see report for details.")
    print(f"Reports written to {args.out_json} and {args.out_md}")


if __name__ == "__main__":
    main()
