#!/usr/bin/env python3
# Pre-commit hook to verify that AWS resource blocks and
# specific module blocks in a Terraform file include a 'tags' attribute.
# For modules, if the module name (which may include underscores, e.g. "rds_db")
# contains any of the following keywords (case-insensitive):
#   rds, postgres, db, database, ec2, aurora
# then the block is checked for a valid 'tags' attribute.

import sys
import re

def get_block_lines(lines, start_index):
    """
    Extracts the lines belonging to a Terraform block starting at start_index.

    The block starts at the first occurrence of '{' and ends when all opened braces
    are closed.

    Returns:
        block_lines (list): Lines within the block.
        next_index (int): Line index immediately after the block.
    """
    block_lines = []
    brace_count = 0
    block_started = False
    i = start_index
    while i < len(lines):
        line = lines[i]
        if not block_started:
            if "{" in line:
                block_started = True
                brace_count += line.count("{")
                brace_count -= line.count("}")
            block_lines.append(line)
        else:
            block_lines.append(line)
            brace_count += line.count("{")
            brace_count -= line.count("}")
        i += 1
        if block_started and brace_count <= 0:
            break
    return block_lines, i

def check_aws_tags(file_path):
    """
    Validates that AWS resource blocks and select module blocks include a 'tags' attribute.

    For module blocks, we extract the module name (expecting a format like: module "name" {),
    and only perform the check if the module name (which could include underscores, e.g. "rds_db")
    contains one of the designated keywords.

    Returns:
        warnings (list): Warning messages for blocks missing the 'tags' attribute.
    """
    warnings = []
    with open(file_path, "r") as f:
        lines = f.readlines()

    # Regex to match a valid tags assignment with optional whitespace before '='.
    tags_regex = re.compile(r'\btags\s*=', re.IGNORECASE)
    # Keywords to check for within module names.
    module_keywords = ['rds', 'postgres', 'db', 'database', 'ec2', 'aurora']

    i = 0
    while i < len(lines):
        stripped_line = lines[i].strip()

        # AWS resource block: check if the line contains both "resource" and "aws_".
        if "resource" in stripped_line and "aws_" in stripped_line:
            block_lines, next_index = get_block_lines(lines, i)
            if not any(tags_regex.search(bl) for bl in block_lines):
                warnings.append(f"⚠️ WARNING: {file_path}: Line {i+1} - AWS resource missing 'tags'.")
            i = next_index
            continue

        # Module block: check if the line starts with "module".
        elif stripped_line.startswith("module"):
            # Expect module declaration in the form: module "name" {
            module_match = re.search(r'^module\s+"([^"]+)"', stripped_line)
            if module_match:
                module_name = module_match.group(1).lower()
                # Check if module name contains any of the designated keywords.
                if any(keyword in module_name for keyword in module_keywords):
                    block_lines, next_index = get_block_lines(lines, i)
                    if not any(tags_regex.search(bl) for bl in block_lines):
                        warnings.append(f"⚠️ WARNING: {file_path}: Line {i+1} - Module '{module_name}' missing 'tags'.")
                    i = next_index
                    continue
        i += 1

    return warnings

def main():
    # Validate that a file path was provided.
    if len(sys.argv) < 2:
        print("Usage: python hooks/check_aws_tags.py <file.tf>")
        sys.exit(0)  # Exit without blocking commit if no file is provided.

    file_path = sys.argv[1]
    warnings = check_aws_tags(file_path)

    # Output warnings if any; otherwise confirm that all checks passed.
    if warnings:
        print("\n".join(warnings))
    else:
        print("✅ All AWS resources and relevant modules have 'tags'.")

    # Always exit with status 0 to avoid blocking commits.
    sys.exit(0)

if __name__ == "__main__":
    main()
