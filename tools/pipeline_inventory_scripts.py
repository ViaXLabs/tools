"""
pipeline_inventory_scripts.py

Script to inventory Jenkinsfiles in a team/repo directory structure,
extracting docker agent info, image variables, nexus info, and shell scripts per stage,
and generating a summary CSV in the output folder.
"""

import re
import shutil
from pathlib import Path
from utils import write_csv_report, iter_team_repo_files, run_inventory

def extract_docker_agent_info(jenkinsfile_path: Path, team: str, repo: str):
    results = []
    try:
        content = jenkinsfile_path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"Error reading {jenkinsfile_path}: {e}")
        return results

    stage_blocks = re.findall(
        r"(stage\s*\(['\"](.+?)['\"]\)\s*\{([\s\S]*?)^\s*\})",
        content, re.DOTALL | re.MULTILINE
    )
    for block, stage_name in [(b[0], b[1]) for b in stage_blocks]:
        agent_match = re.search(
            r"agent\s*\{\s*docker\s*\{\s*image\s+['\"]?([\w\-/\.:${}\s]+)['\"]?.*?\}",
            block
        )
        image = agent_match.group(1) if agent_match else ""
        image_var_value = ""
        var_name = ""
        if image:
            var_match = re.match(
                r"\$\{?([A-Za-z0-9_]+(?:[\.\+\-][A-Za-z0-9_]+)*)\}?", image
            )
            if var_match:
                var_name = var_match.group(1)
        assign_match = None
        if var_name:
            assign_match = re.search(
                rf"{var_name}\s*[:=]\s*['\"]?([^\s'\"]+)",
                content
            )
            if assign_match:
                image_var_value = assign_match.group(1)
        nexus_match = re.search(
            r"(nexus\s*:\s*['\"]?dockerfile['\"]?\s*:\s*['\"]?tag['\"]?)",
            block,
            re.IGNORECASE
        )
        script_blocks = re.findall(
            r"script\s*\{([\s\S]*?)\}|sh(?:\s+script:)?\s*(['\"`]{1,3})([\s\S]*?)\2",
            block
        )
        flat_blocks = []
        for b in script_blocks:
            val = (b[2] if isinstance(b, tuple) else b).strip()
            if val:
                flat_blocks.append(val)
        results.append({
            "Team": team,
            "Repo": repo,
            "Jenkinsfile": jenkinsfile_path.name,
            "Stage": stage_name,
            "Agent Image": image,
            "Agent Image Variable Value": image_var_value,
            "Nexus Info": nexus_match.group(1) if nexus_match else "",
            "Shell Scripts": "\n---\n".join(flat_blocks) if flat_blocks else ""
        })
    return results

HEADERS = [
    "Team",
    "Repo",
    "Jenkinsfile",
    "Stage",
    "Agent Image",
    "Agent Image Variable Value",
    "Nexus Info",
    "Shell Scripts"
]

if __name__ == "__main__":
    run_inventory(
        extract_func=extract_docker_agent_info,
        filename_pattern="Jenkinsfile*",
        headers=HEADERS,
        output_csv="pipeline_inventory_scripts.csv",
        description="Inventory Jenkinsfile pipeline scripts and docker agent info."
    )

    # Cleanup __pycache__ folder
    pycache_path = Path("__pycache__")
    if pycache_path.exists():
        shutil.rmtree(pycache_path)

    print("✅ Cleanup complete: __pycache__ folder removed.")