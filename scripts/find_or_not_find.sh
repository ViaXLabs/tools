#!/bin/bash

SEARCH_STRING="ls -la"    # String to search for
TARGET_FILE="pipe*"       # File pattern to search
SEARCH_MODE="find"        # Set to "find" (ensure presence) or "not_find" (ensure absence)

MATCHING_FOLDERS=()       # Stores repositories meeting the condition

for repo in */; do
    if [ -d "$repo/.git" ]; then
        FILE_PATH=$(find "$repo" -type f -name "$TARGET_FILE" | head -n 1)

        if [ -n "$FILE_PATH" ]; then
            case "$SEARCH_MODE" in
                "find")
                    if grep -q "$SEARCH_STRING" "$FILE_PATH"; then
                        echo "'$SEARCH_STRING' FOUND in: $repo"
                        MATCHING_FOLDERS+=("$repo")
                    fi
                    ;;
                "not_find")
                    if ! grep -q "$SEARCH_STRING" "$FILE_PATH"; then
                        echo "'$SEARCH_STRING' NOT found in: $repo"
                        MATCHING_FOLDERS+=("$repo")
                    fi
                    ;;
                *)
                    echo "Invalid SEARCH_MODE. Use 'find' or 'not_find'."
                    exit 1
                    ;;
            esac
        else
            echo "No matching file ($TARGET_FILE) found in: $repo"
        fi
    fi
done

# List all repositories that met the condition
echo "--------------------------------"
if [ "${#MATCHING_FOLDERS[@]}" -gt 0 ]; then
    echo "Repositories matching '$SEARCH_MODE' condition for '$SEARCH_STRING':"
    printf '%s\n' "${MATCHING_FOLDERS[@]}"
else
    echo "No repositories matched the condition."
fi
