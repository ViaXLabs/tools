## to run this:
# go run release_report.go

package main

import (
	"encoding/json"
	"fmt"
	"html/template"
	"io/ioutil"
	"net/http"
	"os"
	"time"
)

// Struct for service configuration
type Service struct {
	Service string `json:"service"`
	Repo    string `json:"repo"`
}

// Struct for GitHub commit data
type Commit struct {
	SHA     string `json:"sha"`
	Message string `json:"commit"`
	URL     string `json:"html_url"`
	Date    string `json:"date"`
}

// Load service configuration from config.json
func loadConfig(filename string) ([]Service, error) {
	file, err := ioutil.ReadFile(filename)
	if err != nil {
		return nil, err
	}

	var config struct {
		Services []Service `json:"services"`
	}
	err = json.Unmarshal(file, &config)
	return config.Services, err
}

// Fetch commits from GitHub API
func fetchGithubCommits(repo string, startDate, endDate string) ([]Commit, error) {
	url := fmt.Sprintf("https://api.github.com/repos/%s/commits?since=%s&until=%s", repo, startDate, endDate)
	req, _ := http.NewRequest("GET", url, nil)
	req.Header.Set("Authorization", "token YOUR_GITHUB_TOKEN")

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var commits []Commit
	err = json.NewDecoder(resp.Body).Decode(&commits)
	return commits, err
}

// Generate and save the HTML report
func generateHTMLReport(services []Service, startDate, endDate string) {
	const templateHTML = `
<!DOCTYPE html>
<html>
<head>
	<title>Release Report</title>
	<style>
		body { font-family: Arial, sans-serif; margin: 20px; }
		.container { max-width: 900px; margin: auto; background: white; padding: 20px; }
		.section { margin-bottom: 30px; }
		.service { font-weight: bold; color: #0073e6; }
		.commit { color: #ff9800; }
		.commit-link { text-decoration: none; color: #0073e6; }
	</style>
</head>
<body>
	<div class="container">
		<h1>🚀 Release Report - {{.Date}}</h1>

		<!-- Summary Report by Environment -->
		<div class="section">
			<h2>📌 Summary Report by Environment</h2>
			{{range .Services}}
				<h3 class="service">{{.Service}}</h3>
				<ul>
				{{range .Commits}}
					<li class="commit"><a href="{{.URL}}" class="commit-link">{{.Message}}</a> - {{.Date}}</li>
				{{end}}
				</ul>
			{{end}}
		</div>
	</div>
</body>
</html>`

	reportFile, err := os.Create("release_report.html")
	if err != nil {
		fmt.Println("Error creating HTML file:", err)
		return
	}
	defer reportFile.Close()

	tmpl, _ := template.New("report").Parse(templateHTML)
	reportData := struct {
		Date     string
		Services []struct {
			Service string
			Commits []Commit
		}
	}{
		Date:     time.Now().Format("January 2, 2006"),
		Services: []struct {
			Service string
			Commits []Commit
		}{},
	}

	for _, service := range services {
		commits, _ := fetchGithubCommits(service.Repo, startDate, endDate)
		reportData.Services = append(reportData.Services, struct {
			Service string
			Commits []Commit
		}{service.Service, commits})
	}

	tmpl.Execute(reportFile, reportData)
	fmt.Println("✅ HTML Release Report generated successfully!")
}

// Main function to execute the report generation
func main() {
	services, err := loadConfig("config.json")
	if err != nil {
		fmt.Println("Error loading config:", err)
		return
	}

	// Default date range (last 14 days)
	startDate := time.Now().AddDate(0, 0, -14).Format("2006-01-02")
	endDate := time.Now().Format("2006-01-02")

	// Allow user input for date range
	fmt.Printf("Enter start date (YYYY-MM-DD) [Default: %s]: ", startDate)
	fmt.Scanln(&startDate)
	fmt.Printf("Enter end date (YYYY-MM-DD) [Default: %s]: ", endDate)
	fmt.Scanln(&endDate)

	// Generate the report
	generateHTMLReport(services, startDate, endDate)
}
