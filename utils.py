import os
from pathlib import Path
import csv

def write_csv_report(data, headers, output_dir, csv_file):
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)
    csv_path = output_dir / csv_file
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(data)
    print(f"✅ Writing CSV to: {csv_path.resolve()} with {len(data)} records.")

def iter_team_repo_files(root_dir, filename_pattern="*"):
    root = Path(root_dir)
    for team_path in root.iterdir():
        if not team_path.is_dir():
            continue
        for repo_path in team_path.iterdir():
            if not repo_path.is_dir():
                continue
            for file in repo_path.glob(filename_pattern):
                yield team_path.name, repo_path.name, file

def run_inventory(
    extract_func,
    filename_pattern,
    headers,
    output_csv,
    description,
    only_dirs=False
):
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("root_dir", help="Root directory containing team subdirectories")
    args = parser.parse_args()
    root_dir = Path(args.root_dir)
    if not root_dir.is_dir():
        print(f"Error: The directory '{args.root_dir}' does not exist or is not accessible.")
        return

    data = []
    for team, repo, file_or_dir in iter_team_repo_files(root_dir, filename_pattern):
        if only_dirs and not file_or_dir.is_dir():
            continue
        data.extend(extract_func(file_or_dir, team, repo))
    write_csv_report(data, headers, "output", output_csv)
    print(f"✅ Inventory report saved to output/{output_csv}")