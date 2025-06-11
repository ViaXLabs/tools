#!/usr/bin/env python3
# Pre-commit hook to check if AWS resources in a Terraform file include a 'tags' attribute.
import sys
import re

def check_aws_tags(file_path):
    # Collect warnings for resources missing the 'tags' attribute.
    warnings = []

    # Read all lines from the file
    with open(file_path, "r") as f:
        lines = f.readlines()

    # Regex to match 'tags' followed by optional whitespace and an '=' sign (case-insensitive)
    tags_regex = re.compile(r'\btags\s*=', re.IGNORECASE)

    # Iterate through each line to check for an AWS resource declaration
    for i, line in enumerate(lines):
        stripped_line = line.strip()

        # Check if line indicates an AWS resource block (contains both "resource" and "aws_")
        if "resource" in stripped_line and "aws_" in stripped_line:
            # Look ahead from the current line for a valid 'tags' attribute in the block
            if not any(tags_regex.search(l) for l in lines[i:]):
                warnings.append(f"⚠️ WARNING: {file_path}: Line {i+1} - AWS resource missing 'tags'.")

    return warnings

def main():
    # Validate command-line arguments
    if len(sys.argv) < 2:
        print("Usage: python hooks/check_aws_tags.py <file.tf>")
        sys.exit(0)  # Exit without blocking commit if no file is provided.

    file_path = sys.argv[1]
    warnings = check_aws_tags(file_path)

    # Output warnings if any, else confirm that all resources include 'tags'
    if warnings:
        print("\n".join(warnings))
    else:
        print("✅ All AWS resources have 'tags'.")

    sys.exit(0)  # Always exit with status 0

if __name__ == "__main__":
    main()
