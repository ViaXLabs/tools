import sys

def fix_yaml_indentation(file_path):
    with open(file_path, "r") as f:
        lines = f.readlines()

    fixed_lines = []
    adjust_next_line = False  # Flag to adjust indentation after `-`
    step_indent = " " * 4  # Indent first `- step:` by 4 spaces
    nested_indent = " " * 4  # Indent nested keys consistently

    for i, line in enumerate(lines):
        stripped_line = line.lstrip()

        # Ensure `-` triggers 4-space indent for the next line
        if stripped_line.startswith("-"):
            fixed_lines.append("  " + stripped_line)  # Ensure `-` uses 2 spaces
            adjust_next_line = True

        # Ensure nested keys under a `- step:` are correctly aligned (4 spaces)
        elif adjust_next_line:
            fixed_lines.append(nested_indent + stripped_line)  # Next line gets 4 spaces
            adjust_next_line = False

        # Standard indentation remains 2 spaces for everything else
        else:
            fixed_lines.append("  " + stripped_line)

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
