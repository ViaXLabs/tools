import sys

def fix_yaml_indentation(file_path):
    with open(file_path, "r") as f:
        lines = f.readlines()

    fixed_lines = []
    inside_steps = False  # Track if inside 'steps:' block
    first_step = True  # Track first '- step:' entry under 'steps:'
    step_indent = None  # Store the correct indentation for the first '- step:'

    for i, line in enumerate(lines):
        stripped_line = line.lstrip()

        # Detect 'steps:' block
        if stripped_line.startswith("steps:"):
            inside_steps = True
            first_step = True  # Reset first step tracking

        # Ensure the first '- step:' is indented correctly, but leave others unchanged
        if stripped_line.startswith("- step:") and inside_steps:
            if first_step:
                step_indent = " " * 4  # First '- step:' should be indented 4 spaces
                fixed_lines.append(step_indent + stripped_line)
                first_step = False  # After first step, disable indentation enforcement
            else:
                fixed_lines.append(line)  # Keep original indentation for subsequent '- step:' lines
        else:
            fixed_lines.append(line)

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
