#!/bin/bash

# Define the command to run inside each repo
GIT_COMMAND="git fetch; git pull; git branch"

# Loop through each top-level directory in the current directory
for repo in */; do
    if [ -d "$repo/.git" ]; then  # Check if the directory is a Git repository
        echo "Processing repo: $repo"
        cd "$repo" || exit  # Enter the repo directory
        eval "$GIT_COMMAND"  # Execute the Git command
        cd ..  # Move back to the parent directory
        echo "Done with $repo"
        echo "-----------------------------"
    fi
done
