"""
pipeline_inventory_docker.py

Script to inventory Dockerfiles and docker-compose files in a team/repo
directory structure and write a CSV report.
"""

from pathlib import Path
import shutil
from tools.utils import write_csv_report, iter_team_repo_files, run_inventory

def extract_from_command(file_path: Path, max_lines: int = 100) -> str:
    """
    Reads a file and returns the first line containing 'FROM' (case sensitive).
    Limits the number of lines read to `max_lines` for efficiency.
    Returns an empty string if not found or file does not exist.
    """
    try:
        with file_path.open("r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= max_lines:
                    break
                if line.strip().startswith("FROM ") and len(line.strip().split()) > 1:
                    return line.strip()
    except (FileNotFoundError, PermissionError, AttributeError):
        pass
    return ""

def extract_docker_info(repo_path: Path, team: str, repo: str):
    """
    For a given repo, find all Dockerfiles and docker-compose files,
    and return a list of dicts for CSV output.
    """
    data = []
    root = repo_path.parents[1]
    dockerfiles = list(repo_path.glob("Dockerfile*"))
    compose_files = [f for ext in ['yml', 'yaml'] for f in repo_path.glob(f'docker-compose*.{ext}')]
    compose_file = compose_files[0] if compose_files else None
    compose_file_name = compose_file.name if compose_file else ""
    compose_file_path = str(compose_file.relative_to(root)) if compose_file else ""
    compose_from = extract_from_command(compose_file) if compose_file else ""

    if not dockerfiles:
        data.append({
            "Team Folder": team,
            "Repo Name": repo,
            "Dockerfile Path": "",
            "Dockerfile Name": "",
            "Dockerfile FROM": "",
            "Compose File Path": compose_file_path,
            "Compose File Name": compose_file_name,
            "Compose FROM": compose_from
        })
    else:
        for dockerfile in dockerfiles:
            dockerfile_from = extract_from_command(dockerfile)
            data.append({
                "Team Folder": team,
                "Repo Name": repo,
                "Dockerfile Path": str(dockerfile.parent.relative_to(root)),
                "Dockerfile Name": dockerfile.name,
                "Dockerfile FROM": dockerfile_from,
                "Compose File Path": compose_file_path,
                "Compose File Name": compose_file_name,
                "Compose FROM": compose_from
            })
    return data

HEADERS = [
    "Team Folder",
    "Repo Name",
    "Dockerfile Path",
    "Dockerfile Name",
    "Dockerfile FROM",
    "Compose File Path",
    "Compose File Name",
    "Compose FROM"
]

if __name__ == "__main__":
    run_inventory(
        extract_func=extract_docker_info,
        filename_pattern="",
        headers=HEADERS,
        output_csv="pipeline_inventory_docker.csv",
        description="Inventory Dockerfiles and Compose files in team/repo structure.",
        only_dirs=True
    )

    # Cleanup __pycache__ folder
    pycache_path = Path("__pycache__")
    if pycache_path.exists():
        shutil.rmtree(pycache_path)

    print("✅ Cleanup complete: __pycache__ folder removed.")
