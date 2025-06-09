import sys
import re

def check_yaml_indentation(file_path):
    errors = []
    with open(file_path, "r") as f:
        lines = f.readlines()

    for i, line in enumerate(lines):
        stripped_line = line.lstrip()

        # If the line starts with "-", enforce 4-space indentation
        if stripped_line.startswith("-") and not re.match(r"^\s{4}-", line):
            errors.append(f"❌ Line {i + 1}: '{stripped_line}' should be indented with 4 spaces.")

        # If the line does NOT start with "-", enforce 2-space indentation
        elif not stripped_line.startswith("-") and re.match(r"^\s{4,}", line):
            errors.append(f"❌ Line {i + 1}: '{line.strip()}' should use 2-space indentation.")

    return errors

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python hooks/validate_yaml_indent.py <file.yaml>")
        sys.exit(1)

    file_path = sys.argv[1]
    errors = check_yaml_indentation(file_path)

    if errors:
        print("\n".join(errors))
        sys.exit(1)
    else:
        print("✅ YAML indentation is correct!")
        sys.exit(0)
