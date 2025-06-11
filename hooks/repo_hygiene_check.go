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

	// For debugging: print the current working directory.
	wd, err := os.Getwd()
	if err == nil {
		fmt.Printf("Checking repository hygiene from working directory: %s\n", wd)
	} else {
		fmt.Printf("WARNING: Cannot determine working directory: %v\n", err)
	}

	// Loop over each required candidate, checking for both existence and expected type.
	for _, candidate := range requiredCandidates {
		info, err := os.Stat(candidate.Path)
		if err != nil {
			// Check if the error is because the candidate does not exist.
			if os.IsNotExist(err) {
				fmt.Printf("WARNING: Missing required %s: %s\n", candidate.RequiredType, candidate.Path)
			} else {
				// Print any other error that might be encountered.
				fmt.Printf("WARNING: Could not access %s %s: %v\n", candidate.RequiredType, candidate.Path, err)
			}
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

	// Always exit with 0 to avoid blocking the commit.
	os.Exit(0)
}
