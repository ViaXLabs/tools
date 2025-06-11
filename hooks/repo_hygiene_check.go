package main

import (
	"fmt"
	"os"
)

// RequiredCandidate represents a file or directory that must exist with a specific type.
type RequiredCandidate struct {
	Path         string // Relative path from the repository root.
	RequiredType string // Expected type: "file" or "dir".
}

// List of required files and directories.
var requiredCandidates = []RequiredCandidate{
	{Path: ".github", RequiredType: "dir"},
	{Path: ".github/CODEOWNERS", RequiredType: "file"},
	{Path: ".github/PULL_REQUEST_TEMPLATE.md", RequiredType: "file"},
	{Path: ".harness", RequiredType: "dir"},
	{Path: ".harness/piplines", RequiredType: "dir"},
	{Path: ".harness/input_steps", RequiredType: "dir"},
	{Path: ".vscode", RequiredType: "dir"},
	{Path: ".vscode/extentions.json", RequiredType: "file"},
	{Path: ".dockerignore", RequiredType: "file"},
	{Path: ".editorconfig", RequiredType: "file"},
	{Path: ".gitignore", RequiredType: "file"},
	{Path: ".pre-commit-config.yaml", RequiredType: "file"},
}

func main() {
	missingFound := false

	// Loop over each required entry, checking for both existence and type.
	for _, candidate := range requiredCandidates {
		info, err := os.Stat(candidate.Path)
		if err != nil {
			fmt.Printf("WARNING: Missing required %s: %s\n", candidate.RequiredType, candidate.Path)
			missingFound = true
			continue
		}

		// Verify that the candidate is of the required type.
		if candidate.RequiredType == "file" && info.IsDir() {
			fmt.Printf("WARNING: Expected file but found directory: %s\n", candidate.Path)
			missingFound = true
		} else if candidate.RequiredType == "dir" && !info.IsDir() {
			fmt.Printf("WARNING: Expected directory but found file: %s\n", candidate.Path)
			missingFound = true
		}
	}

	// Print an overall summary.
	if missingFound {
		fmt.Println("⚠️ Repository hygiene check: some required files/directories are missing or incorrect.")
	} else {
		fmt.Println("✅ Repository hygiene check passed.")
	}

	// Always exit with 0 so that the commit is not blocked.
	os.Exit(0)
}
