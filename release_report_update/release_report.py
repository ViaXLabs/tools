import requests
import json
import boto3
import datetime

# Load configuration from JSON file
with open("config.json") as config_file:
    config = json.load(config_file)

# Default date range for commit history (Last 14 days)
DEFAULT_START_DATE = (datetime.datetime.utcnow() - datetime.timedelta(days=14)).strftime("%Y-%m-%d")
DEFAULT_END_DATE = datetime.datetime.utcnow().strftime("%Y-%m-%d")

# User input for custom date range
start_date = input(f"Enter start date (YYYY-MM-DD) [Default: {DEFAULT_START_DATE}]: ") or DEFAULT_START_DATE
end_date = input(f"Enter end date (YYYY-MM-DD) [Default: {DEFAULT_END_DATE}]: ") or DEFAULT_END_DATE

# Function: Fetch recent commits from GitHub API for a given repository
def fetch_github_commits(repo):
    """Retrieve commit history for a specific GitHub repository."""
    url = f"https://api.github.com/repos/{repo}/commits?since={start_date}&until={end_date}"
    headers = {"Authorization": f"token YOUR_GITHUB_TOKEN"}

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json()  # Return commit data as JSON
    else:
        print(f"Error fetching commits for {repo}: {response.status_code}")
        return []

# Function: Fetch deployment details from AWS ECS
def fetch_aws_deployments():
    """Retrieve ECS cluster and service deployments from AWS."""
    session = boto3.Session(aws_access_key_id="YOUR_AWS_ACCESS_KEY", aws_secret_access_key="YOUR_AWS_SECRET_KEY")
    ecs_client = session.client("ecs")

    clusters = ecs_client.list_clusters()["clusterArns"]
    deployments = []

    for cluster in clusters:
        services = ecs_client.list_services(cluster=cluster)["serviceArns"]
        deployments.append({"cluster": cluster, "services": services})

    return deployments

# Function: Generate and save the HTML report
def generate_html_report():
    """Create a structured HTML report with summary, details, and commit history."""

    report = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Release Report</title>
        <style>
            body {{ font-family: Arial, sans-serif; background: #f4f4f4; margin: 20px; }}
            .container {{ max-width: 900px; margin: auto; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
            h1, h2 {{ text-align: center; }}
            .section {{ margin-bottom: 20px; }}
            .env {{ background: #e6f7ff; padding: 10px; border-left: 5px solid #0073e6; margin-bottom: 10px; }}
            .commit-link {{ color: #0073e6; text-decoration: none; }}
            .commit-link:hover {{ text-decoration: underline; }}
        </style>
    </head>
    <body>
    <div class="container">
        <h1>🚀 Release Report - {datetime.datetime.utcnow().strftime('%Y-%m-%d')}</h1>
    """

    # Summary Report by Environment
    report += "<div class='section'><h2>📌 Summary Report by Environment</h2>"
    for service in config["services"]:
        commits = fetch_github_commits(service["repo"])
        latest_commit = commits[0]["commit"]["message"] if commits else "No commits found"

        report += f"<div class='env'><h3>{service['service']}</h3><ul>"
        report += f"<li>{latest_commit} (<a href='{commits[0]['html_url']}' class='commit-link'>View</a>)</li>" if commits else "<li>No commits found</li>"
        report += "</ul></div>"
    report += "</div>"

    # Detailed Report by Service
    report += "<div class='section'><h2>🛠️ Detailed Report by Service</h2>"
    deployments = fetch_aws_deployments()

    for deployment in deployments:
        report += f"<div class='env'><h3>{deployment['cluster']}</h3><ul>"
        for service in deployment["services"]:
            report += f"<li>Service: {service}</li>"
        report += "</ul></div>"
    report += "</div>"

    # Commit History Report
    report += "<div class='section'><h2>📜 Commit History Report</h2>"
    for service in config["services"]:
        commits = fetch_github_commits(service["repo"])

        report += f"<div class='env'><h3>{service['service']}</h3><ul>"
        for commit in commits:
            report += f"<li><a href='{commit['html_url']}' class='commit-link'>{commit['commit']['message']} ({commit['commit']['committer']['date']})</a></li>"
        report += "</ul></div>"
    report += "</div>"

    report += "</div></body></html>"

    # Save the report as an HTML file
    with open("release_report.html", "w") as file:
        file.write(report)

    print("✅ HTML Release Report generated successfully!")

# Execute the report generation process
generate_html_report()
