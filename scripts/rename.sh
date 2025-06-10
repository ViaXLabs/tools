#!/bin/bash

# Usage: ./rename.sh folder pipe pipes
# Usage: ./rename.sh file example.txt example-renamed.txt

MODE=$1        # Choose "file" or "folder"
OLD_NAME=$2    # Current name
NEW_NAME=$3    # New name

RENAMED=()     # Stores repos where rename occurred
NO_FOUND=()    # Stores repos where no matching file/folder was found

# Validate input
if [[ -z "$MODE" || -z "$OLD_NAME" || -z "$NEW_NAME" ]]; then
    echo "Usage: $0 <file|folder> <old_name> <new_name>"
    exit 1
fi

for repo in */; do
    if [[ -d "$repo/.git" ]]; then
        if [[ "$MODE" == "folder" ]]; then
            TARGET_PATH="$repo/$OLD_NAME"
            if [[ -d "$TARGET_PATH" ]]; then
                mv "$TARGET_PATH" "$repo/$NEW_NAME"
                RENAMED+=("$repo: $OLD_NAME → $NEW_NAME")
            else
                NO_FOUND+=("$repo")
            fi
        elif [[ "$MODE" == "file" ]]; then
            TARGET_PATH=$(find "$repo" -type f -name "$OLD_NAME" | head -n 1)
            if [[ -n "$TARGET_PATH" ]]; then
                NEW_PATH="${TARGET_PATH%/*}/$NEW_NAME"
                mv "$TARGET_PATH" "$NEW_PATH"
                RENAMED+=("$repo: $OLD_NAME → $NEW_NAME ($TARGET_PATH)")
            else
                NO_FOUND+=("$repo")
            fi
        else
            echo "Invalid MODE! Use 'file' or 'folder'."
            exit 1
        fi
    fi
done

# Display results
echo "--------------------------------"
echo "Renamed items:"
printf '%s\n' "${RENAMED[@]}"

echo "--------------------------------"
echo "Repos where '$OLD_NAME' was NOT found:"
printf '%s\n' "${NO_FOUND[@]}"
