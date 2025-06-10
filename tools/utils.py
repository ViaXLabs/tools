import os
import json
from pathlib import Path
import csv
import shutil

def load_tool_keywords(tool_file):
    """Load tool keywords dynamically from a JSON file."""
    try:
        with open(tool_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("tools", [])
    except Exception as e:
        print(f"⚠️ Error loading tool keywords from {tool_file}: {e}")
        return []

def write_csv_report(data, headers, output_dir, csv_file):
    """Writes inventory data to a CSV file."""
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)
    csv_path = output_dir / csv_file

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(data)

    print(f"✅ Writing CSV to: {csv_path.resolve()} with {len(data)} records.")

def is_git_repo(path: Path):
    """Check if the directory contains a .git folder to confirm it’s a Git repository."""
    return (path / ".git").exists()

def iter_team_repo_files(root_dir, filename_pattern="*"):
    """Iterates over repositories, ensuring they are valid Git repositories."""
    root = Path(root_dir)
    for team_path in root.iterdir():
        if not team_path.is_dir():
            continue
        for repo_path in team_path.iterdir():
            if not repo_path.is_dir() or not is_git_repo(repo_path):
                continue
            for file in repo_path.rglob(filename_pattern):  # Search in nested folders
                yield team_path.name, repo_path.name, file
