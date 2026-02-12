# New Relic Tag Tool (Export → Check (CSV) → Review/Edit → Apply)

- [New Relic Tag Tool (Export → Check (CSV) → Review/Edit → Apply)](#new-relic-tag-tool-export--check-csv--reviewedit--apply)
  - [Setup](#setup)
  - [Quick “what changed vs your last version”](#quick-what-changed-vs-your-last-version)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export NR_API_KEY="NRAK-..."
The main files you will edit (easy maintenance)
1) tag_policy.json
Where you define:

required tags (required)

safe defaults for missing tags (defaults)

derived mapping rules (derived) (ex: team mapping)

To add a new required tag:

add it under required

optionally add a default under defaults

optionally add a derived rule under derived

2) filters.json (optional)
Only used if you pass --filters filters.json.

This lets you INCLUDE or EXCLUDE entities by:

GUID

name contains (case-insensitive)

domain

entityType

Default behavior if you do not pass --filters:

tools process everything.

Step-by-step process (recommended)
Step 1) Export entities + tags (default = everything)
python export_newrelic_entity_tags.py --account-id 1234567 --out entities_tags.json
Optional: export only a subset using filters

python export_newrelic_entity_tags.py \
  --account-id 1234567 \
  --out entities_tags.json \
  --filters filters.json
Step 2) Check tags (dry-run proposals) and generate CSV
This is the file you review first.

python check_newrelic_tags.py \
  --in entities_tags.json \
  --policy tag_policy.json \
  --out-json tag_report.json \
  --out-csv tag_report.csv \
  --only-action-needed
Optional: review only a subset (without changing the export)

python check_newrelic_tags.py \
  --in entities_tags.json \
  --policy tag_policy.json \
  --filters filters.json \
  --out-json tag_report.json \
  --out-csv tag_report.csv \
  --only-action-needed
What you will see in tag_report.csv:

missing_keys = required tags missing

present_required_values = required tags already present + their values

proposed_add = what will be ADDED (this is usually what you want)

invalid_keys = required tags present but invalid (tool flags these but does not change them by default)

IMPORTANT DEFAULT:

the checker proposes ADD for missing tags

the checker flags invalid tags but does NOT propose replacements

If you really want it to propose replacements (opt-in):

python check_newrelic_tags.py \
  --in entities_tags.json \
  --policy tag_policy.json \
  --out-json tag_report.json \
  --out-csv tag_report.csv \
  --only-action-needed \
  --propose-replacements
Step 3) Review and optionally edit before applying
You have 3 safe ways to proceed:

Option A (most common): edit tag_policy.json and re-run Step 2
Example:

adjust derived team mapping rules

add more required tags

add defaults

Then rerun Step 2 to regenerate the CSV and report.

Option B: edit filters.json and re-run Step 2
Example:

exclude noisy entities

focus on one set of systems

Option C: manually edit the report JSON tag_report.json
This is allowed and sometimes useful.

Typical manual edits:

Remove an entity entry you do NOT want to apply

Remove a specific proposed key from proposed.add

Change a proposed value

Look for each entry like:

"proposed": {
  "add": { "team": ["save"] },
  "replace": {}
}
Step 4) Apply DRY-RUN (prints + writes CSV log)
This will NOT change anything in New Relic, but you get a clear log.

python apply_newrelic_tag_changes.py \
  --report tag_report.json \
  --policy tag_policy.json \
  --out-csv apply_log.csv \
  --dry-run
Optional: apply only a subset using filters (even at apply time)

python apply_newrelic_tag_changes.py \
  --report tag_report.json \
  --policy tag_policy.json \
  --filters filters.json \
  --out-csv apply_log.csv \
  --dry-run
Review:

apply_log.csv shows every action as DRY_RUN

Step 5) Apply for real (default = ADD only)
python apply_newrelic_tag_changes.py \
  --report tag_report.json \
  --policy tag_policy.json \
  --out-csv apply_log.csv
By default this applies ADD actions only.

If you explicitly want REPLACE actions (advanced, careful):

python apply_newrelic_tag_changes.py \
  --report tag_report.json \
  --policy tag_policy.json \
  --out-csv apply_log.csv \
  --allow-replace
Updating team mapping (easy and obvious)
Team mapping is controlled in tag_policy.json here:

"derived": {
  "team": {
    "rules": [
      {
        "source": "any_tag_text",
        "match": "contains_any",
        "needles": ["save"],
        "value": "save"
      }
    ]
  }
}
To add another mapping:

add another object to the rules array

rules are checked top-to-bottom

first match wins

Example new rule template:

{
  "source": "entity_name",
  "match": "contains_any",
  "needles": ["svs", "svs-"],
  "value": "svs"
}
Notes / Safety
Protected keys (like TOC) are never modified.

Default behavior avoids replacing tags.

You always review tag_report.csv before you apply anything.

You always have --dry-run for apply and an apply_log.csv output.


---

## Quick “what changed vs your last version”
- Added **filters.json + filter_utils.py** so you can include/exclude easily without touching Python.
- Checker always produces **CSV** to review.
- Applier always produces **CSV log** of what would/did happen.
- Default behavior is “**ADD missing required tags only**”.

If you want one more quality-of-life improvement: I can add a `make_reports.sh` and `make_apply.sh` (simple shell scripts) so you don’t have to remember command flags — but the current README should already be straightforward.
```
