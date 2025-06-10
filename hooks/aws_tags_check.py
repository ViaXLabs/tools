import sys
import re

def check_aws_tags(file_path):
    warnings = []
    with open(file_path, "r") as f:
        lines = f.readlines()

    for i, line in enumerate(lines):
        stripped_line = line.strip()

        # Check if the resource block defines a 'tags' attribute
        if "resource" in stripped_line and "aws_" in stripped_line:
            if not any("tags = {" in l for l in lines[i:]):
                warnings.append(f"⚠️ WARNING: {file_path}: Line {i+1} - AWS resource missing 'tags'.")

    return warnings

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python hooks/check_aws_tags.py <file.tf>")
        sys.exit(0)  # Do not block commit

    file_path = sys.argv[1]
    warnings = check_aws_tags(file_path)

    if warnings:
        print("\n".join(warnings))
    else:
        print("✅ All AWS resources have 'tags'.")

    sys.exit(0)  # Ensure it does NOT block commits
