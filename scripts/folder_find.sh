#!/bin/bash

TARGET_FOLDER="your-folder-pattern*"   # Change this to the folder name pattern you want to search

FOUND_FOLDER=()       # Stores repositories where the folder was found
NO_FOLDER_FOUND=()    # Stores repositories where no matching folder was found
FOUND_FOLDER_PATHS=() # Stores the discovered folder paths

for repo in */; do
    if [ -d "$repo/.git" ]; then
        # Search for the directory matching the pattern within the repo
        FOLDER_PATH=$(find "$repo" -type d -name "$TARGET_FOLDER" | head -n 1)

        if [ -n "$FOLDER_PATH" ]; then
            FOUND_FOLDER+=("$repo")
            FOUND_FOLDER_PATHS+=("$FOLDER_PATH")
        else
            NO_FOLDER_FOUND+=("$repo")
        fi
    fi
done

# Display categorized results
echo "--------------------------------"
echo "Repos where folder matching '$TARGET_FOLDER' was found:"
for i in "${!FOUND_FOLDER[@]}"; do
    echo "${FOUND_FOLDER[i]} - ${FOUND_FOLDER_PATHS[i]}"
done

echo "--------------------------------"
echo "Repos where NO folder matching '$TARGET_FOLDER' was found:"
printf '%s\n' "${NO_FOLDER_FOUND[@]}"
