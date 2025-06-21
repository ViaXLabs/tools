#!/bin/bash

FIND_TEXT="old_text"     # Text to find
REPLACE_TEXT="new_text"  # Text to replace with
TARGET_FILE="config.json" # File where replacement happens

# Define the command as a variable
COMMAND="sed -i 's/$FIND_TEXT/$REPLACE_TEXT/g'"

for repo in */; do
    if [ -d "$repo/.git" ]; then  # Check if the directory is a Git repository
        FILE_PATH=$(find "$repo" -type f -name "$TARGET_FILE")

        if [ -n "$FILE_PATH" ]; then
            echo "Updating $TARGET_FILE in: $repo"
            eval "$COMMAND \"$FILE_PATH\""  # Execute the command on the file
            echo "Replacement done in $FILE_PATH"
        else
            echo "$TARGET_FILE not found in $repo"
        fi

        echo "-----------------------------"
    fi
done
