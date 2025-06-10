import sys

def fix_yaml_indentation(file_path):
    with open(file_path, "r") as f:
        lines = f.readlines()

    fixed_lines = []
    inside_steps = False  # Track if inside 'steps:' block
    step_indent = None  # Store consistent indentation for '- step:'

    for i, line in enumerate(lines):
        stripped_line = line.lstrip()

        # Detect the start of 'steps:'
        if stripped_line.startswith("steps:"):
            inside_steps = True

        # Ensure '- step:' items are aligned correctly
        if stripped_line.startswith("- step:") and inside_steps:
            if step_indent is None:  # First '- step:' should be indented 4 spaces
                step_indent = " " * 4
            fixed_lines.append(step_indent + stripped_line)
        else:
            fixed_lines.append(line)

        # Track indentation of the previous line
        prev_indent = len(line) - len(stripped_line)

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
