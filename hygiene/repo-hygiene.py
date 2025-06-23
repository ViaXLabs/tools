#!/usr/bin/env python3
"""
#!/bin/bash
# repo-hygiene.sh
#
# This script recursively scans a directory tree for Git repositories,
# compares each repository against a "model" (gold-standard) repository, and
# generates a self-contained fix script to update any missing files (which are copied)
# and directories (which are created) based on the configuration provided in a JSON file.
#
# All settings come from a JSON configuration file.
#
# Dependencies:
#   - GNU Bash (compatible with Bash 3.2)
#   - jq (for JSON parsing)
#
# If jq is not installed, the script displays installation instructions and exits.
"""

import argparse
import json
import os
import stat
import sys
import time
from pathlib import Path

def expand_tilde(p):
    """
    Expand a path beginning with '~' to the full HOME directory.
    """
    return os.path.expanduser(p)

def restore_home(p):
    """
    For output, if the path is under HOME, return it with a leading '~'.
    """
    home = os.path.expanduser("~")
    if p.startswith(home):
        return "~" + p[len(home):]
    return p

def join_path(a, b):
    """
    Join two paths ensuring a single path separator.
    """
    return os.path.join(a.rstrip(os.sep), b.lstrip(os.sep))

def join_by(delimiter, *args):
    """
    Join array elements with the given delimiter.
    """
    return delimiter.join(args)

def abspath(p):
    """
    Return the absolute path.
    """
    return os.path.abspath(p)

