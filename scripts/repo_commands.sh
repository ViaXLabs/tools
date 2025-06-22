#!/bin/bash

# Optional: preset a TARGET_DIR within the script.
# Leave empty ("") if you want to be prompted when no argument is provided.
TARGET_DIR_OVERRIDE=""

# If a directory argument is provided, use it. Otherwise, check for a script override.
if [ $# -ge 1 ]; then
    TARGET_DIR="$1"
elif [ -n "$TARGET_DIR_OVERRIDE" ]; then
    TARGET_DIR="$TARGET_DIR_OVERRIDE"
else
    read -p "Enter the directory to scan for repos: " TARGET_DIR
fi

# Validate the target directory.
if [ ! -d "$TARGET_DIR" ]; then
    echo "Error: '$TARGET_DIR' is not a valid directory."
    exit 1
fi

# Define the command to run inside each repo.
GIT_COMMAND="git fetch; git pull; git branch"

# Loop through each top-level directory in the target directory.
for repo in "$TARGET_DIR"/*/; do
    if [ -d "$repo/.git" ]; then  # Check if the directory is a Git repository.
        echo "Processing repo: $repo"
        cd "$repo" || exit  # Enter the repository directory.
        eval "$GIT_COMMAND"  # Execute the Git command(s).
        cd - > /dev/null  # Return to the parent directory (silently).
        echo "Done with $repo"
        echo "-----------------------------"
    fi
done
