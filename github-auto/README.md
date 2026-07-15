# Golden Repo Provisioning Kit

Enforces your golden repo standard (settings, branch protection, labels, team
permissions, webhooks) against new repos — either from a checked-in JSON
spec, or by copying the live settings off a reference repo you point at.

## Files

- `golden-repo-config.example.json` — the declarative standard. Copy to
  `golden-repo-config.json`, edit to match your program's actual standard,
  and check it into the golden template repo itself so it stays versioned
  alongside the template content.
- `apply_golden_repo.py` — does the work. Two modes:
  - `--mode config` — reads `golden-repo-config.json` and applies it.
  - `--mode mirror` — introspects a live `--source-repo` (e.g. your actual
    golden template, or any repo whose current permission setup you like)
    and applies the same settings to the target.
  In either mode, if the target repo doesn't exist yet, it's created first
  via GitHub's "generate from template" API against `--template-repo`, so
  the new repo gets the golden repo's actual file contents too, not just
  its settings.
- `harness-pipeline.yaml` — a Harness CI pipeline with four inputs (owner,
  new repo name, requesting team, mode) that runs the script for you.

## One-time setup

1. Store a GitHub token with org admin / repo admin scopes as a Harness
   secret, e.g. `github_admin_token` (referenced in the pipeline YAML).
2. Put `golden-repo-config.json` and `apply_golden_repo.py` somewhere the
   pipeline's codebase clone will have access to (e.g. a small internal
   "golden-repo-tooling" repo that this pipeline's codebase points to).
3. Import `harness-pipeline.yaml` into Harness, fix up `projectIdentifier`
   / `orgIdentifier`, and set the codebase connector.

## Running it directly (outside Harness, for testing)

```bash
export GITHUB_TOKEN=ghp_xxx

# Config-driven — brand-new repo, built from a template repo's contents,
# configured per the JSON standard
python3 apply_golden_repo.py \
  --owner my-org \
  --new-repo-name payments-service \
  --team platform-team \
  --mode config \
  --config golden-repo-config.json \
  --template-repo my-org/golden-repo-template

# Mirror mode — "make it exactly like this other repo's current settings"
python3 apply_golden_repo.py \
  --owner my-org \
  --new-repo-name payments-service \
  --team platform-team \
  --mode mirror \
  --source-repo my-org/some-repo-with-permissions-i-like

# Repo already exists, just bring its settings into line
python3 apply_golden_repo.py \
  --owner my-org \
  --new-repo-name existing-repo \
  --team platform-team \
  --mode config \
  --config golden-repo-config.json \
  --skip-create
```

## What it touches

Repo feature flags (wiki, issues, projects, merge strategies, etc.),
default branch, visibility, branch protection on the default branch,
topics, labels (creates or updates), team permissions (grants the
requesting team's permission plus any explicit overrides from the config —
e.g. always giving `security-team` read access), and webhooks.

## Notes / things to adapt

- **Team permission logic**: right now the requesting team gets
  `overrides[team]` if present, else `team_permissions.default`. If your
  actual policy is more nuanced (e.g. permission depends on which program
  the repo belongs to, not just which team), that's the one function
  (`apply_team_permissions`) to extend.
- **Rulesets vs. classic branch protection**: this uses the classic
  branch-protection API since it's simpler and universally available. If
  your org has moved to GitHub's newer repository rulesets, that's a
  different endpoint (`/repos/{owner}/{repo}/rulesets`) — happy to add a
  variant if that's what you're on.
- **Individual collaborators**: deliberately left out, since golden repos
  are usually access-via-team, not via named individuals. Easy to add a
  `collaborators` block if you need it.
- **Auth**: the script expects `GITHUB_TOKEN` in the environment — never
  hardcode it. In Harness, pull it from a secret as shown in the pipeline
  YAML.
