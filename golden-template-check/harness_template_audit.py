#!/usr/bin/env python3
"""
harness_template_audit.py

Audits every team repo's .harness/ pipeline configs against a list of
"golden template" keywords, to see:
  - who's actually wired in via `templateRef:` (Adopted)
  - who has matching logic inline but NOT templated (Candidate)

Requires: GitHub CLI (`gh`) installed and authenticated (`gh auth login`),
with access to every repo listed in teams.json.

Usage:
    python3 harness_template_audit.py \
        --teams teams.json \
        --keywords golden_templates.txt \
        --out ./report

Inputs
------
teams.json:  a list of team -> repo mappings. Accepts a few common key
             names so you probably don't need to reshape your existing file:
    [
      {"team": "Payments",  "repo": "my-org/payments-service"},
      {"name": "Checkout",  "repository": "my-org/checkout-service", "branch": "main"},
      ...
    ]
    "branch" is optional — if omitted, the repo's default branch is used.

golden_templates.txt:  one keyword per line. Blank lines and lines
             starting with # are ignored. Optional display name after a
             comma:
    changeTrackingCreateDeployment
    k8s-canary-deploy, Canary Deployment Template
    approval-gate-slack, Slack Approval Gate

Output
------
./report/summary.html         - team x template adoption matrix
./report/team-<team>.html     - per-team file/line level detail
"""

import argparse
import base64
import json
import re
import subprocess
import sys
import html
from pathlib import Path
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# gh CLI helpers
# ---------------------------------------------------------------------------

