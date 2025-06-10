#!/bin/bash

SEARCH_STRING="your-search-string"  # Change this to the string you want to find
TARGET_FILE="your-file-pattern*"    # Change this to the file pattern you want to search

FOUND_BOTH=()        # Stores repos where the file AND string were found
FOUND_FILE_ONLY=()   # Stores repos where file was found but NOT the string
NO_FILE_FOUND=()     # Stores repos where NO matching file was found
FOUND_BOTH_FILES=()  # Stores associated file paths
FOUND_FILE_ONLY_FILES=() # Stores associated file paths

for repo in */; do
    if [ -d "$repo/.git" ]; then
        FILE_PATH=$(find "$repo" -type f -name "$TARGET_FILE" | head -n 1)

        if [ -n "$FILE_PATH" ]; then
            if grep -q "$SEARCH_STRING" "$FILE_PATH"; then
                FOUND_BOTH+=("$repo")
                FOUND_BOTH_FILES+=("$FILE_PATH")
            else
                FOUND_FILE_ONLY+=("$repo")
                FOUND_FILE_ONLY_FILES+=("$FILE_PATH")
            fi
        else
            NO_FILE_FOUND+=("$repo")
        fi
    fi
done

# Display categorized results
echo "--------------------------------"
echo "Repos where BOTH '$SEARCH_STRING' AND '$TARGET_FILE' were found:"
for i in "${!FOUND_BOTH[@]}"; do
    echo "${FOUND_BOTH[i]} - ${FOUND_BOTH_FILES[i]}"
done

echo "--------------------------------"
echo "Repos where '$TARGET_FILE' was found, BUT '$SEARCH_STRING' was MISSING:"
for i in "${!FOUND_FILE_ONLY[@]}"; do
    echo "${FOUND_FILE_ONLY[i]} - ${FOUND_FILE_ONLY_FILES[i]}"
done

echo "--------------------------------"
echo "Repos where NO '$TARGET_FILE' was found:"
printf '%s\n' "${NO_FILE_FOUND[@]}"
