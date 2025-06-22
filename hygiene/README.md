# Repo Hygiene Fix-Script Generator

A **Bash** utility that recursively scans a directory tree for Git repositories, compares each repository against a “model” (gold-standard) repository, and generates a self-contained **fix script**. This fix script updates any missing files or directories according to your configuration. Optionally, you can run the fix script immediately to apply the fixes.

All configuration is provided via a single JSON file.

---

## Features

- **Configuration via JSON:**
  - **scan_dir**: The root directory where the scan begins (e.g., `/repo` or `/repo/Team1`).
  - **model_repo**: Path to your gold-standard repository (which contains the correct files/directories).
  - **output_file**: The filename (and optionally, path) for the generated fix script.
  - **required_dirs**: An array of directories that each repository must have.
  - **required_files**: An array of file paths (supports dot-files and nested files) that each repository must have.
- **Tilde Expansion:**
  - Any path beginning with `~` is automatically expanded to your HOME directory.
- **Recursive Scanning:**
  - The script recursively scans the specified `scan_dir`, handling nested structures (e.g., team folders).
- **Model Repository Exclusion:**
  - If the model repository is inside the scan directory, it is skipped.
- **Backup:**
  - An existing fix script at the output location is backed up (renamed with a timestamp) before generating a new one.
- **Status Blocks & Fix Commands:**
  - For each repository, a commented status block shows what’s present (with line count comparisons for files) and what is missing.
  - Active commands (e.g., `mkdir -p` and `cp`) follow for any missing items.
- **Optional Application:**
  - With the `--apply` flag, the generated fix script is executed immediately.
- **Dependency Check:**
  - The script ensures that `jq` is installed, displaying instructions if it isn’t.

---

## Prerequisites

- **GNU Bash 4+**
- **jq** (JSON command-line parser)

If `jq` isn’t installed, try:

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

---

## Installation

1. Clone or download this repository.
2. Make the main script executable:
   ```bash
   chmod +x repo-hygiene.sh
   ```

---

## Configuration

Create a JSON file (e.g., `config.json`) in the same folder as `repo-hygiene.sh`. Example:

```json
{
  "scan_dir": "repos",
  "model_repo": "model-repo",
  "output_file": "fix-script.sh",
  "required_dirs": [".vscode", ".github", "harness"],
  "required_files": [".gitignore", "pre-commit.yaml", ".vscode/extensions.json"]
}
```

- **scan_dir**: The base directory for scanning (you may use `~` to represent your HOME directory).
- **model_repo**: The path to your reference repository.
- **output_file**: The name/path for the generated fix script.
- **required_dirs** and **required_files**: Items that must exist in every repository.

---

## Usage

Run the script by specifying your configuration file:

```bash
./repo-hygiene.sh -c config.json [--apply]
```

**Options:**

- `-c <file>`: (Required) JSON config file.
- `-o <file>`: (Optional) Override the output fix script filename from the config.
- `--apply` : (Optional) Immediately run the generated fix script.
- `-h` : Show help.

### Examples:

- **Generate only (dry-run):**
  ```bash
  ./repo-hygiene.sh -c config.json
  ```
- **Generate and apply fixes:**
  ```bash
  ./repo-hygiene.sh -c config.json --apply
  ```

---

## Example Directory Layout

For example, your directory structure might look like:

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

---

## How It Works

1. **Dependency Check:**
   The script verifies that `jq` is installed.
2. **Configuration Loading & Tilde Expansion:**
   Reads settings from `config.json` and expands any path starting with `~` to your HOME directory.
3. **Backup:**
   If an output fix script already exists, it is backed up with a timestamp.
4. **Recursive Scan:**
   All `.git` directories under `scan_dir` are located using `find`. The parent of each `.git` folder is considered a repository root. The model repository is skipped.
5. **Status Block Generation:**
   For each repository, a commented status block shows which required directories/files exist (with file line count comparisons) and which are missing.
6. **Fix Commands Generation:**
   If any required items are missing, active commands (`mkdir -p` and `cp`) are generated to fix them.
7. **Optional Execution:**
   If the `--apply` flag is provided, the script runs the generated fix script immediately.
8. **Output:**
   The fix script is generated at the specified path and is made executable.

---

## Testing the Script

You can test the script with the following steps:

1. **Set Up a Test Environment:**

   ```bash
   # Create a sample model repository.
   mkdir model-repo && cd model-repo
   git init -q
   echo -e "line1\nline2\nline3" > .gitignore
   echo -e "steps1\nsteps2\nsteps3\nsteps4" > pre-commit.yaml
   mkdir -p .vscode && echo '{"foo":1}' > .vscode/extensions.json
   cd ..

   # Create target repositories under the scan directory.
   mkdir -p repos/Team1/repoA repos/Team1/repoB repos/Team2/repoC

   # Initialize Git in each target repository.
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

2. **Dry Run: Generate the Fix Script Only**

   ```bash
   ./repo-hygiene.sh -c config.json
   cat fix-script.sh
   ```

3. **Apply Fixes Immediately:**

   ```bash
   ./repo-hygiene.sh -c config.json --apply
   tree -a
   ```

   After running these commands, you should see that each target repository has been updated with any missing directories or files from the model repository.

---

### Explanation Summary

- **Tilde Expansion:**
  The `expand_tilde()` function ensures that any path starting with `~` is correctly expanded to the user's HOME directory.

- **Configuration Loading:**
  The script loads the scan directory, model repository, and output fix script filename from a JSON config file. It uses `readarray` to load the arrays of required directories and files.

- **Backup:**
  Before generating a new fix script, an existing output file (if present) is backed up with a timestamp.

- **Scanning & Fix Generation:**
  The `find` command is used to recursively locate all `.git` directories under `scan_dir`. For each repository, the script writes a commented status block with information about existing/missing directories and files (including file line counts), then emits active commands to create missing items.

- **Optional Application:**
  When run with `--apply`, the script executes the generated fix script immediately.
