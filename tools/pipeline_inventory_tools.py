# -------------------------------------------------------------------------------
# pipeline_inventory_tools.py
# -------------------------------------------------------------------------------

import os
import csv
import re
import argparse
import logging
import shutil
from pathlib import Path
from tools.utils import write_csv_report, iter_team_repo_files

TOOL_KEYWORDS = [
    "artillery",
    "ansible",
    "ansible-lint",
    "alembic",
    "aws",
    "aws-cli",
    "awscli",
    "curl",
    "cypress",
    "docker-compose",
    "docker build",
    "docker push",
    "flake8",
    "git",
    "gradle",
    "gradle build",
    "gradle publish",
    "gradle test",
    "gradle wrapper",
    "gradle assemble",
    "gradlew",
    "java",
    "junit",
    "kubernetes",
    "kubernetes apply",
    "kubernetes create",
    "kubernetes delete",
    "jq",
    "make install",
    "make generate",
    "molecule",
    "newrelic",
    "nexus-iq",
    "nexus iq",
    "nexusiq",
    "node",
    "newrelic",
    "npm",
    "prisma-cloud",
    "prismacloudpublish",
    "python",
    "python3",
    "rvm.rake",
    "ruby",
    "rubocop",
    "snyk",
    "sonar",
    "sonar-scanner",
    "splunk",
    "tennable",
    "terraform apply",
    "terraform plan",
    "twistlock",
    "twistlock publish",
    "twistlock scan",
    "wget",
    "yarn"
]
# (Your existing list remains unchanged)
TOOL_KEYWORDS_LOWER = [tool.lower() for tool in TOOL_KEYWORDS]

def is_git_repo(path: Path):
    """Check if the directory contains a .git folder to confirm it’s a Git repository."""
    return (path / ".git").exists()

def iter_team_repo_files(root_dir, filename_pattern="*"):
    """Iterate through team repo directories, ensuring they are valid Git repositories."""
    root = Path(root_dir)
    for team_path in root.iterdir():
        if not team_path.is_dir():
            continue
        for repo_path in team_path.iterdir():
            if not repo_path.is_dir() or not is_git_repo(repo_path):  # Git repo check added
                continue
            for file in repo_path.rglob(filename_pattern):  # Search in nested folders
                yield team_path.name, repo_path.name, file

def parse_jenkinsfile(path: Path):
    """Extracts Jenkins pipeline tool usage from a Jenkinsfile."""
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
        stage_blocks = re.findall(r"(stage\s*\(['\"].+?['\"]\)\s*\{.*?\})", content, re.DOTALL)
        stages, step_counts, tool_counts_per_stage, tools_used_per_stage = [], [], [], []

        for block in stage_blocks:
            stage_name_match = re.search(r"stage\s*\(['\"](.+?)['\"]\)", block)
            if stage_name_match:
                stages.append(stage_name_match.group(1))
                steps_in_stage = len(re.findall(r"\s*steps\s*{", block))
                step_counts.append(steps_in_stage)
                block_lower = block.lower()
                tool_counts = [len(re.findall(rf"\b{tool}\b", block_lower)) for tool in TOOL_KEYWORDS_LOWER]
                tool_counts_per_stage.append(tool_counts)
                tools_used = [TOOL_KEYWORDS[i] for i, count in enumerate(tool_counts) if count > 0]
                tools_used_per_stage.append(", ".join(tools_used))

        return stages, step_counts, tool_counts_per_stage, tools_used_per_stage

    except Exception as e:
        logging.error(f"Error reading file at {path}. Exception: {e}")
        return [], [], [], []

def collect_data(root_dir: str):
    """Collects tool usage data across all repositories."""
    data = []

    for team, repo, jenkinsfile in iter_team_repo_files(root_dir, "Jenkinsfile*"):
        rel_path = f"{repo}/{jenkinsfile.name}"
        stages, step_counts, tool_counts_per_stage, tools_used_per_stage = parse_jenkinsfile(jenkinsfile)

        for stage, step_count, tool_counts, tools_used in zip(stages, step_counts, tool_counts_per_stage, tools_used_per_stage):
            row = {
                "Team Folder": team,
                "Repo Name": repo,
                "Jenkinsfile Name": jenkinsfile.name,
                "Stage Name": stage,
                "Step Count": step_count,
                "Full Path": rel_path,
                "Tools Used": tools_used,
                **{tool: count for tool, count in zip(TOOL_KEYWORDS, tool_counts)}
            }
            data.append(row)

    return data

def main():
    parser = argparse.ArgumentParser(description="Generate Jenkins pipeline tool usage reports.")
    parser.add_argument("root_dir", help="Path to the repos directory")
    parser.add_argument("--log-level", default="WARNING", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], help="Set the logging level")
    args = parser.parse_args()
    Path("output").mkdir(exist_ok=True)

    logging.basicConfig(
        filename="output/error_log.txt",
        level=getattr(logging, args.log_level.upper(), logging.WARNING)
    )

    data = collect_data(args.root_dir)
    headers = ["Team Folder", "Repo Name", "Jenkinsfile Name", "Stage Name", "Step Count", "Full Path", "Tools Used"] + TOOL_KEYWORDS
    write_csv_report(data, headers, "output", "jenkins_pipeline_report_by_stage.csv")

    # Cleanup __pycache__ folder
    pycache_path = Path("__pycache__")
    if pycache_path.exists():
        shutil.rmtree(pycache_path)

    print("✅ Cleanup complete: __pycache__ folder removed.")
    print("✅ Pipeline reports saved to output/jenkins_pipeline_report_by_stage.csv")
    print("⚠️ Any errors encountered during processing are logged in output/error_log.txt")

if __name__ == "__main__":
    main()
