#!/usr/bin/env python3
"""
jexl_scanner.py

Generic, rule-agnostic scanner: finds .harness/**/*.yaml pipeline files
across many repos and extracts every JEXL expression (<+...>) found in them.

This module deliberately knows NOTHING about which expressions are
"risky" or why - that logic lives in a separate rules module (e.g.
jexl_35_upgrade_rules.py) that imports this one. That way:
  - the scanning/discovery logic is reusable for any future rule set
    (a different Harness upgrade, a style lint, a deprecated-variable
    search, etc.)
  - rules can be added/changed/versioned without touching how repos
    and expressions are found.

Public API:
  extract_jexl_expressions(text) -> list[(start_line, end_line, expr)]
  find_harness_dirs(repo_path) -> list[Path]
  check_sparse_checkout_warning(repo_path) -> str | None
  iter_repo_paths(repos_root, repo_list_file) -> generator[Path]
  scan_repos(repos_root, repo_list_file) -> ScanResult
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

YAML_EXTS = (".yaml", ".yml")
HARNESS_DIR_NAME = ".harness"


# ---------------------------------------------------------------------------
# JEXL expression extraction
# ---------------------------------------------------------------------------

def extract_jexl_expressions(text: str):
    """
    Find every top-level <+ ... > Harness/JEXL expression in `text`.

    Harness expressions can nest, e.g.:
        <+ <+pipeline.triggerType> == "MANUAL" ? <+pipeline.variables.x> : <+trigger.x> >

    We track nesting depth using "<+" as +1 and the matching ">" as -1.
    This is a heuristic (JEXL also uses ">" as greater-than), but is good
    enough to recover complete expression bodies for pattern-scanning
    purposes: depth only decrements while > 0, so a bare ">" comparison
    that appears before any "<+" has opened is never mistaken for a close.

    Returns a list of (start_line, end_line, expression_text) tuples,
    1-indexed lines, expression_text including the outer <+ and >.
    """
    results = []
    i = 0
    n = len(text)
    line_starts = [0]
    for idx, ch in enumerate(text):
        if ch == "\n":
            line_starts.append(idx + 1)

    def offset_to_line(offset):
        lo, hi = 0, len(line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_starts[mid] <= offset:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1  # 1-indexed

    while i < n:
        start = text.find("<+", i)
        if start == -1:
            break
        depth = 1
        j = start + 2
        while j < n and depth > 0:
            if text.startswith("<+", j):
                depth += 1
                j += 2
                continue
            if text[j] == ">":
                depth -= 1
                j += 1
                continue
            j += 1
        end = j  # exclusive, just past the closing '>'
        expr = text[start:end]
        results.append((offset_to_line(start), offset_to_line(end - 1), expr))
        i = end if end > start else start + 2
    return results


# ---------------------------------------------------------------------------
# Repo / file discovery
# ---------------------------------------------------------------------------

@dataclass
class JexlOccurrence:
    """One raw JEXL expression found in one file. No rule-evaluation here -
    just where it is and what it says."""
    repo: str
    file: str
    start_line: int
    end_line: int
    expression: str


@dataclass
class ScanResult:
    occurrences: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    scanned_repos: int = 0
    scanned_files: int = 0


def find_harness_dirs(repo_path: Path):
    """Find all .harness directories under repo_path (usually exactly one
    at the repo root, but scan recursively in case of monorepos or
    unusual layouts)."""
    found = []
    for dirpath, dirnames, _filenames in os.walk(repo_path):
        if ".git" in dirnames:
            dirnames.remove(".git")
        if os.path.basename(dirpath) == HARNESS_DIR_NAME:
            found.append(Path(dirpath))
    return found


def check_sparse_checkout_warning(repo_path: Path):
    """
    Best-effort warning: if this repo is a git sparse checkout and its
    sparse-checkout config does not appear to include .harness, warn,
    since cone-mode sparse-checkout excludes dot-directories by default
    unless explicitly added.

    Returns a warning string, or None if not applicable / looks fine.
    """
    git_dir = repo_path / ".git"
    if not git_dir.exists():
        return None

    sparse_file = git_dir / "info" / "sparse-checkout"
    if not sparse_file.exists():
        return None

    try:
        content = sparse_file.read_text(errors="ignore")
    except OSError:
        return None

    if HARNESS_DIR_NAME in content:
        return None

    return (
        f"{repo_path}: sparse-checkout config exists but does not "
        f"appear to explicitly reference '{HARNESS_DIR_NAME}'. If this "
        f"repo is using cone mode, dot-directories are excluded by "
        f"default and .harness/ may have been silently skipped. Verify "
        f"with `git -C {repo_path} sparse-checkout list`, and if needed "
        f"add it with `git -C {repo_path} sparse-checkout add .harness` "
        f"(cone mode) or a `.harness/**` pattern (non-cone mode)."
    )


def iter_repo_paths(repos_root: Optional[str], repo_list_file: Optional[str]):
    seen = set()
    if repos_root:
        root = Path(repos_root)
        if not root.exists():
            yield from ()  # nothing to do; caller can inspect warnings separately
        else:
            candidates = [p for p in root.iterdir() if p.is_dir()]
            looks_like_repo_collection = any(
                (c / ".git").exists() or (c / HARNESS_DIR_NAME).exists()
                for c in candidates
            )
            if looks_like_repo_collection:
                for c in candidates:
                    if c.resolve() not in seen:
                        seen.add(c.resolve())
                        yield c
            else:
                if root.resolve() not in seen:
                    seen.add(root.resolve())
                    yield root

    if repo_list_file:
        with open(repo_list_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                p = Path(line)
                if p.resolve() not in seen:
                    seen.add(p.resolve())
                    yield p


def scan_repos(repos_root: Optional[str], repo_list_file: Optional[str]) -> ScanResult:
    """Walk repos, find .harness YAML files, extract raw JEXL expressions.
    Returns a ScanResult with occurrences (no rule evaluation applied)."""
    result = ScanResult()

    if repos_root and not Path(repos_root).exists():
        result.warnings.append(f"--repos-root {repos_root} does not exist")

    for repo_path in iter_repo_paths(repos_root, repo_list_file):
        if not repo_path.exists():
            result.warnings.append(f"repo path does not exist, skipping: {repo_path}")
            continue

        result.scanned_repos += 1

        sc_warning = check_sparse_checkout_warning(repo_path)
        if sc_warning:
            result.warnings.append(sc_warning)

        harness_dirs = find_harness_dirs(repo_path)
        if not harness_dirs:
            result.warnings.append(
                f"{repo_path}: no '{HARNESS_DIR_NAME}' directory found "
                f"(sparse checkout may have missed it, or this repo has "
                f"no Harness pipelines)"
            )
            continue

        for hdir in harness_dirs:
            for dirpath, _dirnames, filenames in os.walk(hdir):
                for fname in filenames:
                    if not fname.endswith(YAML_EXTS):
                        continue
                    fpath = Path(dirpath) / fname
                    result.scanned_files += 1
                    try:
                        text = fpath.read_text(errors="ignore")
                    except OSError as e:
                        result.warnings.append(f"could not read {fpath}: {e}")
                        continue

                    for start_line, end_line, expr in extract_jexl_expressions(text):
                        result.occurrences.append(JexlOccurrence(
                            repo=str(repo_path),
                            file=str(fpath.relative_to(repo_path)),
                            start_line=start_line,
                            end_line=end_line,
                            expression=expr.strip(),
                        ))

    return result
