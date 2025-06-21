#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

# Print usage and exit
usage() {
  cat <<EOF
Usage: ${0##*/} -i <config.json> [-o <fix-script.sh>] [--apply] [-h]
  -i <file>     JSON config file (required)
  -o <file>     Output fix-script (default: fix-script.sh)
  --apply       Execute fix-script after generation
  -h            Show this help and exit
EOF
  exit "${1:-0}"
}

# 1) Parse flags
CONFIG=""; OUTFILE="fix-script.sh"; APPLY=0
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
[[ -n $CONFIG ]] || { echo "ERROR: -i <config.json> is required." >&2; usage 1; }
[[ -f $CONFIG ]]   || { echo "ERROR: '$CONFIG' not found." >&2; exit 2; }
command -v jq >/dev/null || { echo "ERROR: 'jq' is required." >&2; exit 3; }

# 3) Load JSON settings
MODEL_REPO=$(jq -r '.model_repo // empty' "$CONFIG")
[[ -n $MODEL_REPO ]] || { echo "ERROR: 'model_repo' missing." >&2; exit 4; }
mapfile -t REQUIRED_DIRS  < <(jq -r '.required_dirs[]'  "$CONFIG")
mapfile -t REQUIRED_FILES < <(jq -r '.required_files[]' "$CONFIG")
[[ -d $MODEL_REPO/.git ]] || { echo "ERROR: '$MODEL_REPO' is not a git repo." >&2; exit 5; }

# 4) Initialize fix-script
cat > "$OUTFILE" <<EOF
#!/usr/bin/env bash
# Auto-generated fix script – DO NOT EDIT
# Model repo : $MODEL_REPO
# Generated on: $(date --rfc-3339=seconds)

EOF

# 5) Scan each Git repo subfolder
for repo in */; do
  [[ -d $repo/.git ]] || continue

  present_dirs=();  missing_dirs=()
  present_files=(); missing_files=()

  # Check for each required directory
  for d in "${REQUIRED_DIRS[@]}"; do
    [[ -d "${repo%/}/$d" ]] && present_dirs+=("$d") || missing_dirs+=("$d")
  done

  # Check for each required file
  for f in "${REQUIRED_FILES[@]}"; do
    if [[ -f "$repo$f" ]]; then
      present_files+=("$f")
    else
      missing_files+=("$f")
    fi
  done

  # Only generate actions if something is missing
  if (( ${#missing_dirs[@]} + ${#missing_files[@]} )); then
    echo "# Repo: $repo"                                          >> "$OUTFILE"
    echo "echo \"=> Updating $repo\""                            >> "$OUTFILE"
    echo "echo \"   Missing dirs : ${missing_dirs[*]}\""         >> "$OUTFILE"
    echo "echo \"   Missing files: ${missing_files[*]}\""        >> "$OUTFILE"
    echo                                                         >> "$OUTFILE"

    # Create & copy missing directories
    for d in "${missing_dirs[@]}"; do
      echo "mkdir -p \"$repo$d\""                                >> "$OUTFILE"
      echo "cp -r \"$MODEL_REPO/$d\" \"$repo$d\""                 >> "$OUTFILE"
    done

    # Create parent folders & copy missing files
    for f in "${missing_files[@]}"; do
      dirpath=\$(dirname "$f")
      [[ \$dirpath != "." ]] && echo "mkdir -p \"$repo\$dirpath\"" >> "$OUTFILE"
      echo "cp \"$MODEL_REPO/$f\" \"$repo$f\""                      >> "$OUTFILE"
    done
    echo                                                        >> "$OUTFILE"
  else
    # No fix needed—commented out
    echo "# Repo: $repo is already compliant – no actions needed." >> "$OUTFILE"
    echo                                                        >> "$OUTFILE"
  fi
done

# 6) Finalize
chmod +x "$OUTFILE"
echo "Fix-script generated: $OUTFILE"

# 7) Optionally apply immediately
if (( APPLY )); then
  echo "Running fix-script..."
  ./"$OUTFILE"
fi
