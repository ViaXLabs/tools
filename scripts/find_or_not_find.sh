#!/bin/bash

SEARCH_STRING="ls -la"    # String to search for
TARGET_FILE="pipe*"       # File to look inside
SEARCH_MODE="find"        # Set to "find" or "not_find"

MISSING_FOLDERS=()        # Store matching repo names

for repo in */; do
    if [ -d "$repo/.git" ]; then
        FILE_PATH=$(find "$repo" -type f -name "$TARGET_FILE" | head -n 1)

        if [ -n "$FILE_PATH" ]; then
            case "$SEARCH_MODE" in
                "find")
                    if grep -q "$SEARCH_STRING" "$FILE_PATH"; then
                        echo "'$SEARCH_STRING' FOUND in: $repo"
                    else
                        echo "'$SEARCH_STRING' NOT found in: $repo"
                        MISSING_FOLDERS+=("$repo")
                    fi
                    ;;
                "not_find")
                    if ! grep -q "$SEARCH_STRING" "$FILE_PATH"; then
                        echo "'$SEARCH_STRING' NOT present in: $repo"
                    else
                        echo "'$SEARCH_STRING' FOUND in: $repo"
                        MISSING_FOLDERS+=("$repo")
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

# List all repos that matched the condition
echo "--------------------------------"
echo "Folders meeting '$SEARCH_MODE' condition for '$SEARCH_STRING':"
printf '%s\n' "${MISSING_FOLDERS[@]}"
