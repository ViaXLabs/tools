import sys
import re

def fix_yaml_indentation(file_path):
    with open(file_path, "r") as f:
        lines = f.readlines()

    fixed_lines = []
    for line in lines:
        stripped_line = line.lstrip()

        # If line starts with "-", fix it to 4-space indentation
        if stripped_line.startswith("-") and not re.match(r"^\s{4}-", line):
            fixed_lines.append("    " + stripped_line)

        # If the line does NOT start with "-", enforce 2-space indentation
        elif not stripped_line.startswith("-") and re.match(r"^\s{4,}", line):
            fixed_lines.append("  " + stripped_line)

        else:
            fixed_lines.append(line)

    # Overwrite the file with corrected indentation
    with open(file_path, "w") as f:
        f.writelines(fixed_lines)

    print(f"✅ Fixed YAML indentation in {file_path}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python hooks/auto_fix_yaml_indent.py <file.yaml>")
        sys.exit(1)

    file_path = sys.argv[1]
    fix_yaml_indentation(file_path)
