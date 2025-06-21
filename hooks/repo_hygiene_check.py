#!/usr/bin/env python3
import os
import sys

def main():
    # Print the current working directory for debugging purposes.
    work_dir = os.getcwd()
    print(f"Running repository hygiene check in: {work_dir}")

    # Define a list of required items with their expected type.
    # Each item is a dictionary with:
    #   "path": the relative path to check
    #   "type": either "file" or "dir"
    required_items = [
        {"path": ".github", "type": "dir"},
        {"path": ".github/CODEOWNERS", "type": "file"},
        {"path": ".github/PULL_REQUEST_TEMPLATE.md", "type": "file"},
        {"path": ".harness", "type": "dir"},
        {"path": ".harness/piplines", "type": "dir"},
        {"path": ".harness/input_steps", "type": "dir"},
        {"path": ".vscode", "type": "dir"},
        {"path": ".vscode/extentions.json", "type": "file"},
        {"path": ".dockerignore", "type": "file"},
        {"path": ".editorconfig", "type": "file"},
        {"path": ".gitignore", "type": "file"},
        {"path": ".pre-commit-config.yaml", "type": "file"},
    ]

    missing_found = False

    # Check each required path.
    for item in required_items:
        path = item["path"]
        expected_type = item["type"]

        if not os.path.exists(path):
            # The candidate does not exist at all.
            print(f"WARNING: Missing required {expected_type}: {path}")
            missing_found = True
        else:
            if expected_type == "file" and not os.path.isfile(path):
                # Path exists but is not a file as expected.
                print(f"WARNING: Expected a file but found something else: {path}")
                missing_found = True
            elif expected_type == "dir" and not os.path.isdir(path):
                # Path exists but is not a directory as expected.
                print(f"WARNING: Expected a directory but found something else: {path}")
                missing_found = True

    # Overall summary: print whether the hygiene check passed or if some items are missing.
    if missing_found:
        print("⚠️  Repository hygiene check: some required files/directories are missing or incorrect.")
    else:
        print("✅ Repository hygiene check passed.")

    # Exit with code 0 so that the commit is not blocked.
    sys.exit(0)

if __name__ == "__main__":
    main()
