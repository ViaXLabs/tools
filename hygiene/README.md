# Repo Hygiene Fix-Script Generator

This Python script scans a directory tree for Git repositories, compares each repository with a “model” (gold‑standard) repository, and generates a Bash fix script that you can run to create any missing directories and copy any missing files. Missing files are copied from the model repository and missing directories are created (without copying their contents). The generated script displays detailed status blocks and active fix commands.

- [Repo Hygiene Fix-Script Generator](#repo-hygiene-fix-script-generator)
  - [Features](#features)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Configuration](#configuration)
  - [Usage](#usage)
  - [Example Output](#example-output)
    - [Generated Fix Script (repo-hygiene-fix.sh – excerpt):](#generated-fix-script-repo-hygiene-fixsh--excerpt)
    - [Generated Fix Commands (if there were missing items):](#generated-fix-commands-if-there-were-missing-items)
    - [Execution](#execution)
  - [How It Works](#how-it-works)

## Features

- **Configuration via JSON:**
  Specify the directory to scan (e.g., `"scan_dir": "~/repos"`), a model repository (e.g., `"model_repo": "~/model-repo"`), the output fix script name (default: `"repo-hygiene-fix.sh"`), and lists of required directories and files.

- **Tilde Handling:**
  Paths starting with `~` in the configuration are expanded to the full HOME directory for processing. In the generated fix script, any path under HOME is restored to show a leading `~`.

- **Status Blocks:**
  For each Git repository, the generated fix script includes a commented status block that indicates:

  - Which required directories exist (or are missing).
  - Which required files exist, along with a comparison of line counts. If the line counts match, the file sizes (in bytes) are also reported.

- **Active Fix Commands:**
  If any required directories or files are missing:

  - For missing directories: only a `mkdir -p` command is provided.
  - For missing files: the script ensures that the parent directory exists and then copies the file from the model repository.
  - Missing items are echoed one per line (and the header "Missing dirs:" and "Missing files:" are only shown if there are missing items).

- **Divider Lines:**
  Each repository block in the fix script is separated by a divider line of "=" characters for clarity.

- **Backup of Previous Output:**
  If a previous output file exists, it is backed up with a timestamp before generating a new fix script.

- **Optional Immediate Execution:**
  Using the `--apply` flag when running the Python script will automatically execute the generated Bash fix script.

- **Bash v3 Compatibility:**
  The generated fix script is compatible with Bash 3.2.

## Prerequisites

- **Python 3**
- **jq** (if you intend to run the original Bash version; not needed for the Python script)
- **GNU Bash 3+** for running the generated fix script

## Installation

1. Download or clone the repository containing `repo_hygiene.py`.
2. Make the script executable (optional):
   ```bash
   chmod +x repo_hygiene.py
   ```

## Configuration

Create a JSON configuration file (e.g., `config.json`) in the same directory. For example:

```json
{
  "scan_dir": "~/repos",
  "model_repo": "~/model-repo",
  "output_file": "repo-hygiene-fix.sh",
  "required_dirs": [".vscode", ".github", "harness"],
  "required_files": [".gitignore", "pre-commit.yaml", ".vscode/extensions.json"]
}
```

- **scan_dir:** The directory to scan (you can use a tilde, e.g., `"~/repos"`).
- **model_repo:** The path to your gold‑standard repository (e.g., `"~/model-repo"`).
- **output_file:** The filename for the generated Bash fix script.
- **required_dirs:** A list of directory names that each repository must have.
- **required_files:** A list of file paths (including dot‑files) that each repository must have.

## Usage

Run the Python script by specifying your config file. For example:

```bash
python repo_hygiene.py -c config.json
```

This will generate a Bash script named `repo-hygiene-fix.sh` (by default) that you can inspect.

To immediately run the generated fix script, use the `--apply` flag:

```bash
python repo_hygiene.py -c config.json --apply
```

## Example Output

### Generated Fix Script (repo-hygiene-fix.sh – excerpt):

```bash
#!/bin/bash
# Auto-generated fix script — DO NOT EDIT
# scan_dir    : ~/repos
# model_repo  : ~/model-repo
# Generated on: 2023-11-26T23:45:10

# ───────────────────────────────────────
# Repo: ~/repos/Team1/repoA
#   Directories:
#     + DIR .vscode exists
#     – DIR .github missing
#     – DIR harness missing
#   Files:
#     + FILE .gitignore exists (model lines: 15 vs scanned file: 15; model size: 1024 bytes vs scanned file: 1200 bytes)
#     – FILE pre-commit.yaml missing
#     + FILE .vscode/extensions.json exists (model lines: 10 vs scanned file: 10; model size: 512 bytes vs scanned file: 512 bytes)
#
echo "======================================================="
```

### Generated Fix Commands (if there were missing items):

```bash
echo ">> Updating ~/repos/Team1/repoA"
echo "Missing dirs:"
echo "  .github"
echo "  harness"
echo "Missing files:"
echo "  pre-commit.yaml"

mkdir -p ~/repos/Team1/repoA/.github
mkdir -p ~/repos/Team1/repoA/harness
mkdir -p ~/repos/Team1/repoA  # (if needed for parent directory of a file)
cp ~/model-repo/pre-commit.yaml ~/repos/Team1/repoA/pre-commit.yaml

echo "======================================================="
```

### Execution

After generating the fix script, if you ran with the `--apply` flag, the script will be executed immediately and missing files/directories will be created/copied.

## How It Works

1. **Dependency & Config Handling:**
   The Python script uses `argparse` to parse command-line arguments and `json` to load the configuration file. It expands paths that use `~` into absolute paths using `os.path.expanduser()`.

2. **Scanning Repositories:**
   It walks through the `scan_dir` to find Git repositories (by detecting .git folders) and excludes any repository that is within the model repository.

3. **Status Block & Fix Commands:**
   For each repository, the script checks for the presence of each required directory and file. For files, it compares the line counts; if equal, it also gets file sizes. These results are then formatted into commented lines for the status block. Active commands are generated only for missing items, with only `mkdir` for directories (no copying) and `cp` for files.

4. **Output Generation:**
   All text is assembled into a list of strings and written to the output fix script. The script uses functions to “restore” HOME paths (so that they show with a leading `~` rather than the full absolute path).

5. **Backup & Permissions:**
   Before writing the new fix script, any existing file is backed up with a timestamp. The new script is then made executable.

6. **Optional Execution:**
   If the `--apply` flag is provided, the script uses `os.system()` to execute the generated Bash script immediately.
