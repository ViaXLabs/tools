# Repo Hygiene Fix-Script Generator

A **Bash** utility that recursively scans a directory tree for Git repositories, compares each repository against a “model” (gold-standard) repository, and generates a self-contained **fix script** to update any missing files or directories. Optionally, you can immediately run the generated fix script to apply fixes.

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
    - [Set Up a Test Environment:](#set-up-a-test-environment)
    - [Dry Run (Generate Fix Script Only):](#dry-run-generate-fix-script-only)
    - [Apply Fixes Immediately:](#apply-fixes-immediately)
  - [License](#license)

All configuration is provided via a single JSON file.

## Features

- **Configuration via JSON:**
  - **scan_dir:** The starting directory to scan for Git repositories (e.g., `/repo` or `/repo/Team1`). Paths may begin with `~` to refer to your HOME directory.
  - **model_repo:** Path to your gold-standard repository.
  - **output_file:** The filename (or path) for the generated fix script.
  - **required_dirs:** An array of directories that each repository must contain.
  - **required_files:** An array of file paths (including dotfiles and nested paths) that each repository must have.
- **Tilde Expansion and Restoration:**
  Internally, paths beginning with `~` are expanded to full HOME paths. In the generated fix script, any path falling within your HOME directory is restored to a leading `~`.
- **Path Joining:**
  The `join_path` helper function correctly joins parent paths with relative paths, ensuring that dotfiles (such as `.gitignore`) and subdirectories (e.g., `.vscode`) are handled properly.
- **Recursive Scanning:**
  Scans the entire tree under `scan_dir`, handling nested directories (e.g., team folders).
- **Model Repo Exclusion:**
  Skips processing any repository whose absolute path begins with that of the model repository.
- **Backup:**
  Backs up an existing fix script (renamed with a timestamp) before generating a new one.
- **Status Blocks & Fix Commands:**
  For each repository, the generated fix script contains:
  - A commented status block that shows which required directories exist and which required files exist. For files, if the model file’s line count equals the scanned file's line count, the file sizes (in bytes) are also obtained and printed. For example:
    - When line counts differ:
      `+ FILE .gitignore exists (model lines: 15 vs scanned file: 20)`
    - When line counts are equal:
      `+ FILE .gitignore exists (model lines: 15 vs scanned file: 15; model size: 1024 bytes vs scanned file: 1200 bytes)`
  - Active fix commands to create missing directories and copy missing files. In this section, each missing directory or file is echoed on its own line.
- **Divider Line:**
  A line of equals signs is printed between repository blocks in the generated fix script.
- **Optional Immediate Application:**
  The `--apply` flag causes the generated fix script to be executed immediately.
- **Bash v3 Compatibility:**
  Uses while‑read loops, backticks for command substitution, and `expr` for arithmetic to ensure compatibility with Bash 3.2.

## Prerequisites

- **GNU Bash 3+**
- **jq** – A JSON command‑line processor

If jq isn’t installed, use one of the following:

```bash
# Ubuntu/Debian:
sudo apt-get install jq

# macOS (Homebrew):
brew install jq

# Fedora/RHEL:
sudo dnf install jq

# Arch Linux:
sudo pacman -S jq
```

## Installation

1. Clone or download this repository.
2. Make the script executable:
   ```bash
   chmod +x repo-hygiene.sh
   ```

## Configuration

Create a JSON configuration file (e.g., `config.json`) in the same directory as the script. For example:

```json
{
  "scan_dir": "repos",
  "model_repo": "model-repo",
  "output_file": "repo-hygiene-fix.sh",
  "required_dirs": [".vscode", ".github", "harness"],
  "required_files": [".gitignore", "pre-commit.yaml", ".vscode/extensions.json"]
}
```

- **scan_dir:** The directory from which scanning begins (absolute paths or those starting with `~` are supported).
- **model_repo:** The path to your reference repository.
- **output_file:** The filename for the generated fix script.
- **required_dirs/required_files:** Lists of directories and files expected in every repository.

## Usage

Run the script by specifying your configuration file:

```bash
./repo-hygiene.sh -c config.json [--apply]
```

**Options:**

- `-c <file>`: (Required) JSON config file.
- `-o <file>`: (Optional) Override the output fix script filename.
- `--apply`: (Optional) Immediately run the generated fix script.
- `-h`: Show the help message and exit.

### Examples

- **Dry Run (Generate Fix Script Only):**
  ```bash
  ./repo-hygiene.sh -c config.json
  ```
- **Generate and Apply Fixes Immediately:**
  ```bash
  ./repo-hygiene.sh -c config.json --apply
  ```

## Example Directory Layout

For example, your directory structure might be:

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

The script recursively scans `scan_dir` and processes each Git repository (excluding any whose absolute path starts with the model_repo’s absolute path).

## How It Works

1. **Dependency Check:** Verifies that jq is installed.
2. **Configuration & Tilde Expansion:** Reads settings from config.json and expands any tilde in input paths. In the generated fix script, paths that fall within your HOME directory are restored to use `~`.
3. **Backup:** Backs up any existing fix script with a timestamp.
4. **Recursive Scanning & Path Joining:** Uses the `find` command to locate all `.git` directories under `scan_dir`. The helper function `join_path` ensures correct formation of file paths (so dotfiles such as `.gitignore` are handled correctly). Any repository whose absolute path begins with that of model_repo is skipped.
5. **Status Block Generation:** For each repository, a commented block is produced that lists the required directories and files that exist. For files, it compares line counts and, if equal, displays the file sizes. For example:
   ```
   + FILE .gitignore exists (model lines: 15 vs scanned file: 15; model size: 1024 bytes vs scanned file: 1200 bytes)
   ```
   or if line counts differ:
   ```
   + FILE .gitignore exists (model lines: 15 vs scanned file: 20)
   ```
6. **Fix Command Generation:** If any required items are missing, active commands to create directories and copy files are output, with each missing item echoed on its own line.
7. **Divider Line:** A divider line of "=" characters separates each repository block.
8. **Optional Execution:** With the `--apply` flag, the generated fix script is executed immediately.
9. **Output:** The fix script is created at the specified location and made executable.

## Testing the Script

### Set Up a Test Environment:

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
  "output_file": "repo-hygiene-fix.sh",
  "required_dirs": [".vscode", ".github"],
  "required_files": [".gitignore", "pre-commit.yaml", ".vscode/extensions.json"]
}
EOF
```

### Dry Run (Generate Fix Script Only):

```bash
./repo-hygiene.sh -c config.json
cat repo-hygiene-fix.sh
```

Examine the generated fix script. It should include:

- A header with HOME-relative paths restored (using `~`).
- For each repository, a commented status block listing existing directories and files. For files, the line count comparison is printed; if the counts match, file sizes are also displayed.
- Missing directories and files are printed on separate echo lines.
- A divider line separates repository blocks.

### Apply Fixes Immediately:

```bash
./repo-hygiene.sh -c config.json --apply
tree -a
```

After running these commands, verify that the target repositories have been updated with any missing directories and files copied from the model repository.

## License

MIT © Your Name

Feel free to modify or extend this script as needed!

```

---

This final version initializes missing_dirs (and similar arrays) properly using default expansion when referenced, and prints each missing item on its own line. The shebang is `#!/bin/bash` and the default output filename is now `repo-hygiene-fix.sh`. When writing the fix commands, paths falling within `$HOME` are restored to start with `~`.

Enjoy your improved Repo Hygiene Fix-Script Generator!
```
