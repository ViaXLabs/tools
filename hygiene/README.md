# Repo Hygiene Fix-Script Generator

A **Bash** utility that scans a directory tree of Git repositories, compares each repo to a "model" repository, and generates a self-contained **fix script** to bring them into compliance. Optionally, it can apply fixes automatically. All settings are provided via a JSON configuration file.

---

## Features

- **Configuration via JSON**:
  - `scan_dir`: The directory where the script starts looking for Git repositories.
  - `model_repo`: Your "gold-standard" repository.
  - `output_file`: The name of the generated fix script.
  - `required_dirs`: Array of directories each repo must contain.
  - `required_files`: Array of files (including dot-files and nested paths) each repo must have.
- **Dependency Check**: Ensures `jq` is installed before proceeding.
- **Backup**: Automatically backs up any existing fix script by renaming it with a timestamp.
- **Status Block**: For each repo, outputs a commented status block showing:
  - For directories: Whether they exist or are missing.
  - For files: Whether they exist, and if so, the line count in the repo versus the model.
- **Active Fix Commands**: Generates active commands (`echo`, `mkdir -p`, and `cp`) to add any missing items.
- **Skip Model Repo**: Skips scanning the model repository if it's within the scan directory.
- **Optional Application**: With the `--apply` flag, the generated fix script runs immediately to fix the repositories.

---

## Prerequisites

- **GNU Bash 4+**
- **jq** (JSON processor)

If `jq` is not installed, you can install it as follows:

```bash
# Ubuntu/Debian
sudo apt-get install jq

# macOS (using Homebrew)
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

Create a JSON file (e.g., `config.json`) in the same folder as `repo-hygiene.sh`:

```json
{
  "scan_dir": "repos",
  "model_repo": "model-repo",
  "output_file": "fix-script.sh",
  "required_dirs": [".vscode", ".github", "harness"],
  "required_files": [".gitignore", "pre-commit.yaml", ".vscode/extensions.json"]
}
```

- **scan_dir**: The directory to start scanning (e.g., where your target repos reside).
- **model_repo**: The path to your reference repository.
- **output_file**: The name of the generated fix script.
- **required_dirs** and **required_files**: Lists of directories and files expected in each repository.

---

## Usage

Run the script specifying your configuration file with `-c`:

```bash
./repo-hygiene.sh -c config.json [--apply]
```

- `-c <file>`: JSON config file (required).
- `-o <file>`: (Optional) Specify a different output fix-script file name.
- `--apply`: After generating the fix script, run it immediately to apply the fixes.
- `-h`: Display help.

Example (dry run):

```bash
./repo-hygiene.sh -c config.json
```

Example (apply fixes immediately):

```bash
./repo-hygiene.sh -c config.json --apply
```

---

## Example Directory Layout

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
    ├── repoA/              # Has .git; may have some missing files/dirs
    ├── repoB/              # Has .git; likely missing required items
    └── repoC/              # etc.
```

---

## What the Script Does

1. **Dependency Check**: Verifies that `jq` is installed.
2. **Loads Config**: Reads settings from the provided JSON file.
3. **Scans for Repos**: Looks under `scan_dir` for directories containing a `.git` folder, skipping the model repo.
4. **Checks for Required Items**: For each repo, it checks that the required directories and files exist. For files, it compares the line count in the target repo with that of the model repository.
5. **Generates a Fix Script**:
   - Generates a commented status block for each repo showing what is present and what's missing.
   - Emits active commands (`mkdir` and `cp`) to create missing directories and copy missing files.
6. **Backup**: If an output fix script already exists, it is backed up with a timestamp.
7. **Optional Apply**: With `--apply`, the fix script is executed immediately.

---

## Testing the Script

You can perform a quick test using the following snippet (assuming you have a similar directory structure):

```bash
#!/usr/bin/env bash
set -euo pipefail

# Setup test environment

# Create model repository
mkdir model-repo && cd model-repo
git init -q
echo -e "a\nb\nc" > .gitignore
echo -e "1\n2\n3\n4" > pre-commit.yaml
mkdir -p .vscode && echo '{"foo": 1}' > .vscode/extensions.json
cd ..

# Create target repositories in scan_dir (repos)
mkdir -p repos/repoA repos/repoB
cd repos/repoA
git init -q && echo -e "a\nb" > .gitignore
cd ../repoB
git init -q
cd ..

# Create config file
cat > config.json <<EOF
{
  "scan_dir": "repos",
  "model_repo": "model-repo",
  "output_file": "fix-script.sh",
  "required_dirs": [".vscode", ".github"],
  "required_files": [".gitignore", "pre-commit.yaml", ".vscode/extensions.json"]
}
EOF

# Run dry run
../repo-hygiene.sh -c config.json
cat fix-script.sh

# Optionally, run with --apply to update the repos.
../repo-hygiene.sh -c config.json --apply
tree -a
```

After running, you'll see that repositories missing items have had directories created and files copied from the model.

---

### Explanation (tl/dr;)

- **Dependency Check**: Right at the top, the script checks if `jq` is installed. If it isn’t, it prints installation instructions and exits.

- **Usage & Config**: The script uses `-c` to take a JSON config file. This JSON sets the scanning directory, the model repo (the gold standard), and the required files and directories. The output fix script name is read from the JSON (with a default).

- **Backup Mechanism**: If an output file with the same name already exists, it is renamed with a timestamp before writing a new one.

- **Scanning & Reporting**: For each repo found in the scan directory (skipping the model repo if it’s inside the scan directory), the script checks for required directories and files. It computes line counts for files, then writes a commented status block to the fix script (indicating what’s present or missing).

- **Active Fix Commands**: Only if missing items are detected, the script writes active commands (i.e. commands that are not commented out) to create directories and copy files from the model repo.

- **Optional Apply**: The fix script can be executed immediately by using the `--apply` flag.
