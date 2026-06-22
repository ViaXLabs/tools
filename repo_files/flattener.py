"""
_scanner/flattener.py — Stage 1: flatten a repo into one text file.
"""

from datetime import datetime
from pathlib import Path

try:
    import pathspec
    HAS_PATHSPEC = True
except ImportError:
    HAS_PATHSPEC = False

from _scanner.warnings import FILE_FOOTER

FILE_MARKER = "=" * 60

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".obj", ".o",
    ".pyc", ".pyo", ".pyd",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv",
    ".ttf", ".otf", ".woff", ".woff2",
    ".db", ".sqlite", ".sqlite3", ".svg",
}

SKIP_DIRS = {
    ".git", ".hg", ".svn",
    "node_modules", "__pycache__", ".tox",
    ".venv", "venv", "env",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "dist", "build",
}

# Note: ".env" removed from SKIP_DIRS — it's a file not a dir.
# .env files are handled by gitignore parsing. Use --include-gitignored to scan them.

SKIP_FILES = {".DS_Store", "Thumbs.db", "desktop.ini"}


def _load_spec(root: Path):
    if not HAS_PATHSPEC:
        print("  [WARN] pip install pathspec  for .gitignore support")
        return None
    patterns = []
    for gi in root.rglob(".gitignore"):
        try:
            patterns.extend(gi.read_text(encoding="utf-8", errors="ignore").splitlines())
        except OSError:
            pass
    return pathspec.PathSpec.from_lines("gitwildmatch", patterns) if patterns else None


def _skip(path: Path, root: Path, spec, max_bytes: int):
    for part in path.parts:
        if part in SKIP_DIRS:
            return True, f"dir:{part}"
    if path.name in SKIP_FILES:
        return True, "skip-filename"
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True, f"binary{path.suffix}"
    try:
        if path.stat().st_size > max_bytes:
            return True, f"too-large"
    except OSError:
        pass
    if spec:
        if spec.match_file(str(path.relative_to(root))):
            return True, ".gitignore"
    return False, ""


def _tree(root: Path, spec, max_bytes: int, prefix: str = "") -> list[str]:
    lines = []
    try:
        entries = sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        return lines
    visible = [e for e in entries if not _skip(e, root, spec, max_bytes)[0]]
    for i, entry in enumerate(visible):
        conn = "└── " if i == len(visible) - 1 else "├── "
        lines.append(f"{prefix}{conn}{entry.name}")
        if entry.is_dir():
            ext = "    " if i == len(visible) - 1 else "│   "
            lines.extend(_tree(entry, spec, max_bytes, prefix + ext))
    return lines


def run(root: Path, out_path: Path, max_file_kb: int = 500, encoding: str = "utf-8", include_gitignored: bool = False) -> dict:
    root = root.resolve()
    max_bytes = max_file_kb * 1024
    spec = None if include_gitignored else _load_spec(root)

    stats = {"included": 0, "skipped": 0, "reasons": {}, "gitignore_skipped": []}
    sections = [
        FILE_MARKER,
        f"REPO SCAN — {root.name}",
        f"Generated : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Root      : {root}",
        FILE_MARKER, "",
        "DIRECTORY TREE",
        FILE_MARKER,
        root.name + "/",
    ]
    sections += _tree(root, spec, max_bytes)
    sections += ["", ""]

    # We'll insert the gitignore warning after collecting (placeholder replaced below)
    gitignore_warning_placeholder = "<<<GITIGNORE_WARNING>>>"
    sections.append(gitignore_warning_placeholder)
    sections += ["", ""]

    for file_path in sorted(root.rglob("*")):
        if not file_path.is_file():
            continue
        skip, reason = _skip(file_path, root, spec, max_bytes)
        if skip:
            stats["skipped"] += 1
            stats["reasons"][reason] = stats["reasons"].get(reason, 0) + 1
            if reason == ".gitignore":
                stats["gitignore_skipped"].append(str(file_path.relative_to(root)))
            continue
        rel = file_path.relative_to(root)
        try:
            content = file_path.read_text(encoding=encoding, errors="replace")
        except OSError as e:
            content = f"[ERROR: {e}]"
        sections += [FILE_MARKER, f"FILE: {rel}", FILE_MARKER, content, ""]
        stats["included"] += 1

    sections += [
        FILE_MARKER,
        f"END — {stats['included']} files included, {stats['skipped']} skipped",
        FILE_MARKER,
    ]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(sections) + FILE_FOOTER, encoding="utf-8")
    stats["spec_loaded"] = spec is not None
    return stats
