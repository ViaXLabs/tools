import os
import json
import csv
import re
import argparse
import logging
import shutil
from pathlib import Path
from tools.utils import write_csv_report, iter_team_repo_files, load_tool_keywords

def parse_jenkinsfile(path: Path, tool_keywords):
    """Extracts Jenkins pipeline tool usage from a Jenkinsfile."""
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
        stage_blocks = re.findall(r"(stage\s*\(['\"].+?['\"]\)\s*\{.*?\})", content, re.DOTALL)
        stages, step_counts, tool_counts_per_stage, tools_used_per_stage = [], [], [], []
        total_tool_counts = [0] * len(tool_keywords)  # Initialize summary tool counts

        for block in stage_blocks:
            stage_name_match = re.search(r"stage\s*\(['\"](.+?)['\"]\)", block)
            if stage_name_match:
                stages.append(stage_name_match.group(1))
                steps_in_stage = len(re.findall(r"\s*steps\s*{", block))
                step_counts.append(steps_in_stage)
                block_lower = block.lower()
                tool_counts = [len(re.findall(rf"\b{tool.lower()}\b", block_lower)) for tool in tool_keywords]
                tool_counts_per_stage.append(tool_counts)
                tools_used = [tool_keywords[i] for i, count in enumerate(tool_counts) if count > 0]
                tools_used_per_stage.append(", ".join(tools_used))

                # Accumulate tool counts for summary report
                total_tool_counts = [total_tool_counts[i] + tool_counts[i] for i in range(len(tool_counts))]

        summary_tools_used = [tool_keywords[i] for i, count in enumerate(total_tool_counts) if count > 0]
        return stages, step_counts, tool_counts_per_stage, tools_used_per_stage, total_tool_counts, ", ".join(summary_tools_used)

    except Exception as e:
        logging.error(f"Error reading file at {path}. Exception: {e}")
        return [], [], [], [], [0] * len(tool_keywords), ""

def collect_data(root_dir: str, tool_keywords):
    """Collects tool usage data across all repositories."""
    detailed_data = []
    summary_data = []

    for team, repo, jenkinsfile in iter_team_repo_files(root_dir, "Jenkinsfile*"):
        rel_path = f"{repo}/{jenkinsfile.name}"
        stages, step_counts, tool_counts_per_stage, tools_used_per_stage, total_tool_counts, summary_tools_used = parse_jenkinsfile(jenkinsfile, tool_keywords)

        # Detailed report (by stage)
        for stage, step_count, tool_counts, tools_used in zip(stages, step_counts, tool_counts_per_stage, tools_used_per_stage):
            row = {
                "Team Folder": team,
                "Repo Name": repo,
                "Jenkinsfile Name": jenkinsfile.name,
                "Stage Name": stage,
                "Step Count": step_count,
                "Full Path": rel_path,
                "Tools Used": tools_used,
                **{tool: count for tool, count in zip(tool_keywords, tool_counts)}
            }
            detailed_data.append(row)

        # Summary report (aggregated at Jenkinsfile level)
        summary_row = {
            "Team Folder": team,
            "Repo Name": repo,
            "Jenkinsfile Name": jenkinsfile.name,
            "Full Path": rel_path,
            "Tools Used": summary_tools_used,
            **{tool: count for tool, count in zip(tool_keywords, total_tool_counts)}
        }
        summary_data.append(summary_row)

    return detailed_data, summary_data

def main():
    parser = argparse.ArgumentParser(description="Generate Jenkins pipeline tool usage reports.")
    parser.add_argument("root_dir", help="Path to the repos directory")
    parser.add_argument("--tool_file", default="tool_keywords.json", help="Path to the JSON file containing tool keywords")
    parser.add_argument("--log-level", default="WARNING", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], help="Set the logging level")
    args = parser.parse_args()
    Path("output").mkdir(exist_ok=True)

    logging.basicConfig(
        filename="output/error_log.txt",
        level=getattr(logging, args.log_level.upper(), logging.WARNING)
    )

    tool_keywords = load_tool_keywords(args.tool_file)  # Load tools dynamically
    detailed_data, summary_data = collect_data(args.root_dir, tool_keywords)

    headers = ["Team Folder", "Repo Name", "Jenkinsfile Name", "Stage Name", "Step Count", "Full Path", "Tools Used"] + tool_keywords
    summary_headers = ["Team Folder", "Repo Name", "Jenkinsfile Name", "Full Path", "Tools Used"] + tool_keywords

    write_csv_report(detailed_data, headers, "output", "jenkins_pipeline_report_by_stage.csv")
    write_csv_report(summary_data, summary_headers, "output", "jenkins_pipeline_summary_report.csv")

    # Cleanup __pycache__ folder
    pycache_path = Path("__pycache__")
    if pycache_path.exists():
        shutil.rmtree(pycache_path)

    print("✅ Cleanup complete: __pycache__ folder removed.")
    print("✅ Reports saved to output/jenkins_pipeline_report_by_stage.csv & output/jenkins_pipeline_summary_report.csv")
    print("⚠️ Any errors encountered during processing are logged in output/error_log.txt")

if __name__ == "__main__":
    main()
