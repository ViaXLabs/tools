# -----------------------------------------------------------------------------
# Jenkinsfile Inventory Script
#
# Usage:
#   python jenkinsfile_inventroy.py <root_dir>
#
# Arguments:
#   <root_dir>   Path to the root directory containing team folders and repos.
#
# Description:
#   This script scans all Jenkinsfiles in the given directory structure,
#   extracts pipeline stages, step counts, and tool/command usage,
#   and writes a CSV report (jenkins_pipeline_report_by_stage.csv).
#
# Output:
#   - jenkins_pipeline_report_by_stage.csv: CSV file with pipeline and tool usage details.
#   - error_log.txt: Log file for any file read errors.
# -----------------------------------------------------------------------------

import os
import csv
import re
import argparse
import logging
from pathlib import Path
from utils import write_csv_report, iter_team_repo_files

TOOL_KEYWORDS = [
    "docker build", "docker push", "flake8", "gradlew", "newrelic", "nexus iq", "nexusiq",
    "npm", "prisma-cloud", "prismacloudpublish", "python", "python3", "rvm.rake",
    "sonar-scanner", "splunk", "tennable", "terraform apply", "twistlock"
]
TOOL_KEYWORDS_LOWER = [tool.lower() for tool in TOOL_KEYWORDS]

def parse_jenkinsfile(path: Path):
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

def collect_file_summary(root_dir: str):
    summary = []
    for team, repo, jenkinsfile in iter_team_repo_files(root_dir, "Jenkinsfile*"):
        rel_path = f"{repo}/{jenkinsfile.name}"
        stages, step_counts, tool_counts_per_stage, tools_used_per_stage = parse_jenkinsfile(jenkinsfile)
        total_steps = sum(step_counts)
        total_tool_counts = [sum(tool_counts[i] for tool_counts in tool_counts_per_stage) for i in range(len(TOOL_KEYWORDS))]
        tools_used_set = {tool for tools_used in tools_used_per_stage for tool in re.split(r", |\n", tools_used) if tool}
        tools_used_str = ", ".join(sorted(tools_used_set))
        row = {
            "Team Folder": team,
            "Repo Name": repo,
            "Jenkinsfile Name": jenkinsfile.name,
            "Total Step Count": total_steps,
            "Full Path": rel_path,
            "Tools Used": tools_used_str,
            **{tool: count for tool, count in zip(TOOL_KEYWORDS, total_tool_counts)}
        }
        summary.append(row)
    return summary

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

    summary = collect_file_summary(args.root_dir)
    summary_headers = ["Team Folder", "Repo Name", "Jenkinsfile Name", "Total Step Count", "Full Path", "Tools Used"] + TOOL_KEYWORDS
    write_csv_report(summary, summary_headers, "output", "jenkins_pipeline_report_by_jenkinsfile.csv")

    print("✅ Pipeline reports saved to output/jenkins_pipeline_report_by_stage.csv and output/jenkins_pipeline_report_by_jenkinsfile.csv")
    print("⚠️ Any errors encountered during processing are logged in output/error_log.txt")

if __name__ == "__main__":
    main()