#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

# Show help
usage() {
  cat <<EOF
Usage: ${0##*/} -i <config.json> [-o <fix-script.sh>] [--apply] [-h]
  -i <file>     JSON config file (required)
  -o <file>     Output fix-script (default: fix-script.sh)
  --apply       Run fix-script after generation
  -h            Show help
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
    *) echo "Unknown arg: $1" >&2; usage 1 ;;
  esac
done

# 2) Validate inputs
[[ -n $CONFIG ]] || { echo "ERROR: -i <config.json> is required." >&2; exit 1; }
[[ -f $CONFIG ]]   || { echo "ERROR: '$CONFIG' not found." >&2; exit 2; }
command -v jq >/dev/null || { echo "ERROR: 'jq' is required." >&2; exit 3; }

# 3) Load JSON settings
MODEL_REPO=$(jq -r '.model_repo // empty' "$CONFIG")
[[ -n $MODEL_REPO ]] || { echo "ERROR: 'model_repo' missing." >&2; exit 4; }
mapfile -t REQUIRED_DIRS  < <(jq -r '.required_dirs[]'  "$CONFIG")
mapfile -t REQUIRED_FILES < <(jq -r '.required_files[]' "$CONFIG")
[[ -d $MODEL_REPO/.git ]] || { echo "ERROR: '$MODEL_REPO' is not a git repo." >&2; exit 5; }

# 4) Backup existing fix-script
if [[ -f "$OUTFILE" ]]; then
  ts=$(date +%Y%m%d_%H%M%S)
  mv "$OUTFILE" "${OUTFILE}.${ts}.bak"
  echo "Backed up old script to ${OUTFILE}.${ts}.bak"
fi

# 5) Write fresh fix-script header
cat > "$OUTFILE" <<EOF
#!/usr/bin/env bash
# Auto-generated fix script — DO NOT EDIT
# Model repo : $MODEL_REPO
# Generated on: $(date --rfc-3339=seconds)

EOF

# 6) Scan each Git repo subfolder
for repo in */; do
  [[ -d $repo/.git ]] || continue

  present_dirs=(); missing_dirs=()
  declare -A file_lines
  missing_files=()

  for d in "${REQUIRED_DIRS[@]}"; do
    [[ -d "${repo%/}/$d" ]] && present_dirs+=("$d") || missing_dirs+=("$d")
  done

  for f in "${REQUIRED_FILES[@]}"; do
    RP="$repo$f"; MP="$MODEL_REPO/$f"
    if [[ -f $RP ]]; then
      rl=$(wc -l < "$RP" | tr -d ' ')
      ml=$(wc -l < "$MP" | tr -d ' ')
      file_lines["$f"]="$rl:$ml"
    else
      missing_files+=("$f")
    fi
  done

  # 7) Commented status block
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

  # 8) Emit fix commands
  if (( ${#missing_dirs[@]} + ${#missing_files[@]} )); then
    {
      echo "echo \">> Updating $repo\""
      echo "echo \" Missing dirs : ${missing_dirs[*]}\""
      echo "echo \" Missing files: ${missing_files[*]}\""
      echo
      for d in "${missing_dirs[@]}"; do
        echo "mkdir -p \"$repo$d\""
        echo "cp -r \"$MODEL_REPO/$d\" \"$repo$d\""
      done
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
done

# 9) Finalize
chmod +x "${OUTFILE}"
echo "Fix-script generated at: ${OUTFILE}"

# 10) Optionally apply
if (( APPLY )); then
  echo "Running ${OUTFILE}…"
  ./"${OUTFILE}"
fi
