package main

import (
	"fmt"
	"os"
)

// List of required files and directories relative to the repository root.
var requiredPaths = []string{
	".github",
	".github/CODEOWNERS",
	".github/PULL_REQUEST_TEMPLATE.md",
	".harness",
	".harness/piplines",
	".harness/input_steps",
	".vscode",
	".vscode/extentions.json",
	".dockerignore",
	".editorconfig",
	".gitignore",
	".pre-commit-config.yaml",
}

func main() {
	missing := false

	// Loop over each required path and check for its existence.
	for _, path := range requiredPaths {
		// os.Stat returns an error if the file/directory doesn't exist.
		if _, err := os.Stat(path); os.IsNotExist(err) {
			fmt.Printf("WARNING: Missing required file or directory: %s\n", path)
			missing = true
		}
	}

	// Print a summary of the hygiene check.
	if missing {
		fmt.Println("⚠️ Repository hygiene check: some required files/directories are missing.")
	} else {
		fmt.Println("✅ Repository hygiene check passed.")
	}

	// Always exit with status code 0 to avoid blocking the commit.
	os.Exit(0)
}
