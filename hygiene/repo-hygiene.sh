#!/usr/bin/env bash
# repo-hygiene.sh
#
# This script recursively scans a directory tree for Git repositories,
# compares each repository against a "model" (gold-standard) repository, and
# generates a self-contained fix script to update any missing files or directories.
#
# All settings are provided via a JSON configuration file.
#
# Dependencies:
#   - GNU Bash (compatible with Bash v3)
#   - jq (for JSON parsing)
#
# If 'jq' is not installed, the script displays installation instructions and exits.

set -euo pipefail
IFS=$'\n\t'

# -----------------------------------------------------------------------------
# Dependency check: ensure jq is installed.
if ! command -v jq >/dev/null 2>&1; then
  echo "ERROR: 'jq' is not installed." >&2
  echo "Please install it:" >&2
  echo "  Ubuntu/Debian: sudo apt-get install jq" >&2
  echo "  macOS (Homebrew): brew install jq" >&2
  echo "  Fedora/RHEL: sudo dnf install jq" >&2
  echo "  Arch Linux: sudo pacman -S jq" >&2
  exit 1
fi

# -----------------------------------------------------------------------------
# Function to expand '~' at the beginning of a path to $HOME.
expand_tilde() {
  [[ "$1" == ~* ]] && echo "${1/#\~/$HOME}" || echo "$1"
}

# -----------------------------------------------------------------------------
# Function to return the absolute path of a directory.
# (We remove extra parentheses here to avoid syntax issues in Bash v3.)
abspath() {
  cd "$1" && pwd
}

# -----------------------------------------------------------------------------
# Usage: display help and exit.
usage() {
  cat <<EOF
Usage: ${0##*/} -c <config.json> [-o <output_fix_script>] [--apply] [-h]

  -c <file>   Path to the JSON config file (required).
  -o <file>   Output fix script file (default: value of "output_file" in config).
  --apply     After generating the fix script, run it immediately to apply fixes.
  -h          Show this help message and exit.

The JSON config must include:
  scan_dir       : Starting directory to scan for Git repositories.
  model_repo     : Path to your gold-standard repository.
  output_file    : Name for the generated fix script.
  required_dirs  : Array of directories that each repository must contain.
  required_files : Array of files (including dot-files and nested paths) that each repository must have.

Example config.json:
{
  "scan_dir": "repos",
  "model_repo": "model-repo",
  "output_file": "fix-script.sh",
  "required_dirs": [".vscode", ".github", "harness"],
  "required_files": [".gitignore", "pre-commit.yaml", ".vscode/extensions.json"]
}
EOF
  exit "${1:-0}"
}

# -----------------------------------------------------------------------------
# 1) Parse command-line arguments.
CONFIG=""
OUTFILE=""
APPLY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -c)  CONFIG=$2; shift 2 ;;
    -o)  OUTFILE=$2; shift 2 ;;
    --apply) APPLY=1; shift ;;
    -h) usage 0 ;;
    *) echo "Unknown argument: $1" >&2; usage 1 ;;
  esac
done

# -----------------------------------------------------------------------------
# 2) Validate inputs and set defaults.
[[ -n $CONFIG ]] || { echo "ERROR: -c <config.json> is required." >&2; exit 1; }
[[ -f $CONFIG ]] || { echo "ERROR: Config file '$CONFIG' not found." >&2; exit 2; }
# If OUTFILE was not provided on the command-line, load it from the JSON config.
if [[ -z $OUTFILE ]]; then
  OUTFILE=$(jq -r '.output_file // "fix-script.sh"' "$CONFIG")
fi

# -----------------------------------------------------------------------------
# Expand '~' in important paths.
SCAN_DIR=$(expand_tilde "$(jq -r '.scan_dir // empty' "$CONFIG")")
MODEL_REPO=$(expand_tilde "$(jq -r '.model_repo // empty' "$CONFIG")")
OUTFILE=$(expand_tilde "$OUTFILE")

# -----------------------------------------------------------------------------
# 3) Load arrays for required directories and files from JSON.
# Bash v3 does not support readarray, so we use while-read loops.
REQUIRED_DIRS=()
while IFS= read -r line; do
  REQUIRED_DIRS+=("$line")
done < <(jq -r '.required_dirs[]' "$CONFIG")

REQUIRED_FILES=()
while IFS= read -r line; do
  REQUIRED_FILES+=("$line")
done < <(jq -r '.required_files[]' "$CONFIG")

# Validate that SCAN_DIR and MODEL_REPO are provided.
for var in SCAN_DIR MODEL_REPO; do
  [[ -n "${!var}" ]] || { echo "ERROR: '$var' missing in config." >&2; exit 3; }
done
[[ -d $SCAN_DIR ]] || { echo "ERROR: scan_dir '$SCAN_DIR' not found." >&2; exit 4; }
[[ -d $MODEL_REPO/.git ]] || { echo "ERROR: model_repo '$MODEL_REPO' is not a Git repo." >&2; exit 5; }

