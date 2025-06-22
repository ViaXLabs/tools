# Repo Hygiene Fix-Script Generator

A **Bash** utility that recursively scans a directory tree for Git repositories, compares each repository
against a "model" (gold-standard) repository, and generates a self-contained **fix script** to update any missing
files or directories. Optionally, the fix script can be applied immediately.

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
  - `scan_dir` : The root directory to start scanning Git repositories (e.g. `/repo` or `/repo/Team1`).
  - `model_repo` : Path to your gold-standard repository containing the correct files and directories.
  - `output_file` : Name/path of the generated fix script.
  - `required_dirs` : An array of directories every repository must contain.
  - `required_files` : An array of file paths (supporting dot-files and nested paths) every repository must have.
- **Tilde Expansion:**
  - Any input paths beginning with `~` are automatically expanded to the user's HOME directory.
- **Recursive Scanning:**
  - The script scans the entire directory tree under `scan_dir` (supports nested team folders).
- **Excludes the Model Repo:**
  - If the model repository is inside the scan directory, it is skipped.
- **Backup Existing Output:**
  - If a fix script already exists at the output location, it is backed up with a timestamp.
- **Status Blocks and Active Fix Commands:**
  - For each repository, a commented status block is generated, showing which required directories and files
    are present (with file line count comparisons) and which are missing.
  - If any items are missing, active commands (`mkdir -p` and `cp`) to fix them are emitted.
- **Optional Automatic Apply:**
  - If run with the `--apply` flag, the generated fix script is executed immediately.

---

## Prerequisites

- **GNU Bash 4+**
- **jq** (for JSON parsing)

If `jq` is not installed, use one of the following:

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

- **scan_dir**: The directory from which to start scanning for Git repositories. This can be an absolute path, or you can use `~` (which will be expanded to your HOME directory).
- **model_repo**: The path to your reference repository.
- **output_file**: The name for the generated fix script.
- **required_dirs** and **required_files**: Lists of directories and files that must exist in every repository.

---

## Usage

Run the script with the configuration file:

```bash
./repo-hygiene.sh -c config.json [--apply]
```

**Options:**

- `-c <file>` : (Required) Path to the JSON config file.
- `-o <file>` : (Optional) Specify a different output fix script filename.
- `--apply` : (Optional) Immediately run the generated fix script to apply fixes.
- `-h` : Show the help message and exit.

### Examples

- **Dry Run (generate fix script only):**

  ```bash
  ./repo-hygiene.sh -c config.json
  ```

- **Apply Fixes Immediately:**

  ```bash
  ./repo-hygiene.sh -c config.json --apply
  ```

---

## Example Directory Layout

For instance, you may have a structure like this:

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
    │   ├── repoA/          # Git repo with possible missing items
    │   └── repoB/          # Another Git repo
    └── Team2/
        └── repoC/          # Yet another Git repo
```

The script will recursively scan `repos` and handle nested folders like `Team1` and `Team2`.

---

## How It Works

1. **Dependency Check:**
   The script verifies that `jq` is installed. If not, it exits with installation instructions.

2. **Load and Process Config:**
   It loads configuration values from `config.json` and expands any leading `~` in paths to the HOME directory.

3. **Backup Mechanism:**
   If an output fix script already exists at the specified location, the script backs it up by renaming it with a timestamp.

4. **Recursive Scan:**
   It uses the `find` command to locate all `.git` directories within `scan_dir` and then scans each repository (the parent of each `.git` directory).
   The model repository is skipped if found within the scan directory.

5. **Status Reporting & Fix Generation:**
   For each repository, the script checks for the required directories and files. For files, it also compares the line count with the corresponding file in the model repo.
   A commented status block is written to the generated fix script, followed by active commands to create missing items.

6. **Optional Fix Application:**
   With the `--apply` flag, after generating the fix script, the script automatically runs it to apply the fixes.

---

## Testing the Script

Here’s a quick test guide:

1. **Set Up Test Environment:**

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
   "required_dirs": [".vscode",".github"],
   "required_files": [".gitignore","pre-commit.yaml",".vscode/extensions.json"]
   }
   EOF
   ```

2. **Generate Fix Script (Dry Run):**

   ```bash
   ./repo-hygiene.sh -c config.json
   cat fix-script.sh
   ```

3. **Apply Fixes Immediately:**

   ```bash
   ./repo-hygiene.sh -c config.json --apply
   tree -a
   ```

After running these commands, the target repositories will have the missing directories and files copied from the model repository.

---

### Explanation Summary

- **Tilde Expansion:** The function `expand_tilde()` ensures that any path starting with `~` is correctly expanded to the HOME directory.
- **Configuration Parsing:** The script reads values from a JSON file and expands paths where necessary.
- **Backup & Output:** If an existing fix script is found, it is backed up with a timestamp before a new one is generated.
- **Scanning & Fix Generation:** Each repository is scanned for required items; a commented status is output (with file line count comparisons) and (if needed) active commands are written for missing items.
- **Optional Immediate Execution:** The `--apply` flag causes the generated fix script to run immediately.

This solution has been thoroughly refactored and tested to be clear, robust, and easy to use. Enjoy your new Repo Hygiene Fix-Script Generator!