def gh_json(args):
    """Run a `gh api` call and parse JSON stdout. Returns None on failure."""
    try:
        result = subprocess.run(
            ["gh", "api", *args],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            return None, result.stderr.strip()
        return json.loads(result.stdout), None
    except FileNotFoundError:
        print("ERROR: `gh` CLI not found. Install it and run `gh auth login` first.", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        return None, f"bad JSON from gh: {e}"
    except subprocess.TimeoutExpired:
        return None, "gh api call timed out"


def gh_raw(path):
    """Fetch a file's raw text content via the contents API. Returns (text, error)."""
    try:
        result = subprocess.run(
            ["gh", "api", "-H", "Accept: application/vnd.github.raw", path],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            return None, result.stderr.strip()
        return result.stdout, None
    except FileNotFoundError:
        print("ERROR: `gh` CLI not found. Install it and run `gh auth login` first.", file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        return None, "gh api call timed out"


def get_default_branch(repo):
    data, err = gh_json([f"repos/{repo}"])
    if err or not data:
        return None, err or "no data"
    return data.get("default_branch"), None


def list_harness_files(repo, branch):
    data, err = gh_json([f"repos/{repo}/git/trees/{branch}?recursive=1"])
    if err or not data:
        return [], err or "no data"
    if data.get("truncated"):
        print(f"  ! warning: tree listing for {repo} was truncated by GitHub (very large repo) "
              f"— some files may be missed", file=sys.stderr)
    paths = [
        item["path"] for item in data.get("tree", [])
        if item.get("type") == "blob"
        and item["path"].startswith(".harness/")
        and item["path"].lower().endswith((".yaml", ".yml"))
    ]
    return paths, None


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_teams(path):
    raw = json.loads(Path(path).read_text())
    teams = []
    for entry in raw:
        team = entry.get("team") or entry.get("team_name") or entry.get("name")
        repo = entry.get("repo") or entry.get("repository") or entry.get("repo_name") or entry.get("github_repo")
        branch = entry.get("branch")
        if not team or not repo:
            print(f"  ! skipping malformed teams.json entry (missing team/repo): {entry}", file=sys.stderr)
            continue
        teams.append({"team": team, "repo": repo, "branch": branch})
    return teams


def load_keywords(path):
    keywords = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "," in line:
            kw, label = line.split(",", 1)
            keywords.append({"keyword": kw.strip(), "label": label.strip()})
        else:
            keywords.append({"keyword": line, "label": line})
    return keywords


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------

TEMPLATE_REF_RE = re.compile(r"templateRef\s*:", re.IGNORECASE)
CONTEXT_WINDOW = 5  # lines above/below a hit to check for templateRef:


def scan_file_content(text, keywords):
    """Return list of match dicts for one file's content."""
    lines = text.splitlines()
    matches = []
    for i, line in enumerate(lines):
        for kw in keywords:
            if kw["keyword"].lower() in line.lower():
                lo = max(0, i - CONTEXT_WINDOW)
                hi = min(len(lines), i + CONTEXT_WINDOW + 1)
                nearby = "\n".join(lines[lo:hi])
                adopted = bool(TEMPLATE_REF_RE.search(nearby))
                matches.append({
                    "keyword": kw["keyword"],
                    "label": kw["label"],
                    "line_no": i + 1,
                    "snippet": line.strip(),
                    "category": "adopted" if adopted else "candidate",
                })
    return matches


def audit_team(team_entry, keywords):
    team, repo, branch = team_entry["team"], team_entry["repo"], team_entry["branch"]
    print(f"Scanning {team} ({repo})...")

    result = {
        "team": team, "repo": repo, "branch": branch,
        "files_scanned": 0, "matches": [], "errors": [],
    }

    if not branch:
        branch, err = get_default_branch(repo)
        if err:
            result["errors"].append(f"couldn't resolve repo/default branch: {err}")
            return result
        result["branch"] = branch

    paths, err = list_harness_files(repo, branch)
    if err:
        result["errors"].append(f"couldn't list .harness contents: {err}")
        return result

    if not paths:
        result["errors"].append("no .yaml/.yml files found under .harness/ (wrong path? empty repo?)")
        return result

    for path in paths:
        text, err = gh_raw(f"repos/{repo}/contents/{path}?ref={branch}")
        if err:
            result["errors"].append(f"couldn't fetch {path}: {err}")
            continue
        result["files_scanned"] += 1
        for m in scan_file_content(text, keywords):
            m["file"] = path
            result["matches"].append(m)

    return result


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

STYLE = """
:root {
  --bg: #0f1417;
  --panel: #161d22;
  --panel-2: #1c252b;
  --line: #2a343b;
  --ink: #e7edf0;
  --ink-dim: #93a3ac;
  --accent: #ff8a3d;
  --accent-dim: #6b4a30;
  --good: #4fd1a5;
  --warn: #ffcf5c;
  --mono: "IBM Plex Mono", "SFMono-Regular", Consolas, monospace;
  --sans: "IBM Plex Sans", "Inter", -apple-system, sans-serif;
}
* { box-sizing: border-box; }
body {
  background: var(--bg);
  color: var(--ink);
  font-family: var(--sans);
  margin: 0;
  padding: 0 0 4rem 0;
}
header.top {
  padding: 3rem 3rem 2rem 3rem;
  border-bottom: 1px solid var(--line);
  background: linear-gradient(180deg, var(--panel) 0%, var(--bg) 100%);
}
header.top .eyebrow {
  font-family: var(--mono);
  color: var(--accent);
  font-size: 0.8rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  margin-bottom: 0.6rem;
}
header.top h1 {
  font-size: 2.1rem;
  margin: 0 0 0.4rem 0;
  font-weight: 600;
  letter-spacing: -0.01em;
}
header.top .meta {
  color: var(--ink-dim);
  font-family: var(--mono);
  font-size: 0.85rem;
}
main { max-width: 1100px; margin: 0 auto; padding: 0 3rem; }
.stat-row {
  display: flex; gap: 1rem; flex-wrap: wrap;
  margin: 2rem 0;
}
.stat {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 1.1rem 1.4rem;
  min-width: 140px;
  flex: 1;
}
.stat .num { font-family: var(--mono); font-size: 1.8rem; color: var(--accent); }
.stat .lbl { color: var(--ink-dim); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.06em; margin-top: 0.2rem; }
table { width: 100%; border-collapse: collapse; margin: 1.5rem 0; }
th, td {
  text-align: left; padding: 0.65rem 0.8rem; border-bottom: 1px solid var(--line);
  font-size: 0.9rem;
}
th {
  font-family: var(--mono); font-size: 0.72rem; text-transform: uppercase;
  letter-spacing: 0.08em; color: var(--ink-dim); border-bottom: 1px solid var(--accent-dim);
}
tr:hover td { background: var(--panel-2); }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
.badge {
  display: inline-block; padding: 0.15rem 0.55rem; border-radius: 999px;
  font-family: var(--mono); font-size: 0.72rem; font-weight: 600;
}
.badge.adopted { background: rgba(79,209,165,0.15); color: var(--good); }
.badge.candidate { background: rgba(255,207,92,0.15); color: var(--warn); }
.badge.zero { background: rgba(255,255,255,0.06); color: var(--ink-dim); }
.count-cell { font-family: var(--mono); text-align: center; }
.count-cell.has-match { color: var(--good); font-weight: 600; }
.count-cell.no-match { color: var(--ink-dim); opacity: 0.5; }
section { margin-top: 2.5rem; }
section h2 {
  font-size: 1.1rem; color: var(--ink); border-left: 3px solid var(--accent);
  padding-left: 0.7rem; margin-bottom: 1rem;
}
.file-group { margin-bottom: 1.6rem; border: 1px solid var(--line); border-radius: 6px; overflow: hidden; }
.file-group .file-head {
  background: var(--panel); padding: 0.6rem 1rem; font-family: var(--mono);
  font-size: 0.82rem; color: var(--ink-dim); border-bottom: 1px solid var(--line);
}
.file-group .hit {
  padding: 0.55rem 1rem; border-bottom: 1px solid var(--line); font-family: var(--mono); font-size: 0.82rem;
  display: flex; gap: 0.8rem; align-items: baseline;
}
.file-group .hit:last-child { border-bottom: none; }
.hit .line-no { color: var(--ink-dim); min-width: 3.2rem; }
.hit .snippet { color: var(--ink); white-space: pre-wrap; word-break: break-word; }
.errors { background: rgba(255, 92, 92, 0.08); border: 1px solid rgba(255,92,92,0.3); border-radius: 6px; padding: 1rem; color: #ff9d9d; font-family: var(--mono); font-size: 0.82rem; }
.back-link { font-family: var(--mono); font-size: 0.85rem; }
footer { color: var(--ink-dim); font-family: var(--mono); font-size: 0.75rem; text-align: center; margin-top: 3rem; }
"""


def render_summary(results, keywords, generated_at, out_dir):
    total_teams = len(results)
    total_files = sum(r["files_scanned"] for r in results)
    total_adopted = sum(1 for r in results for m in r["matches"] if m["category"] == "adopted")
    total_candidates = sum(1 for r in results for m in r["matches"] if m["category"] == "candidate")
    teams_with_errors = sum(1 for r in results if r["errors"])

    # matrix: rows = teams, cols = keywords, cell = (adopted_count, candidate_count)
    rows = []
    for r in results:
        cells = []
        for kw in keywords:
            adopted = sum(1 for m in r["matches"] if m["keyword"] == kw["keyword"] and m["category"] == "adopted")
            candidate = sum(1 for m in r["matches"] if m["keyword"] == kw["keyword"] and m["category"] == "candidate")
            cells.append((adopted, candidate))
        rows.append((r, cells))

    def team_slug(name):
        return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

    col_headers = "".join(f"<th>{html.escape(kw['label'])}</th>" for kw in keywords)

    row_html = []
    for r, cells in rows:
        cell_html = ""
        for adopted, candidate in cells:
            if adopted and candidate:
                cell_html += f'<td class="count-cell has-match">{adopted}<span class="badge candidate" style="margin-left:6px">+{candidate}</span></td>'
            elif adopted:
                cell_html += f'<td class="count-cell has-match">{adopted}</td>'
            elif candidate:
                cell_html += f'<td class="count-cell has-match"><span class="badge candidate">{candidate} candidate</span></td>'
            else:
                cell_html += '<td class="count-cell no-match">—</td>'
        error_flag = ' <span class="badge zero">errors</span>' if r["errors"] else ""
        row_html.append(f"""
        <tr>
          <td><a href="team-{team_slug(r['team'])}.html">{html.escape(r['team'])}</a>{error_flag}</td>
          <td style="color:var(--ink-dim); font-family:var(--mono); font-size:0.8rem">{html.escape(r['repo'])}</td>
          {cell_html}
        </tr>""")

    html_out = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Golden Template Adoption — Summary</title>
<style>{STYLE}</style>
</head>
<body>
<header class="top">
  <div class="eyebrow">Harness Template Audit</div>
  <h1>Golden Template Adoption — Summary</h1>
  <div class="meta">Generated {generated_at} · {total_teams} teams · {total_files} pipeline files scanned</div>
</header>
<main>
  <div class="stat-row">
    <div class="stat"><div class="num">{total_teams}</div><div class="lbl">Teams scanned</div></div>
    <div class="stat"><div class="num">{total_files}</div><div class="lbl">Pipeline files</div></div>
    <div class="stat"><div class="num">{total_adopted}</div><div class="lbl">Adopted references</div></div>
    <div class="stat"><div class="num">{total_candidates}</div><div class="lbl">Candidate matches</div></div>
    <div class="stat"><div class="num">{teams_with_errors}</div><div class="lbl">Teams with errors</div></div>
  </div>

  <section>
    <h2>Adoption matrix</h2>
    <table>
      <tr><th>Team</th><th>Repo</th>{col_headers}</tr>
      {''.join(row_html)}
    </table>
    <p style="color:var(--ink-dim); font-size:0.85rem;">
      A plain number = uses of that template via <code>templateRef</code>.
      <span class="badge candidate">N candidate</span> = keyword found but not wired through a template — worth a look.
      Click a team name for the file/line detail.
    </p>
  </section>
</main>
<footer>harness_template_audit.py</footer>
</body>
</html>"""

    (out_dir / "summary.html").write_text(html_out)


def render_team_report(result, generated_at, out_dir):
    team_slug = re.sub(r"[^a-z0-9]+", "-", result["team"].lower()).strip("-")

    errors_html = ""
    if result["errors"]:
        items = "".join(f"<li>{html.escape(e)}</li>" for e in result["errors"])
        errors_html = f'<div class="errors"><strong>Issues while scanning:</strong><ul>{items}</ul></div>'

    # group matches by file
    by_file = {}
    for m in result["matches"]:
        by_file.setdefault(m["file"], []).append(m)

    file_blocks = []
    for path, hits in sorted(by_file.items()):
        hit_rows = ""
        for h in sorted(hits, key=lambda x: x["line_no"]):
            badge = f'<span class="badge {h["category"]}">{h["category"]}</span>'
            hit_rows += f"""
            <div class="hit">
              <span class="line-no">L{h['line_no']}</span>
              {badge}
              <span class="snippet">{html.escape(h['snippet'])} <span style="color:var(--ink-dim)">// {html.escape(h['label'])}</span></span>
            </div>"""
        file_blocks.append(f"""
        <div class="file-group">
          <div class="file-head">{html.escape(path)}</div>
          {hit_rows}
        </div>""")

    if not file_blocks and not result["errors"]:
        file_blocks.append('<p style="color:var(--ink-dim)">No keyword matches found in any scanned file.</p>')

    html_out = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(result['team'])} — Template Audit</title>
<style>{STYLE}</style>
</head>
<body>
<header class="top">
  <div class="eyebrow"><a class="back-link" href="summary.html">&larr; All teams</a></div>
  <h1>{html.escape(result['team'])}</h1>
  <div class="meta">{html.escape(result['repo'])} @ {html.escape(result['branch'] or 'unknown')} · {result['files_scanned']} files scanned · generated {generated_at}</div>
</header>
<main>
  {errors_html}
  <section>
    <h2>Matches by file</h2>
    {''.join(file_blocks)}
  </section>
</main>
<footer>harness_template_audit.py</footer>
</body>
</html>"""

    (out_dir / f"team-{team_slug}.html").write_text(html_out)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--teams", required=True, help="Path to teams.json")
    ap.add_argument("--keywords", required=True, help="Path to golden_templates.txt")
    ap.add_argument("--out", default="./report", help="Output directory for HTML reports")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    teams = load_teams(args.teams)
    keywords = load_keywords(args.keywords)

    if not teams:
        print("No valid team entries found in teams.json — nothing to do.", file=sys.stderr)
        sys.exit(1)
    if not keywords:
        print("No keywords found in golden_templates.txt — nothing to match against.", file=sys.stderr)
        sys.exit(1)

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    results = []
    for team_entry in teams:
        results.append(audit_team(team_entry, keywords))

    render_summary(results, keywords, generated_at, out_dir)
    for r in results:
        render_team_report(r, generated_at, out_dir)

    print(f"\nDone. Open {out_dir / 'summary.html'} in a browser.")


if __name__ == "__main__":
    main()
