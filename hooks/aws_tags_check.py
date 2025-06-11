#!/usr/bin/env python3
# Pre-commit hook to verify that AWS resource blocks and
# specific module blocks in a Terraform file include a 'tags' attribute.

import sys
import re

def get_block_lines(lines, start_index):
    """
    Extracts a block's lines from a Terraform file starting at start_index.

    The block is assumed to start at the first occurrence of '{'
    and ends when the balanced closing '}' is reached.

    Returns:
        block_lines (list): List of lines that belong to the block.
        next_index (int): The index of the line immediately after the block.
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
    Checks if AWS resource blocks and select module blocks include a 'tags' attribute.

    For module blocks, we only trigger the check if the module's name (extracted via regex)
    contains any of these keywords (case-insensitive):
        rds, postgres, db, database, ec2, aurora

    Returns:
        warnings (list): A list of warning messages for blocks missing 'tags'.
    """
    warnings = []
    with open(file_path, "r") as f:
        lines = f.readlines()

    # Regex to match a valid tags assignment with optional whitespace before '='.
    tags_regex = re.compile(r'\btags\s*=', re.IGNORECASE)
    # Keywords to check within module names.
    module_keywords = ['rds', 'postgres', 'db', 'database', 'ec2', 'aurora']

    i = 0
    while i < len(lines):
        stripped_line = lines[i].strip()

        # Check if this is an AWS resource block.
        if "resource" in stripped_line and "aws_" in stripped_line:
            block_lines, next_index = get_block_lines(lines, i)
            if not any(tags_regex.search(bl) for bl in block_lines):
                warnings.append(f"⚠️ WARNING: {file_path}: Line {i+1} - AWS resource missing 'tags'.")
            i = next_index
            continue

        # Check for module blocks that need tag validation.
        elif stripped_line.startswith("module"):
            # Extract the module name using regex; expecting a format like: module "name" {
            module_match = re.search(r'^module\s+"([^"]+)"', stripped_line)
            if module_match:
                module_name = module_match.group(1).lower()
                # Proceed only if the module name contains one of the specified keywords.
                if any(keyword in module_name for keyword in module_keywords):
                    block_lines, next_index = get_block_lines(lines, i)
                    if not any(tags_regex.search(bl) for bl in block_lines):
                        warnings.append(f"⚠️ WARNING: {file_path}: Line {i+1} - Module '{module_name}' missing 'tags'.")
                    i = next_index
                    continue
        i += 1

    return warnings

def main():
    # Ensure file path is provided
    if len(sys.argv) < 2:
        print("Usage: python hooks/check_aws_tags.py <file.tf>")
        sys.exit(0)  # Do not block commit if no file is provided.

    file_path = sys.argv[1]
    warnings = check_aws_tags(file_path)

    # Output messages: warnings if any, else confirmation of compliance.
    if warnings:
        print("\n".join(warnings))
    else:
        print("✅ All AWS resources and relevant modules have 'tags'.")

    sys.exit(0)  # Always exit with 0 to keep the commit non-blocking.

if __name__ == "__main__":
    main()
