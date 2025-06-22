#!/usr/bin/env bash
# repo-hygiene.sh
#
# This script scans a directory tree for Git repositories, compares each
# repository against a "model" repository (the gold standard), and generates
# a self-contained fix script to update any missing files or directories.
#
# All configuration is provided via a JSON file.
#
# Dependencies:
#   - GNU bash 4+
#   - jq (for JSON parsing)
#
# If 'jq' is not installed, the script prints installation instructions and exits.

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
# Function to expand '~' to $HOME if the path starts with '~'
expand_tilde() {
  # If the first character is '~', substitute it with $HOME.
  [[ "$1" == ~* ]] && echo "${1/#\~/$HOME}" || echo "$1"
}

# -----------------------------------------------------------------------------
# Usage: show help and exit.
usage() {
  cat <<EOF
Usage: ${0##*/} -c <config.json> [-o <output_fix_script>] [--apply] [-h]

  -c <file>   Path to JSON config file (required)
  -o <file>   Output fix script file (default: value of "output_file" in config)
  --apply     After generating fix script, run it immediately to apply fixes
  -h          Show this help message and exit

The JSON config must include:
  scan_dir       : Starting directory to scan for Git repositories.
  model_repo     : Path to your gold-standard repository.
  output_file    : Name for the generated fix script.
  required_dirs  : Array of directories that each repo must contain.
  required_files : Array of files (including dot-files and nested paths) that each repo must have.

Example config.json:
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
    -c) CONFIG=$2; shift 2 ;;
    -o) OUTFILE=$2; shift 2 ;;
    --apply) APPLY=1; shift ;;
    -h) usage 0 ;;
    *) echo "Unknown argument: $1" >&2; usage 1 ;;
  esac
done

# -----------------------------------------------------------------------------
# 2) Validate inputs and set defaults.
[[ -n $CONFIG ]] || { echo "ERROR: -c <config.json> is required." >&2; exit 1; }
[[ -f $CONFIG ]] || { echo "ERROR: Config file '$CONFIG' not found." >&2; exit 2; }

# If OUTFILE wasn’t provided via command-line, load it from config.
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
# Use readarray as a replacement for mapfile.
readarray -t REQUIRED_DIRS < <(jq -r '.required_dirs[]' "$CONFIG")
readarray -t REQUIRED_FILES < <(jq -r '.required_files[]' "$CONFIG")

# Validate that SCAN_DIR and MODEL_REPO are provided.
for var in SCAN_DIR MODEL_REPO; do
  [[ -n "${!var}" ]] || { echo "ERROR: '$var' missing in config." >&2; exit 3; }
done

[[ -d $SCAN_DIR ]] || { echo "ERROR: scan_dir '$SCAN_DIR' not found." >&2; exit 4; }
[[ -d $MODEL_REPO/.git ]] || { echo "ERROR: model_repo '$MODEL_REPO' is not a Git repo." >&2; exit 5; }

# -----------------------------------------------------------------------------
# 4) Backup existing output file if one exists.
if [[ -f $OUTFILE ]]; then
  ts=$(date +%Y%m%d_%H%M%S)
  backup="${OUTFILE}.${ts}.bak"
  echo "Backing up existing '$OUTFILE' → '$backup'"
  mv -- "$OUTFILE" "$backup"
fi

# -----------------------------------------------------------------------------
# 5) Write the header of the new fix script.
cat > "$OUTFILE" <<EOF
#!/usr/bin/env bash
# Auto-generated fix script — DO NOT EDIT
# scan_dir    : $SCAN_DIR
# model_repo  : $MODEL_REPO
# Generated on: $(date --rfc-3339=seconds)

EOF

# -----------------------------------------------------------------------------
# 6) Recursively scan SCAN_DIR for Git repositories.
#     We use the find command to locate all ".git" directories.
while IFS= read -r gitdir; do
  repo=$(dirname "$gitdir")

  # Skip if the repository is the model_repo (if its path begins with model_repo).
  if [[ "$(realpath "$repo")" == "$(realpath "$MODEL_REPO")"* ]]; then
    continue
  fi

  # Initialize arrays to track present vs. missing items.
  present_dirs=(); missing_dirs=()
  declare -A file_lines  # Maps filename -> "repoLines:modelLines"
  missing_files=()

  # Check required directories.
  for d in "${REQUIRED_DIRS[@]}"; do
    if [[ -d "$repo$d" ]]; then
      present_dirs+=("$d")
    else
      missing_dirs+=("$d")
    fi
  done

  # Check required files and record line counts if they exist.
  for f in "${REQUIRED_FILES[@]}"; do
    rp="$repo$f"           # Path in the target repo.
    mp="$MODEL_REPO/$f"    # Path in the model repo.
    if [[ -f $rp ]]; then
      rl=$(wc -l < "$rp" | tr -d ' ')
      ml=$(wc -l < "$mp" | tr -d ' ')
      file_lines["$f"]="$rl:$ml"
    else
      missing_files+=("$f")
    fi
  done

  # -----------------------------------------------------------------------------
  # 7) Emit a commented status block for this repository.
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
    for f in "${REQUIRED_FILES[@]}"; do
      if [[ -n ${file_lines[$f]:-} ]]; then
        IFS=':' read -r rl ml <<< "${file_lines[$f]}"
        echo "#     + FILE $f exists ($rl vs $ml)"
      else
        echo "#     – FILE $f missing"
      fi
    done
    echo "#"
  } >> "$OUTFILE"

  # -----------------------------------------------------------------------------
  # 8) Emit active fix commands if required items are missing.
  if (( ${#missing_dirs[@]} + ${#missing_files[@]} )); then
    {
      echo "echo \">> Updating $repo\""
      echo "echo \" Missing dirs : ${missing_dirs[*]}\""
      echo "echo \" Missing files: ${missing_files[*]}\""
      echo
      # For each missing directory, create it and copy from the model repository.
      for d in "${missing_dirs[@]}"; do
        echo "mkdir -p \"$repo$d\""
        echo "cp -r \"$MODEL_REPO/$d\" \"$repo$d\""
      done
      # For each missing file, create necessary parent directories and copy the file.
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
# 9) Finalize: make the output fix script executable.
chmod +x "${OUTFILE}"
echo "Fix-script generated at: ${OUTFILE}"

# -----------------------------------------------------------------------------
# 10) Optionally, apply the fix script immediately.
if [[ "${APPLY:-0}" -eq 1 ]]; then
  echo "Running ${OUTFILE}..."
  ./"${OUTFILE}"
fi
