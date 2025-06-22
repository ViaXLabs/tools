# Repo Hygiene Fix-Script Generator

A **Bash** utility that recursively scans a directory tree for Git repositories, compares each repository against a “model” (gold-standard) repository, and generates a self-contained **fix script** to update any missing files or directories. Optionally, the generated fix script can be executed immediately.

All configuration is provided via a single JSON file.

- [Repo Hygiene Fix-Script Generator](#repo-hygiene-fix-script-generator)
  - [Features](#features)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Configuration](#configuration)
  - [Usage](#usage)
    - [Examples](#examples)
  - [Example Directory Layout](#example-directory-layout)
  - [How It Works](#how-it-works)
  - [Testing the Script](#testing-the-script)
    - [Explanation Summary](#explanation-summary)

---

## Features

- **Configuration via JSON:**
  - **scan_dir**: The starting directory to scan for Git repositories (e.g., `/repo` or `/repo/Team1`). You can use `~` to refer to your HOME directory.
  - **model_repo**: The path to your gold-standard repository.
  - **output_file**: The filename (and optionally path) for the generated fix script.
  - **required_dirs**: An array of directories that each repository must contain.
  - **required_files**: An array of file paths (including dot-files and nested paths) that each repository must have.
- **Tilde Expansion:**
  - Any path starting with `~` is automatically expanded to the HOME directory.
- **Recursive Scanning:**
  - The script scans the entire tree under `scan_dir`, handling nested folders (e.g., team folders).
- **Model Repository Exclusion:**
  - If the model repository is found within the scan directory, it is skipped.
- **Backup:**
  - An existing fix script at the output location is backed up with a timestamp before generating a new one.
- **Status Blocks & Fix Commands:**
  - For each repository, a **commented status block** is generated which shows which required directories and files exist (with file line count comparisons) and which are missing.
  - If any items are missing, **active commands** (using `mkdir -p` and `cp`) are emitted to fix them.
- **Optional Immediate Application:**
  - Using the `--apply` flag, the generated fix script is run immediately.
- **Bash v3 Compatibility:**
  - The script uses while‑read loops instead of `readarray` and parallel indexed arrays instead of associative arrays so that it works on Bash version 3.

---

## Prerequisites

- **GNU Bash 3+**
- **jq** – JSON command-line processor

If `jq` isn’t installed, use one of the following commands:

```bash
# Ubuntu/Debian:
sudo apt-get install jq

# macOS (Homebrew):
brew install jq
```

---

## Installation

1. Clone or download this repository.
2. Make the main script executable:
   ```bash
   chmod +x repo-hygiene.sh
   ```

---

## Configuration

Create a JSON configuration file (e.g., `config.json`) in the same folder as `repo-hygiene.sh`. For example:

```json
{
  "scan_dir": "repos",
  "model_repo": "model-repo",
  "output_file": "fix-script.sh",
  "required_dirs": [".vscode", ".github", "harness"],
  "required_files": [".gitignore", "pre-commit.yaml", ".vscode/extensions.json"]
}
```

- **scan_dir**: The directory from which to start scanning for Git repositories (you can use an absolute path or paths starting with `~`).
- **model_repo**: The path to your reference repository.
- **output_file**: The target filename for the generated fix script.
- **required_dirs** & **required_files**: Lists of directories and files expected in every repository.

---

## Usage

Run the script by specifying your configuration file:

```bash
./repo-hygiene.sh -c config.json [--apply]
```

**Options:**

- `-c <file>` : (Required) Path to the JSON config file.
- `-o <file>` : (Optional) Specify a different output file for the fix script.
- `--apply` : (Optional) Immediately run the generated fix script after creation.
- `-h` : Show the help message and exit.

### Examples

- **Dry Run (generate fix script only):**
  ```bash
  ./repo-hygiene.sh -c config.json
  ```
- **Generate and Apply Fixes Immediately:**
  ```bash
  ./repo-hygiene.sh -c config.json --apply
  ```

---

## Example Directory Layout

Suppose your directory structure is as follows:

```
.
├── config.json
├── model-repo/             # Your gold-standard repository
│   ├── .git/
│   ├── .gitignore
│   ├── pre-commit.yaml
│   ├── .vscode/
│   │   └── extensions.json
│   └── harness/
├── repo-hygiene.sh
└── repos/                  # scan_dir
    ├── Team1/
    │   ├── repoA/          # Git repository (may be missing required items)
    │   └── repoB/          # Another Git repository
    └── Team2/
        └── repoC/          # Yet another Git repository
```

The script will recursively scan “repos” and (for example) produce a fix script to add missing directories or files by copying from “model-repo”.

---

## How It Works

1. **Dependency Check:**
   The script first checks whether `jq` is installed and provides installation instructions if it isn’t.
2. **Configuration Loading & Tilde Expansion:**
   It reads configuration values from the JSON file and expands any path that begins with `~` to the HOME directory.
3. **Backup:**
   If the output file already exists, it is backed up (renamed with a timestamp) before a new fix script is created.
4. **Recursive Scan:**
   It uses the `find` command to locate all `.git` directories under the specified `scan_dir` and treats the parent of each as a repository root. The model repository is skipped.
5. **Status Block Generation:**
   For each repository, a commented status block is added to the fix script showing which required directories exist and which files exist (with a comparison of line counts to the model file) alongside those that are missing.
6. **Fix Command Generation:**
   If any required items are missing, active commands (e.g., `mkdir -p` and `cp`) are appended to the fix script.
7. **Optional Execution:**
   If you run the script with the `--apply` flag, the generated fix script is executed immediately.
8. **Output:**
   Finally, the fix script is made executable and its location is reported.

---

## Testing the Script

Follow these steps to test the script:

1. **Set Up a Test Environment:**

   ```bash
   # Create a sample model repository.
   mkdir model-repo && cd model-repo
   git init -q
   echo -e "line1\nline2\nline3" > .gitignore
   echo -e "step1\nstep2\nstep3\nstep4" > pre-commit.yaml
   mkdir -p .vscode && echo '{"foo":1}' > .vscode/extensions.json
   cd ..

   # Create target repositories under the scan directory.
   mkdir -p repos/Team1/repoA repos/Team1/repoB repos/Team2/repoC
   for d in repos/Team1/repoA repos/Team1/repoB repos/Team2/repoC; do
     (cd "$d" && git init -q)
   done

   # Create a config file.
   cat > config.json <<EOF
   {
   "scan_dir": "repos",
   "model_repo": "model-repo",
   "output_file": "fix-script.sh",
   "required_dirs": [".vscode", ".github"],
   "required_files": [".gitignore", "pre-commit.yaml", ".vscode/extensions.json"]
   }
   EOF
   ```

2. **Dry Run (Generate Fix Script Only):**

   ```bash
   ./repo-hygiene.sh -c config.json
   cat fix-script.sh
   ```

   The generated fix script will have commented status blocks for each repository and active commands for adding missing items.

3. **Apply Fixes Immediately:**

   ```bash
   ./repo-hygiene.sh -c config.json --apply
   tree -a
   ```

   After running these commands, check that the target repositories have been updated with the missing directories and files copied from the model repository.

---

### Explanation Summary

- **Tilde Expansion:** A small function in the script ensures that any paths beginning with `~` are expanded correctly.
- **JSON Configuration:** All necessary settings (scan directory, model repository, output file, required items) are loaded from a JSON file.
- **Bash v3 Compatibility:** The script replaces newer commands like “readarray” with while-read loops and uses parallel indexed arrays instead of associative arrays.
- **Backup and Recursive Scan:** The script backs up any existing output file and recursively scans for Git repositories using the `find` command, skipping the model repository if it’s within the scan directory.
- **Status and Fix Commands:** For each repository, the status (existing/missing directories and files with line count comparisons) is output as commented blocks, and active commands are appended only for missing items.
- **Optional Immediate Fix:** The `--apply` flag causes the script to run the generated fix script immediately.