# -----------------------------------------------------------------------------
# 4) Backup existing output file if it already exists.
if [[ -f $OUTFILE ]]; then
  ts=$(date +%Y%m%d_%H%M%S)
  backup="${OUTFILE}.${ts}.bak"
  echo "Backing up existing '$OUTFILE' → '$backup'"
  mv -- "$OUTFILE" "$backup"
fi

# -----------------------------------------------------------------------------
# 5) Write the header for the new fix script.
# Use a portable date format (without %z for maximum compatibility).
cat > "$OUTFILE" <<EOF
#!/usr/bin/env bash
# Auto-generated fix script — DO NOT EDIT
# scan_dir    : $SCAN_DIR
# model_repo  : $MODEL_REPO
# Generated on: $(date +"%Y-%m-%dT%H:%M:%S")
EOF

# -----------------------------------------------------------------------------
# 6) Recursively scan SCAN_DIR for Git repositories.
# Use find to locate all ".git" directories.
while IFS= read -r gitdir; do
  repo=$(dirname "$gitdir")

  # Skip if the repository is inside MODEL_REPO.
  if [[ "$(abspath "$repo")" == "$(abspath "$MODEL_REPO")"* ]]; then
    continue
  fi

  # -----------------------------------------------------------------------------
  # 7) Check required directories.
  present_dirs=()
  missing_dirs=()
  for d in "${REQUIRED_DIRS[@]}"; do
    if [[ -d "$repo$d" ]]; then
      present_dirs+=("$d")
    else
      missing_dirs+=("$d")
    fi
  done

  # -----------------------------------------------------------------------------
  # 8) Check required files.
  # Use parallel index arrays since associative arrays are not supported.
  missing_files=()
  FILE_RESULTS=()  # Each element: "repo_line_count:model_line_count" or empty if missing.
  for f in "${REQUIRED_FILES[@]}"; do
    rp="$repo$f"      # Target repository file.
    mp="$MODEL_REPO/$f"  # Corresponding file in the model repository.
    if [[ -f $rp ]]; then
      rl=$(wc -l < "$rp" | tr -d ' ')
      ml=$(wc -l < "$mp" | tr -d ' ')
      FILE_RESULTS+=("$rl:$ml")
    else
      FILE_RESULTS+=("")
      missing_files+=("$f")
    fi
  done

  # -----------------------------------------------------------------------------
  # 9) Emit a commented status block for this repository.
  {
    echo "# ───────────────────────────────────────"
    echo "# Repo: $repo"
    echo "#   Directories:"
    for d in "${REQUIRED_DIRS[@]}"; do
      if [[ " ${present_dirs[*]} " == *" $d "* ]]; then
        echo "#     + DIR $d exists"
      else
        echo "#     – DIR $d missing"
      fi
    done
    echo "#   Files:"
    i=0
    for f in "${REQUIRED_FILES[@]}"; do
      result="${FILE_RESULTS[$i]}"
      if [[ -n "$result" ]]; then
        IFS=':' read -r rl ml <<< "$result"
        echo "#     + FILE $f exists ($rl vs $ml)"
      else
        echo "#     – FILE $f missing"
      fi
      i=$((i+1))
    done
    echo "#"
  } >> "$OUTFILE"

  # -----------------------------------------------------------------------------
  # 10) Emit active fix commands if any required items are missing.
  if (( ${#missing_dirs[@]} + ${#missing_files[@]} )); then
    {
      echo "echo \">> Updating $repo\""
      echo "echo \" Missing dirs : ${missing_dirs[*]}\""
      echo "echo \" Missing files: ${missing_files[*]}\""
      echo
      # For each missing directory: create it and copy it from the model repository.
      for d in "${missing_dirs[@]}"; do
        echo "mkdir -p \"$repo$d\""
        echo "cp -r \"$MODEL_REPO/$d\" \"$repo$d\""
      done
      # For each missing file: ensure its parent directory exists and copy the file.
      for f in "${missing_files[@]}"; do
        dp=\$(dirname "$f")
        [[ \$dp != "." ]] && echo "mkdir -p \"$repo\$dp\""
        echo "cp \"$MODEL_REPO/$f\" \"$repo$f\""
      done
      echo
    } >> "$OUTFILE"
  else
    echo "# Repo: $repo is fully compliant — no fixes needed." >> "$OUTFILE"
    echo >> "$OUTFILE"
  fi
done < <(find "$SCAN_DIR" -type d -name ".git")

# -----------------------------------------------------------------------------
# 11) Finalize the fix script by making it executable.
chmod +x "${OUTFILE}"
echo "Fix-script generated at: ${OUTFILE}"

# -----------------------------------------------------------------------------
# 12) Optionally, apply the fix script immediately.
if [[ "${APPLY:-0}" -eq 1 ]]; then
  echo "Running ${OUTFILE}..."
  ./"${OUTFILE}"
fi
