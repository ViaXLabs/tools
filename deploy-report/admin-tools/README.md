# Admin tools

Separate from the report generator on purpose -- these scripts *write* to
GitHub, so they're kept apart from a tool that only ever reads.

## manage_team_topics.py

Applies `team-<name>` topics to your GitHub repos based on a static
`teams.json` (same format the main tool's `team_registry.py` reads in
`static` mode -- see `../teams.example.json`). This is the bridge from
"we maintain a JSON file by hand" to "GitHub topics are the source of
truth": run this once your `teams.json` is accurate, then flip the main
tool's config to `team_registry.mode: github_topics` and stop maintaining
the file.

```bash
export GITHUB_TOKEN=ghp_xxx   # needs repo write access (or the fine-grained
                               # "administration: write" permission)

# 1. Dry run first -- always. Shows exactly what would change, writes nothing.
python manage_team_topics.py --teams-file ../teams.json

# 2. Once it looks right, apply for real:
python manage_team_topics.py --teams-file ../teams.json --apply --report topics-report.json
```

What it does, per repo listed in `teams.json`:
- fetches its current topics
- keeps every topic that doesn't start with `team-` (so other topics you
  use for other purposes are left alone)
- adds the `team-<name>` topic(s) it should have
- removes any *stale* `team-*` topic that no longer matches (e.g. a repo
  that moved teams)
- prints a per-repo diff, and skips repos it can't find (renamed, typo, or
  your token doesn't have access) rather than guessing

Nothing is written unless you pass `--apply`. The `--report` file (JSON)
is a full record of what happened (or would happen), useful for a PR
description or an audit trail if you're doing this across a lot of repos.

Team names are slugified for the topic (`"Customer Experience"` ->
`team-customer-experience`); GitHub topics only allow lowercase
letters/numbers/hyphens, so anything with other punctuation may need a
manual tweak either in `teams.json` or via `--team-topic-prefix`.
