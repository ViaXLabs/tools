# Repo Hygiene Fix-Script Generator

A **Bash** utility that scans a directory tree for Git repositories, compares each repository against a “model” (gold-standard) repository, and generates a self-contained **fix script** to update any missing files or directories. Optionally, it can apply fixes immediately.

All configuration is provided through a single JSON file.

- [Repo Hygiene Fix-Script Generator](#repo-hygiene-fix-script-generator)
  - [Features](#features)
  - [Prerequisites](#prerequisites)
- [Create a sample model repository.](#create-a-sample-model-repository)
- [Create target repositories under the scan directory.](#create-target-repositories-under-the-scan-directory)
- [Initialize Git in each target repository.](#initialize-git-in-each-target-repository)
- [Create a configuration file.](#create-a-configuration-file)
  - [Explanation Summary](#explanation-summary)

---

## Features

- **Configuration via JSON:**
  - **scan_dir**: The root directory where the scan starts (for example, `/repo` or `/repo/Team1`).
  - **model_repo**: Your gold-standard repository (with correct files and directories).
  - **output_file**: The name (and path) of the generated fix script.
  - **required_dirs**: An array of directories each repository must have.
  - **required_files**: An array of file paths (including dot-files and nested paths) each repository must have.
- **Recursive Scanning:** The script searches the entire tree under the specified scan directory for Git repositories (identified by a `.git` directory).
- **Excludes the Model Repo:** If the model repository is found within the scan directory, it will be skipped.
- **Commented Status Blocks:** For each repository, the fix script contains a commented status block showing which required items exist (and, for files, a line count comparison) and which are missing.
- **Active Fix Commands:** Only if required items are missing are active `mkdir -p` and `cp` commands generated.
- **Backup:** Any existing fix script is automatically backed up with a timestamp before creating a new one.
- **Optional Automatic Apply:** Using the `--apply` flag, the generated script will be executed immediately after being generated.
- **Dependency Check:** Ensures that `jq` is installed; if not, you'll see instructions on how to install it.

---

## Prerequisites

- **GNU Bash 4+**
- **jq** (for JSON parsing)

If `jq` isn’t already installed, use one of these commands:

```bash
# Ubuntu/Debian:
sudo apt-get install jq

# macOS (Homebrew):
brew install jq
```

Installation
Clone or download the repository containing repo-hygiene.sh and this README.

Make the script executable:

bash
chmod +x repo-hygiene.sh
Configuration
Create a config.json file in the same folder as repo-hygiene.sh. For example:

json
{
"scan_dir": "repos",
"model_repo": "model-repo",
"output_file": "fix-script.sh",
"required_dirs": [
".vscode",
".github",
"harness"
],
"required_files": [
".gitignore",
"pre-commit.yaml",
".vscode/extensions.json"
]
}
scan_dir: The directory where the scan begins (this can include nested team folders such as /repo/Team1 and /repo/Team2).

model_repo: The path to your reference repository containing your “correct” files and directories.

output_file: The name of the generated fix script.

required_dirs and required_files: Lists of items that every repository under scan_dir is expected to have.

Usage
Run the script by specifying your configuration file with the -c flag:

bash
./repo-hygiene.sh -c config.json [--apply]
Options:

-c <file>: (Required) Specifies the JSON config file.

-o <file>: (Optional) Override the output fix script filename from the config file.

--apply : (Optional) Immediately run the generated fix script to update the repositories.

-h : Display the help message and exit.

Examples:
Dry Run (generate fix script only):

bash
./repo-hygiene.sh -c config.json
This creates a fix-script.sh (or the file specified in your config) containing commented status blocks and active fix commands for any missing items.

Apply Fixes Immediately:

bash
./repo-hygiene.sh -c config.json --apply
This runs the above process and then immediately executes the generated fix script.

Example Directory Layout
Suppose you have the following structure:

.
├── config.json
├── model-repo/ # Your "gold-standard" repository
│ ├── .git/
│ ├── .gitignore
│ ├── pre-commit.yaml
│ ├── .vscode/
│ │ └── extensions.json
│ └── harness/
├── repo-hygiene.sh
└── repos/ # scan_dir
├── Team1/
│ ├── repoA/ # Git repo (e.g., missing some required items)
│ └── repoB/ # Another Git repo
└── Team2/
└── repoC/ # Git repo to be updated
The script will recursively scan the repos directory, handle nested structures (like Team1 and Team2), and update only the repositories that are found.

How It Works
Dependency Check: The script first checks if jq is installed.

Load Config: It then reads the configuration from config.json (including the scan directory, model repository, output file name, and required items).

Backup Existing File: If the output file already exists, it is backed up with a timestamp.

Recursive Scan: The script uses the find command to locate all .git directories within scan_dir. The repository root is determined by taking the parent directory of each .git folder.

Status Block: For each repository, a commented block is written to the fix script showing:

For directories: Whether each required directory exists.

For files: Whether the file exists, including a comparison of the line count in that file versus the model file.

Active Fix Commands: If any required item is missing, active commands to create missing directories and copy missing files from the model repository are written.

Optional Apply: If --apply is supplied, the fixer script is executed immediately.

Output: The generated fix script is made executable.

Testing the Script
You can test the script with the following steps:

Set up a test environment:

bash

# Create a sample model repository.

mkdir model-repo && cd model-repo
git init -q
echo -e "line1\nline2\nline3" > .gitignore
echo -e "step1\nstep2\nstep3\nstep4" > pre-commit.yaml
mkdir -p .vscode && echo '{"foo": 1}' > .vscode/extensions.json
cd ..

# Create target repositories under the scan directory.

mkdir -p repos/Team1/repoA repos/Team1/repoB repos/Team2/repoC

# Initialize Git in each target repository.

for d in repos/Team1/repoA repos/Team1/repoB repos/Team2/repoC; do
(cd "$d" && git init -q)
done

# Create a configuration file.

cat > config.json <<EOF
{ "scan_dir": "repos", "model_repo": "model-repo", "output_file": "fix-script.sh", "required_dirs": [".vscode",".github"], "required_files": [".gitignore","pre-commit.yaml",".vscode/extensions.json"] } EOF

2. **Run a dry run (generate only):**

```bash
./repo-hygiene.sh -c config.json
cat fix-script.sh
The generated fix-script.sh will include commented status blocks for each repository along with active commands for missing items.
```

Apply Fixes Immediately:

```bash
./repo-hygiene.sh -c config.json --apply
tree -a
```

This will update the target repositories (e.g., create missing directories and copy missing files from model-repo).

---

### Explanation Summary

- **Dependencies:** The script checks that `jq` is installed and provides installation tips if not.
- **Configuration:** All settings including the starting scan directory, model repository, and output filename are provided via a JSON file.
- **Recursive Scanning:** The script scans the entire tree under `scan_dir` using `find` and handles nested team structures.
- **Backup and Output:** An existing output file is automatically backed up using a timestamp.
- **Status and Fixes:** For each Git repository found (excluding the model repo), the script writes a commented status block (with file line count comparisons) and active commands to fix missing items.
- **Optional Immediate Apply:** The `--apply` option allows you to run the generated fix script immediately.
