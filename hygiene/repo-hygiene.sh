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
