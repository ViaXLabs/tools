FILE: README.md

# New Relic Tag Tool (Export → Check CSV → Review/Edit → Apply)

Key behavior:

- Default: looks at EVERYTHING in the account (unless you pass filters).
- Default: ADD missing required tags. Avoid changing existing tags.
- Always: generate CSVs and review before applying.
- Apply supports --dry-run and always writes apply_log.csv.

---

## Install (no venv required)

```bash
python3 -m pip install --user requests
export NR_API_KEY="NRAK-..."


Optional (recommended):

export NR_ACCOUNT_ID="1234567"

New tags added

This tool now treats these as required:

aws_account: must be "Prod" or "Non-Prod"

eks_cluster: must be "VIS Prod" or "VIS Non-Prod"

Behavior:

If missing, they are derived from environment:

env prod/production => aws_account=Prod, eks_cluster="VIS Prod"

any other env value (as long as environment exists) => aws_account=Non-Prod, eks_cluster="VIS Non-Prod"

Environment standardization (keep current, but flag + suggest)

Your account has many environment values in use.

Target standard values:

dev

test

preprod

stage

prod

Behavior:

Keeps current environment tag (does NOT change it)

Adds a warning if current environment is not in the preferred list

Adds a suggested value (report-only) via suggested.environment_map in tag_policy.json

In the CSV you will see:

suggested_environment

warnings (and warnings_keys)

Team suggestions (report-only)

Behavior:

The tool suggests team based on derived.team.rules

If it cannot derive, it tries suggested.team_normalize

It does NOT overwrite team automatically; it only uses derived team value when team is missing (ADD-only).

In the CSV you will see:

suggested_team

Step-by-step
Step 1) Export

If NR_ACCOUNT_ID is set:

python3 export_newrelic_entity_tags.py --out entities_tags.json


Or specify it:

python3 export_newrelic_entity_tags.py --account-id 1234567 --out entities_tags.json


Optional filters:

python3 export_newrelic_entity_tags.py --out entities_tags.json --filters filters.json

Step 2) Check (dry-run proposals + warnings + suggestions)
python3 check_newrelic_tags.py \
  --in entities_tags.json \
  --policy tag_policy.json \
  --out-json tag_report.json \
  --out-csv tag_report.csv \
  --only-action-needed


Outputs:

tag_report.csv (compact; includes suggestions + warnings + current tags + would-be tags)

tag_report_wide_required.csv (required tags as columns; would-be values)

tag_report_wide_all.csv (all tags as columns; required columns first; would-be values)

Open quickly:

open tag_report.csv
open tag_report_wide_required.csv
open tag_report_wide_all.csv

Step 3) Review / edit

Edit tag_policy.json (required tags, defaults, derived rules, suggested maps)

Edit filters.json to narrow focus

Or manually edit tag_report.json to remove entries or proposed keys

Step 4) Apply DRY-RUN
python3 apply_newrelic_tag_changes.py --report tag_report.json --policy tag_policy.json --out-csv apply_log.csv --dry-run
open apply_log.csv

Step 5) Apply real (ADD only)
python3 apply_newrelic_tag_changes.py --report tag_report.json --policy tag_policy.json --out-csv apply_log.csv
open apply_log.csv

Quality-of-life scripts
chmod +x make_reports.sh make_apply.sh
./make_reports.sh
./make_apply.sh dry
./make_apply.sh real
```
