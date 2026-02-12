# New Relic Tag Tool (Export → Check CSV → Review/Edit → Apply)

Goals:

- Default: look at EVERYTHING in the account.
- Sometimes: include/exclude via `filters.json`.
- Always: generate CSV first, review/edit, then apply.
- Default behavior: **ADD missing required tags**, avoid messing with existing tags.
- Apply supports `--dry-run` and always writes an apply log CSV.

---

## Install (no venv required)

Install requests once:

```bash
python3 -m pip install --user requests
Set your NR API key:

export NR_API_KEY="NRAK-..."
Optional (recommended): set account id so you don't have to type it:

export NR_ACCOUNT_ID="1234567"
Main files you edit
tag_policy.json
Required tags live under required

Defaults for missing tags live under defaults

Team mapping rules live under derived.team.rules

Add a new team mapping rule by copying a rule and changing:

needles (what to look for)

value (what team tag should become)

Rules are checked top-to-bottom. First match wins.

filters.json (optional)
Only used when passed via --filters filters.json.
Lets you include/exclude by:

GUID

name contains

domain

entityType

Step-by-step workflow
Step 1) Export (default = everything)
If you set NR_ACCOUNT_ID, you can just do:

python3 export_newrelic_entity_tags.py --out entities_tags.json
Or specify it explicitly:

python3 export_newrelic_entity_tags.py --account-id 1234567 --out entities_tags.json
Optional filtering at export time:

python3 export_newrelic_entity_tags.py --out entities_tags.json --filters filters.json
Step 2) Check (dry-run proposals) → outputs CSVs
python3 check_newrelic_tags.py \
  --in entities_tags.json \
  --policy tag_policy.json \
  --out-json tag_report.json \
  --out-csv tag_report.csv \
  --only-action-needed
This produces:

tag_report.csv

includes:

all_current_tags (JSON)

would_be_tags (JSON) = current + proposed changes

tag_report_wide_required.csv

WIDE view: ONLY required tag keys are columns (WOULD-BE final values)

tag_report_wide_all.csv

WIDE view: ALL tag keys are columns (WOULD-BE final values)

Friendly order: required columns first, then everything else

Open quickly on macOS:

open tag_report.csv
open tag_report_wide_required.csv
open tag_report_wide_all.csv
Default behavior:

Proposes ADD actions for missing required tags

Flags invalid required tags but does NOT replace them unless you opt-in

Opt-in replacement proposals (advanced):

python3 check_newrelic_tags.py \
  --in entities_tags.json \
  --policy tag_policy.json \
  --out-json tag_report.json \
  --out-csv tag_report.csv \
  --only-action-needed \
  --propose-replacements
Step 3) Review / edit before applying
Safe options:

Edit tag_policy.json and rerun Step 2

Edit filters.json and rerun Step 2

Manually edit tag_report.json (remove entries or delete keys from proposed.add)

Step 4) Apply DRY-RUN (no changes, outputs apply_log.csv)
python3 apply_newrelic_tag_changes.py \
  --report tag_report.json \
  --policy tag_policy.json \
  --out-csv apply_log.csv \
  --dry-run
Open:

open apply_log.csv
Step 5) Apply for real (default = ADD only)
python3 apply_newrelic_tag_changes.py \
  --report tag_report.json \
  --policy tag_policy.json \
  --out-csv apply_log.csv
If you really want to allow REPLACE actions (be careful):

python3 apply_newrelic_tag_changes.py \
  --report tag_report.json \
  --policy tag_policy.json \
  --out-csv apply_log.csv \
  --allow-replace
Quality-of-life scripts (recommended)
Make executable once:

chmod +x make_reports.sh make_apply.sh
Export + Check in one command
If you set NR_ACCOUNT_ID:

./make_reports.sh
Or pass account id:

./make_reports.sh 1234567
Optional filters:

./make_reports.sh 1234567 filters.json
Apply dry-run / real
./make_apply.sh dry
./make_apply.sh real
Safety notes
protected_keys (like TOC) are never modified.

Default apply is ADD-only.

You always review CSVs before applying.


---
```
