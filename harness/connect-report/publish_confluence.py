#!/usr/bin/env python3
"""Push the generated HTML report into a Confluence page (create if missing, else update).

Confluence's 'storage' format is a constrained XHTML subset - <style> blocks
get stripped, so report.py already writes inline styles rather than a
<style> block. This always runs as the last pipeline step; it's not optional.

Reuses the same secret (confluence_api_token) as the confluence_reporting
Harness connector and fetch/confluence.sh - one credential, three consumers.
"""
import os, json
import requests

CONFLUENCE_BASE_URL = os.environ["CONFLUENCE_BASE_URL"]      # e.g. https://yourcompany.atlassian.net/wiki
CONFLUENCE_EMAIL = os.environ["CONFLUENCE_EMAIL"]
CONFLUENCE_API_TOKEN = os.environ["CONFLUENCE_API_TOKEN"]
CONFLUENCE_SPACE_KEY = os.environ["CONFLUENCE_SPACE_KEY"]
CONFLUENCE_PAGE_TITLE = os.environ.get("CONFLUENCE_PAGE_TITLE", "Deployment report")
REPORT_HTML_PATH = os.environ.get("REPORT_HTML_PATH", "./report/deployment-report.html")

def find_existing_page(session):
    resp = session.get(
        f"{CONFLUENCE_BASE_URL}/rest/api/content",
        params={"spaceKey": CONFLUENCE_SPACE_KEY, "title": CONFLUENCE_PAGE_TITLE, "expand": "version"},
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return results[0] if results else None

def main():
    with open(REPORT_HTML_PATH) as f:
        body = f.read()

    session = requests.Session()
    session.auth = (CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN)
    session.headers.update({"Content-Type": "application/json"})

    existing = find_existing_page(session)
    payload_body = {"storage": {"value": body, "representation": "storage"}}

    if existing:
        version = existing["version"]["number"] + 1
        resp = session.put(
            f"{CONFLUENCE_BASE_URL}/rest/api/content/{existing['id']}",
            data=json.dumps({
                "id": existing["id"],
                "type": "page",
                "title": CONFLUENCE_PAGE_TITLE,
                "version": {"number": version},
                "body": payload_body,
            }),
        )
    else:
        resp = session.post(
            f"{CONFLUENCE_BASE_URL}/rest/api/content",
            data=json.dumps({
                "type": "page",
                "title": CONFLUENCE_PAGE_TITLE,
                "space": {"key": CONFLUENCE_SPACE_KEY},
                "body": payload_body,
            }),
        )
    resp.raise_for_status()
    print("Published to Confluence:", resp.json().get("_links", {}).get("webui"))

if __name__ == "__main__":
    main()
