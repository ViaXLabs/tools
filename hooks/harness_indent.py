import sys

def fix_yaml_indentation(file_path):
    with open(file_path, "r") as f:
        lines = f.readlines()

    fixed_lines = []
    prev_indent = 0  # Track indentation of the previous line

    for i, line in enumerate(lines):
        stripped_line = line.lstrip()

        # If the line starts with "-", indent it exactly 4 spaces more than the previous line
        if stripped_line.startswith("-") and i > 0:
            corrected_indent = " " * (prev_indent + 4)
            fixed_lines.append(corrected_indent + stripped_line)
        else:
            fixed_lines.append(line)
            prev_indent = len(line) - len(stripped_line)  # Update previous line's indentation

    # Overwrite the file with corrected indentation
    with open(file_path, "w") as f:
        f.writelines(fixed_lines)

    print(f"✅ Fixed YAML indentation in {file_path}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python hooks/harness_indent.py <file.yaml>")
        sys.exit(1)

    file_path = sys.argv[1]
    fix_yaml_indentation(file_path)
