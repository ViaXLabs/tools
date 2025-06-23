#!/bin/bash
# repo-hygiene.sh
#
# This script recursively scans a directory tree for Git repositories,
# compares each repository against a "model" (gold-standard) repository, and
# generates a self-contained fix script to update any missing files (which will be copied)
# and directories (which are merely created) based on the configuration provided in a JSON file.
#
# All settings come from a JSON configuration file.
#
# Dependencies:
#   - GNU Bash (compatible with Bash 3.2)
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
# Function to expand '~' at the beginning of a path to the user's HOME directory.
# If the configuration file gives a path like "~/<something>", it is converted to "$HOME/<something>".
expand_tilde() {
  [[ "$1" == ~* ]] && echo "${1/#\~/$HOME}" || echo "$1"
}

# -----------------------------------------------------------------------------
# Function to restore the tilde in a path for output.
# When outputting paths in the generated script, any path that falls within $HOME is displayed with "~".
restore_home() {
  local path="$1"
  if [[ "$path" == "$HOME"* ]]; then
    echo "~${path#$HOME}"
  else
    echo "$path"
  fi
}

# -----------------------------------------------------------------------------
# Function to join two paths, ensuring a single "/" separator.
join_path() {
  local base="$1"
  local rel="$2"
  base="${base%/}"
  rel="${rel#/}"
  echo "$base/$rel"
}

# -----------------------------------------------------------------------------
# Function to join array elements with a given delimiter.
join_by() {
  local delimiter="$1"
  shift
  echo "$*"
}

# -----------------------------------------------------------------------------
# Function to return the absolute path of a directory.
abspath() {
  cd "$1" && pwd
}

# -----------------------------------------------------------------------------
# Usage: display help and exit.
usage() {
  cat <<EOF
Usage: ${0##*/} -c <config.json> [-o <output_fix_script>] [--apply] [-h]

  -c <file>   Path to the JSON config file (required).
  -o <file>   Output fix script file (default: repo-hygiene-fix.sh).
  --apply     After generating the fix script, run it immediately to apply fixes.
  -h          Show this help message and exit.

The JSON config must include:
  scan_dir       : Starting directory to scan for Git repositories.
  model_repo     : Path to your gold-standard repository.
  output_file    : Name for the generated fix script.
  required_dirs  : Array of directories each repository must contain.
  required_files : Array of files (including dotfiles and nested paths) each repository must have.

Example config.json:
{
  "scan_dir": "~/repos",
  "model_repo": "~/model-repo",
  "output_file": "repo-hygiene-fix.sh",
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
    -c) CONFIG=$2; shift 2 ;;
    -o) OUTFILE=$2; shift 2 ;;
    --apply) APPLY=1; shift ;;
    -h) usage 0 ;;
    *) echo "Unknown argument: $1" >&2; usage 1 ;;
  esac
done

# -----------------------------------------------------------------------------
# 2) Validate inputs and set defaults.
[[ -n "$CONFIG" ]] || { echo "ERROR: -c <config.json> is required." >&2; exit 1; }
[[ -f "$CONFIG" ]] || { echo "ERROR: Config file '$CONFIG' not found." >&2; exit 2; }
if [[ -z "$OUTFILE" ]]; then
  OUTFILE=$(jq -r '.output_file // "repo-hygiene-fix.sh"' "$CONFIG")
fi

# -----------------------------------------------------------------------------
# Expand '~' in important paths.
SCAN_DIR=$(expand_tilde "$(jq -r '.scan_dir // empty' "$CONFIG")")
MODEL_REPO=$(expand_tilde "$(jq -r '.model_repo // empty' "$CONFIG")")
OUTFILE=$(expand_tilde "$OUTFILE")

# -----------------------------------------------------------------------------
# 3) Load arrays for required directories and files from JSON.
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
[[ -d "$SCAN_DIR" ]] || { echo "ERROR: scan_dir '$SCAN_DIR' not found." >&2; exit 4; }
[[ -d "$(join_path "$MODEL_REPO" ".git")" ]] || { echo "ERROR: model_repo '$MODEL_REPO' is not a Git repo." >&2; exit 5; }

# -----------------------------------------------------------------------------
# 4) Backup existing output file if it already exists.
if [[ -f "$OUTFILE" ]]; then
  ts=$(date +%Y%m%d_%H%M%S)
  backup="${OUTFILE}.${ts}.bak"
  echo "Backing up existing '$OUTFILE' → '$backup'"
  mv -- "$OUTFILE" "$backup"
fi

# -----------------------------------------------------------------------------
# 5) Write the header for the new fix script.
cat > "$OUTFILE" <<EOF
#!/bin/bash
# Auto-generated fix script — DO NOT EDIT
# scan_dir    : $(restore_home "$SCAN_DIR")
# model_repo  : $(restore_home "$MODEL_REPO")
# Generated on: $(date +"%Y-%m-%dT%H:%M:%S")
EOF

