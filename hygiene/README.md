````markdown
# Repo Hygiene Fix-Script Generator

A **Bash** helper that scans a directory of Git repos against a “model” repo and spits out a self-contained **fix script**.
All your repos live under one folder; the script:

- [Installation](#installation)
- [Configuration (JSON)](#configuration-json)
- [Usage](#usage)
- [Example Directory Layout](#example-directory-layout)
- [Sample Run \& Output](#sample-run--output)
- [How It Works](#how-it-works)
- [License](#license)

- Reads **one** JSON config (`-i config.json`) for:
  - `model_repo`: path to your reference (“gold-standard”) repo
  - `required_dirs`: list of directories every repo must have
  - `required_files`: list of files (including dot-files and nested paths)
- Walks each `*/.git` subfolder under your current directory
- Builds a **fix script** (default `fix-script.sh`) in which:
  - **All non-action** lines are commented out
  - `echo` lines announce which repo and items are being fixed
  - `mkdir -p` & `cp` lines are active—ready to run
- Optionally runs the fix script immediately with `--apply`

---

## Table of Contents

1. [Requirements](#requirements)
2. [Installation](#installation)
3. [Configuration (JSON)](#configuration-json)
4. [Usage](#usage)
5. [Example Directory Layout](#example-directory-layout)
6. [Sample Run & Output](#sample-run--output)
7. [Script Walk-Through](#script-walk-through)
8. [License](#license)

---

## Requirements

- **Bash** (GNU Bash 4+)
- **jq** (JSON processor)

```bash
# Debian/Ubuntu
sudo apt-get update && sudo apt-get install -y jq

# macOS (Homebrew)
brew install jq
```
````

---

## Installation

1. Clone or download this repo.
2. Make the main script executable:

   ```bash
   chmod +x repo-hygiene.sh
   ```

---

## Configuration (JSON)

Create a `config.json` next to `repo-hygiene.sh`:

```json
{
  "model_repo": "../my-model-repo",
  "required_dirs": [".vscode", ".github", "harness"],
  "required_files": [".gitignore", "pre-commit.yaml", ".vscode/extensions.json"]
}
```

- **model_repo**: Path to the repo containing your “correct” folders & files.
- **required_dirs**: Any subdirs you want in _every_ target repo.
- **required_files**: Dot-files or nested files to enforce globally.

---

## Usage

```bash
./repo-hygiene.sh \
  -i config.json \
  [-o fix-script.sh] \
  [--apply] \
  [-h]
```

| Flag        | Description                                                               |
| ----------- | ------------------------------------------------------------------------- |
| `-i <file>` | **(required)** JSON config file                                           |
| `-o <file>` | Output fix script path (default: `fix-script.sh`)                         |
| `--apply`   | After generating the script, immediately execute it to copy missing items |
| `-h`        | Show help and exit                                                        |

---

## Example Directory Layout

```
.
├── config.json
├── my-model-repo/              # your “gold standard” repo
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

## Sample Run & Output

1. **Generate the fix script (dry-run):**

   ```bash
   cd repos
   ../repo-hygiene.sh -i ../config.json -o fix-repos.sh
   ```

2. **View `fix-repos.sh`:**

   ```bash
   #!/usr/bin/env bash
   # Auto-generated fix script – DO NOT EDIT
   # Model repo : ../my-model-repo
   # Generated on: 2025-06-21T12:34:56+00:00

   # Repo: repoA/
   echo "=> Updating repoA/"
   echo "   Missing dirs : .vscode .github harness"
   echo "   Missing files: pre-commit.yaml .vscode/extensions.json"

   mkdir -p "repoA/.vscode"
   cp -r "../my-model-repo/.vscode" "repoA/.vscode"
   mkdir -p "repoA/.github"
   cp -r "../my-model-repo/.github" "repoA/.github"
   mkdir -p "repoA/harness"
   cp -r "../my-model-repo/harness" "repoA/harness"
   cp "../my-model-repo/pre-commit.yaml" "repoA/pre-commit.yaml"
   mkdir -p "repoA/.vscode"
   cp "../my-model-repo/.vscode/extensions.json" "repoA/.vscode/extensions.json"


   # Repo: repoB/
   echo "=> Updating repoB/"
   echo "   Missing dirs : .vscode .github harness"
   echo "   Missing files: .gitignore pre-commit.yaml .vscode/extensions.json"

   mkdir -p "repoB/.vscode"
   cp -r "../my-model-repo/.vscode" "repoB/.vscode"
   mkdir -p "repoB/.github"
   cp -r "../my-model-repo/.github" "repoB/.github"
   mkdir -p "repoB/harness"
   cp -r "../my-model-repo/harness" "repoB/harness"
   cp "../my-model-repo/.gitignore" "repoB/.gitignore"
   cp "../my-model-repo/pre-commit.yaml" "repoB/pre-commit.yaml"
   mkdir -p "repoB/.vscode"
   cp "../my-model-repo/.vscode/extensions.json" "repoB/.vscode/extensions.json"


   # Repo: repoC/ is already compliant – no actions needed.
   ```

3. **Apply fixes immediately:**

   ```bash
   ../repo-hygiene.sh -i ../config.json -o fix-repos.sh --apply
   ```

   This will generate & run `fix-repos.sh`, creating any missing dirs/files.

---

## How It Works

1. **Parse flags** (`-i`, `-o`, `--apply`, `-h`).
2. **Validate** JSON config and `jq` availability.
3. **Read** `model_repo`, `required_dirs[]`, `required_files[]` via `jq`.
4. **Create** the fix-script header.
5. **Loop** through each `*/.git` subfolder:
   - Build lists of **missing** dirs & files.
   - If **any** are missing:
     - Write `echo` lines (active) to announce the fix.
     - Write `mkdir -p` and `cp` (active) commands.
   - Otherwise, write a commented note that the repo is compliant.
6. **Make** the fix-script executable.
7. **If** `--apply` is set, immediately run the fix-script.

---
