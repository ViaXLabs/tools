"""
pipeline_inventory_harness_prep.py

Script to inventory .harness, .github, CODEOWNERS, and other key files/dirs
in a team/repo directory structure and write a CSV report.
"""

from pathlib import Path
import shutil
from utils import write_csv_report, iter_team_repo_files, run_inventory

INVENTORY_TARGETS = [
    (".harness", ".harness", True),
    (".github", ".github", True),
    (".vscode", ".vscode", True),
    ("terraform", "terraform", True),
    (".dockerignore", ".dockerignore", False),
    (".editorconfig", ".editorconfig", False),
    (".gitignore", ".gitignore", False),
    (".pre-commit-config.yaml", ".pre-commit-config.yaml", False),
    ("README.md", "README.md", False),
]
CODEOWNERS_LABEL = "CODEOWNERS"

def extract_harness_info(repo_path: Path, team: str, repo: str):
    data = []
    root = repo_path.parents[1]
    for rel_path, label, is_dir in INVENTORY_TARGETS:
        target_path = repo_path / rel_path
        exists = target_path.is_dir() if is_dir else target_path.is_file()
        data.append({
            "Team Folder": team,
            "Repo Name": repo,
            "Type": "DIR" if is_dir else "FILE",
            "Label": label,
            "Exists": "YES" if exists else "NO",
            "Path": str(target_path.relative_to(root)) if exists else "",
        })
    codeowners_path = repo_path / ".github" / CODEOWNERS_LABEL
    exists = codeowners_path.is_file()
    data.append({
        "Team Folder": team,
        "Repo Name": repo,
        "Type": "FILE",
        "Label": CODEOWNERS_LABEL,
        "Exists": "YES" if exists else "NO",
        "Path": str(codeowners_path.relative_to(root)) if exists else "",
    })
    return data

HEADERS = [
    "Team Folder",
    "Repo Name",
    "Type",
    "Label",
    "Exists",
    "Path"
]

if __name__ == "__main__":
    run_inventory(
        extract_func=extract_harness_info,
        filename_pattern="*",  # Updated from "" to "*"
        headers=HEADERS,
        output_csv="pipeline_inventory_harness.csv",
        description="Inventory .harness, .github, CODEOWNERS, and other key files/dirs in team/repo structure.",
        only_dirs=True
    )

    # Cleanup __pycache__ folder
    pycache_path = Path("__pycache__")
    if pycache_path.exists():
        shutil.rmtree(pycache_path)

    print("✅ Cleanup complete: __pycache__ folder removed.")
    