# -----------------------------------------------------------------------------
# 6) Recursively scan SCAN_DIR for Git repositories.
while IFS= read -r gitdir; do
  repo=$(dirname "$gitdir")

  # Skip if this repository's absolute path begins with the model_repo's absolute path.
  if echo "`abspath "$repo"`" | grep -q "^`abspath "$MODEL_REPO"`"; then
    continue
  fi

  # Explicitly initialize arrays for each repository iteration.
  present_dirs=()
  missing_dirs=()
  missing_files=()
  FILE_RESULTS=()

  # -----------------------------------------------------------------------------
  # 7) Check required directories.
  for d in "${REQUIRED_DIRS[@]}"; do
    dir_path=$(join_path "$repo" "$d")
    if [[ -d "$dir_path" ]]; then
      present_dirs+=("$d")
    else
      missing_dirs+=("$d")
    fi
  done

  # -----------------------------------------------------------------------------
  # 8) Check required files.
  for f in "${REQUIRED_FILES[@]}"; do
    file_path=$(join_path "$repo" "$f")
    model_file=$(join_path "$MODEL_REPO" "$f")
    if [[ -f "$file_path" ]]; then
      rl=$(wc -l < "$file_path" | tr -d ' ')
      ml=$(wc -l < "$model_file" | tr -d ' ')
      # If line counts are equal, also get file sizes.
      if [ "$rl" -eq "$ml" ]; then
        rs=$(wc -c < "$file_path" | tr -d ' ')
        ms=$(wc -c < "$model_file" | tr -d ' ')
        FILE_RESULTS+=("$rl:$ml:$rs:$ms")
      else
        FILE_RESULTS+=("$rl:$ml")
      fi
    else
      FILE_RESULTS+=("")
      missing_files+=("$f")
    fi
  done

  # -----------------------------------------------------------------------------
  # 9) Emit a commented status block for this repository.
  {
    echo "# ───────────────────────────────────────"
    echo "# Repo: $(restore_home "$repo")"
    echo "#   Directories:"
    for d in "${REQUIRED_DIRS[@]}"; do
      if [[ " ${present_dirs[*]:-} " == *" $d "* ]]; then
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
        field_count=$(echo "$result" | awk -F: '{print NF}')
        if [ "$field_count" -eq 4 ]; then
          rl=$(echo "$result" | cut -d: -f1)
          ml=$(echo "$result" | cut -d: -f2)
          rs=$(echo "$result" | cut -d: -f3)
          ms=$(echo "$result" | cut -d: -f4)
          echo "#     + FILE $f exists (model lines: $ml vs scanned file: $rl; model size: $ms bytes vs scanned file: $rs bytes)"
        else
          rl=$(echo "$result" | cut -d: -f1)
          ml=$(echo "$result" | cut -d: -f2)
          echo "#     + FILE $f exists (model lines: $ml vs scanned file: $rl)"
        fi
      else
        echo "#     – FILE $f missing"
      fi
      i=$((i+1))
    done
    echo "#"
  } >> "$OUTFILE"

  # -----------------------------------------------------------------------------
  # 10) Emit active fix commands if any required items are missing.
  total_missing=$(expr ${#missing_dirs[@]:-} + ${#missing_files[@]:-})
  if [ "$total_missing" -gt 0 ]; then
    {
      echo "echo \">> Updating $(restore_home "$repo")\""
      echo "echo \"Missing dirs:\""
      for d in "${missing_dirs[@]:-}"; do
        echo "echo \"  $d\""
      done
      echo "echo \"Missing files:\""
      for f in "${missing_files[@]:-}"; do
        echo "echo \"  $f\""
      done
      echo
      for d in "${missing_dirs[@]:-}"; do
        dir_path=$(join_path "$repo" "$d")
        # For missing directories, only create the directory.
        echo "mkdir -p $(restore_home "$dir_path")"
      done
      for f in "${missing_files[@]:-}"; do
        dest=$(join_path "$repo" "$f")
        dp=`dirname "$dest"`
        if [ "$dp" != "$repo" ]; then
          echo "mkdir -p $(restore_home "$dp")"
        fi
        echo "cp $(restore_home "$(join_path "$MODEL_REPO" "$f")") $(restore_home "$dest")"
      done
      echo
    } >> "$OUTFILE"
  else
    echo "# Repo: $(restore_home "$repo") is fully compliant — no fixes needed." >> "$OUTFILE"
    echo >> "$OUTFILE"
  fi

  # -----------------------------------------------------------------------------
  # 10.5) Emit a divider line to separate repository blocks.
  echo "echo \"=======================================================\"" >> "$OUTFILE"

done < <(find "$SCAN_DIR" -type d -name ".git")

# -----------------------------------------------------------------------------
# 11) Finalize the fix script by making it executable.
chmod +x "$OUTFILE"
echo "Fix-script generated at: $(restore_home "$OUTFILE")"

# -----------------------------------------------------------------------------
# 12) Optionally, apply the fix script immediately.
if [ "${APPLY:-0}" -eq 1 ]; then
  echo "Running $(restore_home "$OUTFILE")..."
  ./"$OUTFILE"
fi
