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

# ------------------------- Helper Functions -------------------------

def expand_tilde(p):
    """
    Expand any '~' at the beginning of a path to the user's HOME directory.

    Args:
        p (str): The input path (possibly starting with '~').

    Returns:
        str: The expanded absolute path.
    """
    return os.path.expanduser(p)

def restore_home(p):
    """
    Restore a path so that if it is under the user's HOME, the HOME directory is replaced with '~'.

    Args:
        p (str): An absolute path.

    Returns:
        str: The path with the HOME directory replaced by '~' if applicable.
    """
    home = os.path.expanduser("~")
    if p.startswith(home):
        return "~" + p[len(home):]
    return p

def join_path(a, b):
    """
    Join two paths ensuring there is exactly one path separator between them.

    Args:
        a (str): Base path.
        b (str): Relative path.

    Returns:
        str: Joined path.
    """
    return os.path.join(a.rstrip(os.sep), b.lstrip(os.sep))

def join_by(delimiter, *args):
    """
    Join array elements into a single string with the given delimiter.

    Args:
        delimiter (str): The delimiter to use.
        *args: Items to join.

    Returns:
        str: Joined string.
    """
    return delimiter.join(args)

def abspath(p):
    """
    Return the absolute path of the given path.

    Args:
        p (str): The path.

    Returns:
        str: The absolute path.
    """
    return os.path.abspath(p)

def get_line_count(fp):
    """
    Count and return the number of lines in the file located at fp.

    Args:
        fp (str): File path.

    Returns:
        int: Number of lines in the file.
    """
    try:
        with open(fp, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0

def get_file_size(fp):
    """
    Get the file size in bytes.

    Args:
        fp (str): File path.

    Returns:
        int: File size in bytes.
    """
    try:
        return os.path.getsize(fp)
    except Exception:
        return 0

def scan_for_git_repos(scan_dir):
    """
    Recursively scan a directory for Git repositories by finding directories
    that contain a ".git" folder.

    Args:
        scan_dir (str): The directory to scan.

    Returns:
        list: A list of repository root directories (parent of ".git").
    """
    repos = []
    for root, dirs, _ in os.walk(scan_dir):
        if ".git" in dirs:
            repos.append(root)
            # Do not recurse further into a found repository.
            dirs.clear()
    return repos

# ------------------------- Main Script Function -------------------------

def generate_fix_script(config, out_file):
    """
    Generate a Bash fix script based on the provided configuration.
    This script checks for missing required directories and files in each repo,
    compares file line counts (and sizes if equal), and writes out a fix script
    to create missing directories and copy missing files.

    Args:
        config (dict): Loaded JSON configuration.
        out_file (str): The filename for the generated fix script.
    """
    # Expand configuration paths (which may contain '~')
    scan_dir = expand_tilde(config["scan_dir"])
    model_repo = expand_tilde(config["model_repo"])
    required_dirs = config.get("required_dirs", [])
    required_files = config.get("required_files", [])

    # Convert input paths to absolute paths for processing.
    scan_dir_abs = abspath(scan_dir)
    model_repo_abs = abspath(model_repo)

    # If an output file already exists, back it up with a timestamp.
    if os.path.exists(out_file):
        ts = time.strftime("%Y%m%d_%H%M%S")
        backup_file = out_file + "." + ts + ".bak"
        print(f"Backing up existing '{restore_home(abspath(out_file))}' → '{restore_home(abspath(backup_file))}'")
        os.rename(out_file, backup_file)

    output_lines = []
    # Add header lines to the output.
    output_lines.append("#!/bin/bash")
    output_lines.append("# Auto-generated fix script — DO NOT EDIT")
    output_lines.append("# scan_dir    : " + restore_home(scan_dir_abs))
    output_lines.append("# model_repo  : " + restore_home(model_repo_abs))
    output_lines.append("# Generated on: " + time.strftime("%Y-%m-%dT%H:%M:%S"))
    output_lines.append("")

    # Scan for Git repositories in the scan directory.
    repos = scan_for_git_repos(scan_dir_abs)
    # Exclude any repository that is under the model repository.
    repos = [r for r in repos if not abspath(r).startswith(model_repo_abs)]
    repos.sort()  # Sort for consistent order.

    # Process each repository.
    for repo in repos:
        repo_abs = abspath(repo)
        present_dirs = []
        missing_dirs = []
        missing_files = []
        file_results = {}  # Maps file name to a result string.

        # Check each required directory.
        for d in required_dirs:
            target_dir = join_path(repo, d)
            if os.path.isdir(target_dir):
                present_dirs.append(d)
            else:
                missing_dirs.append(d)

        # Check each required file.
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

        # Build a commented status block for this repository.
        block_lines = []
        block_lines.append("# ───────────────────────────────────────")
        block_lines.append("# Repo: " + restore_home(repo_abs))
        block_lines.append("#   Directories:")
        # For each required directory, explicitly check if it's present.
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

        # Active fix commands section (only if there is something missing).
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
            # Issue mkdir commands for missing directories (do not copy directory contents).
            if missing_dirs:
                for d in missing_dirs:
                    target_dir = join_path(repo, d)
                    active_commands.append("mkdir -p " + restore_home(os.path.abspath(target_dir)))
            # For missing files, ensure the parent directory exists and then copy the file.
            if missing_files:
                for f in missing_files:
                    target_file = join_path(repo, f)
                    parent = os.path.dirname(target_file)
                    # Only create the parent directory if necessary.
                    if parent != repo:
                        active_commands.append("mkdir -p " + restore_home(os.path.abspath(parent)))
                    active_commands.append("cp " + restore_home(os.path.abspath(join_path(model_repo, f))) + " " + restore_home(os.path.abspath(target_file)))
            active_commands.append("")
        else:
            active_commands.append("# Repo: " + restore_home(repo_abs) + " is fully compliant — no fixes needed. (Files still need to be reviewed.)")
            active_commands.append("")

        output_lines.extend(active_commands)
        output_lines.append('echo "======================================================="')
        output_lines.append("")

    # Write the assembled lines to the output file.
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

    # Generate the fix script.
    generate_fix_script(config, output_file)

    # Optionally run the generated fix script.
    if args.apply:
        print("Running fix script...")
        ret = os.system(f"bash {output_file}")
        sys.exit(ret)


if __name__ == "__main__":
    main()
