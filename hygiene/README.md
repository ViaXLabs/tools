# Repo Hygiene Fix-Script Generator

A **Bash** helper that scans a directory of Git repositories against a “model” repository and generates a self-contained fix script. You can also apply fixes automatically.

- [Repo Hygiene Fix-Script Generator](#repo-hygiene-fix-script-generator)
  - [Features](#features)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Configuration](#configuration)
  - [Usage](#usage)
  - [Example Directory Layout](#example-directory-layout)
  - [Sample Run](#sample-run)
    - [1) Dry-run: Generate fix script only](#1-dry-run-generate-fix-script-only)
      - [Excerpt from `fix-repos.sh`](#excerpt-from-fix-repossh)
    - [2) Apply: Generate \& execute](#2-apply-generate--execute)
  - [Script Details](#script-details)
  - [Testing](#testing)
  - [License](#license)

---

## Features

- Reads **all settings** from a single JSON config
- Scans each subfolder for a `.git` directory (i.e. real Git repos)
- Validates presence of required **directories** and **files** (including dot-files and nested paths)
- For each existing file, compares line count vs. the model repo
- Emits a **fix script** (`fix-script.sh` by default) in which:
  - **All non-action** lines are commented out (`# …`)
  - `echo` lines announce which repo and items are being updated
  - `mkdir -p` and `cp` lines are active—ready to run
- Optional `--apply` mode runs the generated fix script immediately

---

## Prerequisites

- **Bash** (GNU Bash 4+)
- **jq** (JSON processor)

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

## Configuration

Create a JSON file (e.g. `config.json`) describing:

- **model_repo**: path to your “gold-standard” repository
- **required_dirs**: array of directory names/paths to enforce
- **required_files**: array of file paths (including dot-files and nested paths)

```json
{
  "model_repo": "../my-model-repo",
  "required_dirs": [".vscode", ".github", "harness"],
  "required_files": [".gitignore", "pre-commit.yaml", ".vscode/extensions.json"]
}
```

Place `config.json` alongside `repo-hygiene.sh`.

---

## Usage

```bash
./repo-hygiene.sh \
  -i config.json \
  [-o fix-script.sh] \
  [--apply] \
  [-h]
```

| Flag        | Description                                                        |
| ----------- | ------------------------------------------------------------------ |
| `-i <file>` | **(Required)** Path to the JSON config file                        |
| `-o <file>` | Output fix script path (default: `fix-script.sh`)                  |
| `--apply`   | After generating the script, immediately execute it to apply fixes |
| `-h`        | Show help and exit                                                 |

---

## Example Directory Layout

```
.
├── config.json
├── my-model-repo/               # reference “model” repo
│   ├── .git/
│   ├── .gitignore
│   ├── pre-commit.yaml
│   ├── .vscode/
│   │   └── extensions.json
│   └── harness/
├── repo-hygiene.sh
└── repos/
    ├── repoA/
    │   ├── .git/
    │   └── .gitignore      # 12 lines
    ├── repoB/
    │   └── .git/
    └── repoC/
        ├── .git/
        └── .github/
```

---

## Sample Run

### 1) Dry-run: Generate fix script only

```bash
cd repos
../repo-hygiene.sh -i ../config.json -o fix-repos.sh
```

#### Excerpt from `fix-repos.sh`

```bash
#!/usr/bin/env bash
# Auto-generated fix script — DO NOT EDIT
# Model repo : ../my-model-repo
# Generated on: 2025-06-22T12:00:00+00:00

# ───────────────────────────────────────
# Repo: repoA/
#   Directories:
#     – DIR .vscode missing
#     – DIR .github missing
#   Files:
#     + FILE .gitignore exists (12 vs 14)
#     – FILE pre-commit.yaml missing
#     – FILE .vscode/extensions.json missing

echo ">> Updating repoA/"
echo " Missing dirs : .vscode .github"
echo " Missing files: pre-commit.yaml .vscode/extensions.json"

mkdir -p "repoA/.vscode"
cp -r "../my-model-repo/.vscode" "repoA/.vscode"
mkdir -p "repoA/.github"
cp -r "../my-model-repo/.github" "repoA/.github"
cp "../my-model-repo/pre-commit.yaml" "repoA/pre-commit.yaml"
mkdir -p "repoA/.vscode"
cp "../my-model-repo/.vscode/extensions.json" "repoA/.vscode/extensions.json"

# ───────────────────────────────────────
# Repo: repoB/
#   Directories:
#     – DIR .vscode missing
#     – DIR .github missing
#   Files:
#     – FILE .gitignore missing
#     – FILE pre-commit.yaml missing
#     – FILE .vscode/extensions.json missing

echo ">> Updating repoB/"
# … and so on …
```

### 2) Apply: Generate & execute

```bash
../repo-hygiene.sh -i ../config.json --apply
```

This will:

1. Backup any existing `fix-script.sh` to `fix-script.sh.YYYYMMDD_HHMMSS.bak`
2. Generate a fresh `fix-script.sh`
3. Make it executable
4. Run it immediately, creating directories and copying files as needed

---

## Script Details

Below is the complete ``.
Save it in your working directory and run `chmod +x repo-hygiene.sh`

---

## Testing

1. **Set up a temporary workspace** (see the “Smoke Test” in this repo or copy-paste section below).
2. **Run a dry-run** and inspect `fix-script.sh`—verify status block, commented lines, and active commands.
3. **Run with `--apply`**—confirm missing directories/files appear in your target repos.

---

## License

MIT © Your Name.
Feel free to adapt and extend!
