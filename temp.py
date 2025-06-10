temp.yaml

import sys

def fix_yaml_indentation(file_path):
    with open(file_path, "r") as f:
        lines = f.readlines()

    fixed_lines = []
    inside_steps = False  # Track if inside 'steps:' block
    adjust_next_line = False  # Flag to adjust indentation after `-`
    step_indent = " " * 4  # Indent first `- step:` by 4 spaces
    nested_indent = " " * 8  # Indent nested keys by 4 spaces more

    for i, line in enumerate(lines):
        stripped_line = line.lstrip()

        # Detect 'steps:' block
        if stripped_line.startswith("steps:"):
            inside_steps = True

        # Fix `- step:` indentation (always 4 spaces)
        if stripped_line.startswith("- step:") and inside_steps:
            fixed_lines.append(step_indent + stripped_line)
            adjust_next_line = True  # Ensure next line is nested correctly

        # Ensure nested keys (after `- step:`) are indented 4 spaces more
        elif adjust_next_line:
            fixed_lines.append(nested_indent + stripped_line)
            adjust_next_line = False  # Reset flag after applying indentation

        # Normal indentation (2 spaces for everything else)
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
