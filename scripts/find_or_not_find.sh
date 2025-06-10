#!/bin/bash

SEARCH_STRING="ls -la"    # String to search for
TARGET_FILE="pipe*"       # File pattern to search

FOUND_BOTH=()      # Stores repos where both the file AND string were found
FOUND_FILE_ONLY=() # Stores repos where file was found but NOT the string
NO_FILE_FOUND=()   # Stores repos where NO matching file was found

for repo in */; do
    if [ -d "$repo/.git" ]; then
        FILE_PATH=$(find "$repo" -type f -name "$TARGET_FILE" | head -n 1)

        if [ -n "$FILE_PATH" ]; then
            if grep -q "$SEARCH_STRING" "$FILE_PATH"; then
                FOUND_BOTH+=("$repo")
            else
                FOUND_FILE_ONLY+=("$repo")
            fi
        else
            NO_FILE_FOUND+=("$repo")
        fi
    fi
done

# Display categorized results
echo "--------------------------------"
echo "Repos where BOTH '$SEARCH_STRING' AND '$TARGET_FILE' were found:"
printf '%s\n' "${FOUND_BOTH[@]}"

echo "--------------------------------"
echo "Repos where '$TARGET_FILE' was found, BUT '$SEARCH_STRING' was MISSING:"
printf '%s\n' "${FOUND_FILE_ONLY[@]}"

echo "--------------------------------"
echo "Repos where NO '$TARGET_FILE' was found:"
printf '%s\n' "${NO_FILE_FOUND[@]}"