def get_line_count(fp):
    """
    Return the number of lines in the given file.
    """
    try:
        with open(fp, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0

def get_file_size(fp):
    """
    Return the size of the file in bytes.
    """
    try:
        return os.path.getsize(fp)
    except Exception:
        return 0

def scan_for_git_repos(scan_dir):
    """
    Recursively scan 'scan_dir' for directories containing a '.git' folder.
    Returns a list of repository root directories.
    """
    repos = []
    for root, dirs, files in os.walk(scan_dir):
        if ".git" in dirs:
            repos.append(root)
            # Skip subdirectories within a repository.
            dirs.clear()
    return repos

def generate_fix_script(config, out_file):
    """
    Generate a Bash fix script based on the configuration.
    """
    # Expand configuration paths (which might contain '~')
    scan_dir = expand_tilde(config["scan_dir"])
    model_repo = expand_tilde(config["model_repo"])
    required_dirs = config.get("required_dirs", [])
    required_files = config.get("required_files", [])

    # Convert to absolute paths for processing.
    scan_dir_abs = abspath(scan_dir)
    model_repo_abs = abspath(model_repo)

    # Before generating a new fix script, back up any existing one.
    if os.path.exists(out_file):
        ts = time.strftime("%Y%m%d_%H%M%S")
        backup_file = out_file + "." + ts + ".bak"
        print(f"Backing up existing '{restore_home(os.path.abspath(out_file))}' → '{restore_home(os.path.abspath(backup_file))}'")
        os.rename(out_file, backup_file)

    output_lines = []
    # Header (restoring HOME paths in output)
    output_lines.append("#!/bin/bash")
    output_lines.append("# Auto-generated fix script — DO NOT EDIT")
    output_lines.append("# scan_dir    : " + restore_home(scan_dir_abs))
    output_lines.append("# model_repo  : " + restore_home(model_repo_abs))
    output_lines.append("# Generated on: " + time.strftime("%Y-%m-%dT%H:%M:%S"))
    output_lines.append("")

    # Scan for Git repositories.
    repos = scan_for_git_repos(scan_dir_abs)
    # Exclude repositories that are part of the model repository.
    repos = [r for r in repos if not abspath(r).startswith(model_repo_abs)]
    repos.sort()

    for repo in repos:
        repo_abs = abspath(repo)
        present_dirs = []
        missing_dirs = []
        missing_files = []
        file_results = {}  # dict with file: result string

        # Check required directories.
        for d in required_dirs:
            target_dir = join_path(repo, d)
            if os.path.isdir(target_dir):
                present_dirs.append(d)
            else:
                missing_dirs.append(d)

        # Check required files.
        for f in required_files:
            target_file = join_path(repo, f)
            model_file = join_path(model_repo, f)
            if os.path.isfile(target_file):
                rl = get_line_count(target_file)
                ml = get_line_count(model_file) if os.path.isfile(model_file) else 0
                if rl == ml:
                    rs = get_file_size(target_file)
                    ms = get_file_size(model_file)
                    file_results[f] = f"{ml}:{rl}:{ms}:{rs}"
                else:
                    file_results[f] = f"{ml}:{rl}"
            else:
                file_results[f] = ""
                missing_files.append(f)

        # Build a commented status block.
        block_lines = []
        block_lines.append("# ───────────────────────────────────────")
        block_lines.append("# Repo: " + restore_home(repo_abs))
        block_lines.append("#   Directories:")
        for d in required_dirs:
            if d in present_dirs:
                block_lines.append("#     + DIR " + d + " exists")
            else:
                block_lines.append("#     – DIR " + d + " missing")
        block_lines.append("#   Files:")
        for f in required_files:
            result = file_results[f]
            if result:
                parts = result.split(":")
                if len(parts) == 4:
                    ml, rl, ms, rs = parts
                    block_lines.append(f"#     + FILE {f} exists (model lines: {ml} vs scanned file: {rl}; model size: {ms} bytes vs scanned file: {rs} bytes)")
                else:
                    ml, rl = parts
                    block_lines.append(f"#     + FILE {f} exists (model lines: {ml} vs scanned file: {rl})")
            else:
                block_lines.append("#     – FILE " + f + " missing")
        block_lines.append("#")
        output_lines.extend(block_lines)

        # Active fix commands.
        active_commands = []
        if missing_dirs or missing_files:
            active_commands.append(f'echo ">> Updating {restore_home(repo_abs)}"')
            if missing_dirs:
                active_commands.append('echo "Missing dirs:"')
                for d in missing_dirs:
                    active_commands.append(f'echo "  {d}"')
            if missing_files:
                active_commands.append('echo "Missing files:"')
                for f in missing_files:
                    active_commands.append(f'echo "  {f}"')
            active_commands.append("")
            if missing_dirs:
                for d in missing_dirs:
                    target_dir = join_path(repo, d)
                    # Only create the missing directory.
                    active_commands.append("mkdir -p " + restore_home(os.path.abspath(target_dir)))
            if missing_files:
                for f in missing_files:
                    target_file = join_path(repo, f)
                    parent = os.path.dirname(target_file)
                    if parent != repo:
                        active_commands.append("mkdir -p " + restore_home(os.path.abspath(parent)))
                    active_commands.append("cp " + restore_home(os.path.abspath(join_path(model_repo, f))) + " " + restore_home(os.path.abspath(target_file)))
            active_commands.append("")
        else:
            active_commands.append("# Repo: " + restore_home(repo_abs) + " is fully compliant — no fixes needed. However, files still need to be reviewed.")
            active_commands.append("")
        output_lines.extend(active_commands)
        output_lines.append('echo "======================================================="')
        output_lines.append("")

    # Write out the fix script.
    with open(out_file, "w") as outf:
        outf.write("\n".join(output_lines))

    # Make the output file executable.
    st = os.stat(out_file)
    os.chmod(out_file, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print("Fix-script generated at:", restore_home(os.path.abspath(out_file)))

def main():
    parser = argparse.ArgumentParser(description="Repo Hygiene Fix-Script Generator")
    parser.add_argument("-c", "--config", required=True, help="Path to JSON configuration file")
    parser.add_argument("-o", "--output", help="Output fix script file (default: repo-hygiene-fix.sh)")
    parser.add_argument("--apply", action="store_true", help="Run the generated fix script immediately")
    args = parser.parse_args()

    config_file = args.config
    if not os.path.exists(config_file):
        print(f"Error: config file {config_file} not found.", file=sys.stderr)
        sys.exit(1)

    with open(config_file, "r") as cf:
        config = json.load(cf)

    output_file = args.output if args.output else "repo-hygiene-fix.sh"

    generate_fix_script(config, output_file)

    if args.apply:
        print("Running fix script...")
        ret = os.system(f"bash {output_file}")
        sys.exit(ret)

if __name__ == "__main__":
    main()
