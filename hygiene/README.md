# Repo Hygiene Checker

A **Bash** script that scans a directory of Git repositories and ensures each repo matches a “model” repository’s structure. It:

- Reads **all settings** from a single **JSON** file
- Verifies required **directories** and **files** exist (including dot-files and nested paths)
- Counts lines in existing files **and** compares them to the model repo’s line counts
- Generates a **plain-text report** listing:
  - Present directories
  - Present files with line counts vs. model
  - Missing directories and files
  - Ready‐to‐run `cp` commands for copying missing items
- Supports a `--apply` flag to **automatically** copy missing items
- Designed for **ease of use**, with clear flags and extensive inline comments

---

- [Repo Hygiene Checker](#repo-hygiene-checker)
  - [Requirements](#requirements)
  - [Installation](#installation)
  - [Configuration (JSON)](#configuration-json)
  - [Usage](#usage)
  - [Sample Run](#sample-run)
    - [Directory Structure](#directory-structure)
    - [`config.json`](#configjson)
    - [Dry‐Run (Report Only)](#dryrun-report-only)
    - [Excerpt from `report.txt`](#excerpt-from-reporttxt)
    - [Dry‐Run with Apply](#dryrun-with-apply)

---

## Requirements

- **Bash** (GNU Bash 4+)
- **jq** (JSON processor)

Install `jq` if you don’t have it:

```bash
# Debian/Ubuntu
sudo apt-get update && sudo apt-get install -y jq

# macOS (Homebrew)
brew install jq
```

---

## Installation

1. Clone or download this repository.
2. Make the script executable:

   ```bash
   chmod +x repo-hygiene.sh
   ```

---

## Configuration (JSON)

Create a JSON file (e.g. `config.json`):

```json
{
  "model_repo": "../my-model-repo",
  "required_dirs": [".vscode", ".github", "harness"],
  "required_files": [".gitignore", "pre-commit.yaml", ".vscode/extensions.json"]
}
```

- **model_repo**: Path to your “gold standard” repository.
- **required_dirs**: Array of directories that must exist in each repo.
- **required_files**: Array of files (including nested/dot-files) that must exist.

---

## Usage

```bash
./repo-hygiene.sh -i config.json [-o report.txt] [--apply] [-h]
```

```
| Flag        | Description                                                                                        |
|-------------|----------------------------------------------------------------------------------------------------|
| `-i <file>` | **(required)** Path to the JSON config file.                                                      |
| `-o <file>` | Path to write the report (default: `hygiene-report.txt`).                                         |
| `--apply`   | If present, **automatically** copies any missing directories/files from the model repo into target repos. |
| `-h`        | Show help and exit.                                                                                |

---
```

## Sample Run

### Directory Structure

```text
.
├── config.json
├── my-model-repo/            # Your reference repo
│   ├── .git/
│   ├── .gitignore            # 14 lines
│   ├── pre-commit.yaml       # 25 lines
│   ├── .vscode/
│   │   └── extensions.json   #  8 lines
│   └── harness/
├── repo-hygiene.sh
└── repos/
    ├── repoA/
    │   ├── .git/
    │   └── .gitignore        # 12 lines
    ├── repoB/
    │   └── .git/
    └── repoC/
        ├── .git/
        └── .github/
```

### `config.json`

```json
{
  "model_repo": "../my-model-repo",
  "required_dirs": [".vscode", ".github", "harness"],
  "required_files": [".gitignore", "pre-commit.yaml", ".vscode/extensions.json"]
}
```

### Dry‐Run (Report Only)

```bash
cd repos
../repo-hygiene.sh -i ../config.json -o report.txt
```

### Excerpt from `report.txt`

```
Repository Hygiene Report
Model repo: ../my-model-repo
Checked on: 2025-06-21 15:42:10+00:00

----------------------------------------
Repo: repoA/
  PRESENT DIRECTORIES:
    (none)
  PRESENT FILES (with line counts vs. model):
    - .gitignore : 12 lines (model: 14)
  MISSING DIRECTORIES:
    - .vscode
    - .github
    - harness
  MISSING FILES:
    - pre-commit.yaml
    - .vscode/extensions.json
  FIX COMMANDS:
    cp -r "../my-model-repo/.vscode" "repoA/.vscode"
    cp -r "../my-model-repo/.github" "repoA/.github"
    cp -r "../my-model-repo/harness" "repoA/harness"
    mkdir -p "repoA/.vscode"
    cp "../my-model-repo/.vscode/extensions.json" "repoA/.vscode/extensions.json"
    cp "../my-model-repo/pre-commit.yaml" "repoA/pre-commit.yaml"
    cp "../my-model-repo/.gitignore" "repoA/.gitignore"
```

### Dry‐Run with Apply

```bash
../repo-hygiene.sh -i ../config.json --apply
```

This will also **copy** missing directories and files into each repo.

---
