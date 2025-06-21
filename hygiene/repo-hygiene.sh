#!/usr/bin/env bash
# Exit on errors, unset vars, and pipeline failures
set -euo pipefail
IFS=$'\n\t'

# Print usage and exit
usage() {
  cat <<EOF
Usage: ${0##*/} -i <config.json> [-o <outfile>] [--apply] [-h]

  -i <file>     JSON config file (required)
  -o <file>     Report output path (default: hygiene-report.txt)
  --apply       Automatically copy missing items from model repo
  -h            Show this help and exit
EOF
  exit "${1:-0}"
}

# 1) Parse command‐line arguments
CONFIG=""
OUTFILE="hygiene-report.txt"
APPLY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -i) CONFIG=$2; shift 2 ;;
    -o) OUTFILE=$2; shift 2 ;;
    --apply) APPLY=1; shift ;;
    -h) usage 0 ;;
    *) echo "Unknown argument: $1" >&2; usage 1 ;;
  esac
done

# 2) Validate inputs
[[ -n $CONFIG ]] || { echo "ERROR: -i <config.json> is required" >&2; usage 1; }
[[ -f $CONFIG ]]   || { echo "ERROR: Config '$CONFIG' does not exist" >&2; exit 2; }
command -v jq >/dev/null || { echo "ERROR: 'jq' is required" >&2; exit 3; }

# 3) Load JSON configuration
MODEL_REPO=$(jq -r '.model_repo // empty' "$CONFIG")
[[ -n $MODEL_REPO ]] || { echo "ERROR: 'model_repo' missing in config" >&2; exit 4; }

# Read arrays of dirs and files from JSON
mapfile -t REQUIRED_DIRS  < <(jq -r '.required_dirs[]'  "$CONFIG")
mapfile -t REQUIRED_FILES < <(jq -r '.required_files[]' "$CONFIG")

# Ensure model repo is a Git repo
[[ -d $MODEL_REPO/.git ]] || { echo "ERROR: '$MODEL_REPO' is not a git repo" >&2; exit 5; }

# 4) Initialize the report
> "$OUTFILE"
{
  echo "Repository Hygiene Report"
  echo "Model repo: $MODEL_REPO"
  echo "Checked on: $(date --rfc-3339=seconds)"
  echo
} >> "$OUTFILE"

# 5) Iterate each subdirectory that contains .git
for repo in */; do
  [[ -d $repo/.git ]] || continue

  # Arrays for present vs. missing items
  present_dirs=();  missing_dirs=()
  present_files=(); missing_files=()
  declare -A file_line_counts

  # Check required directories
  for dir in "${REQUIRED_DIRS[@]}"; do
    if [[ -d "${repo%/}/$dir" ]]; then
      present_dirs+=("$dir")
    else
      missing_dirs+=("$dir")
    fi
  done

  # Check required files, count lines, compare to model
  for file in "${REQUIRED_FILES[@]}"; do
    local_repo_path="$repo$file"
    model_repo_path="$MODEL_REPO/$file"
    if [[ -f $local_repo_path ]]; then
      present_files+=("$file")
      repo_lines=$(wc -l < "$local_repo_path"  | tr -d ' ')
      model_lines=$(wc -l < "$model_repo_path" | tr -d ' ')
      file_line_counts["$file"]="$repo_lines:$model_lines"
    else
      missing_files+=("$file")
    fi
  done

  # Append this repo’s section to the report
  {
    echo "----------------------------------------"
    echo "Repo: $repo"

    # Present directories
    echo "  PRESENT DIRECTORIES:"
    if (( ${#present_dirs[@]} )); then
      for d in "${present_dirs[@]}"; do echo "    - $d"; done
    else
      echo "    (none)"
    fi

    # Present files with line counts vs. model
    echo "  PRESENT FILES (with line counts vs. model):"
    if (( ${#present_files[@]} )); then
      for f in "${present_files[@]}"; do
        IFS=':' read -r rl ml <<< "${file_line_counts[$f]}"
        echo "    - $f : $rl lines (model: $ml)"
      done
    else
      echo "    (none)"
    fi

    # Missing directories
    echo "  MISSING DIRECTORIES:"
    if (( ${#missing_dirs[@]} )); then
      for d in "${missing_dirs[@]}"; do echo "    - $d"; done
    else
      echo "    (none)"
    fi

    # Missing files
    echo "  MISSING FILES:"
    if (( ${#missing_files[@]} )); then
      for f in "${missing_files[@]}"; do echo "    - $f"; done
    else
      echo "    (none)"
    fi

    # Generate fix commands
    echo "  FIX COMMANDS:"
    if (( ${#missing_dirs[@]} + ${#missing_files[@]} )); then
      for d in "${missing_dirs[@]}"; do
        echo "    cp -r \"$MODEL_REPO/$d\" \"$repo$d\""
      done
      for f in "${missing_files[@]}"; do
        dirpath=$(dirname "$f")
        [[ $dirpath != "." ]] && echo "    mkdir -p \"$repo$dirpath\""
        echo "    cp \"$MODEL_REPO/$f\" \"$repo$f\""
      done
    else
      echo "    (nothing to copy)"
    fi

    echo
  } >> "$OUTFILE"

  # 6) Optionally apply the fixes right now
  if (( APPLY )); then
    for d in "${missing_dirs[@]}"; do
      cp -r "$MODEL_REPO/$d" "$repo$d"
    done
    for f in "${missing_files[@]}"; do
      dirpath=$(dirname "$f")
      [[ $dirpath != "." ]] && mkdir -p "$repo$dirpath"
      cp "$MODEL_REPO/$f" "$repo$f"
    done
  fi
done

echo "Done. Report written to: $OUTFILE"
(( APPLY )) && echo "Missing items have been copied into each repo."
