# Deployment Manifest Generator

Scans every ECS and EKS cluster you point it at, reads the container image
actually deployed by each service/deployment, resolves that image's tag
back to a GitHub commit, and writes an HTML report grouped by
**Team -> Environment -> Cluster -> Service**, with links into both the AWS
console and GitHub. Three modes:

- `--mode current` (default) -- what's deployed right now
- `--mode history --start-date ... --end-date ...` -- what changed during
  a date range (defaults to the last 90 days if no dates given)
- `--mode asof --as-of YYYY-MM-DD` -- a snapshot of what was live as of a
  specific past date

It's a plain script, not a service -- run it by hand, wire it into a Harness
pipeline stage, or cron it later. No infrastructure to stand up.

## Quick start (no AWS/GitHub needed)

```bash
pip install -r requirements.txt --break-system-packages   # or use a venv
python generate_report.py --demo                                # current state
python generate_report.py --demo --mode history                 # last 90 days
python generate_report.py --demo --mode asof --as-of 2026-06-01  # as of a date
open deploy-report.html      # (or just double-click it)
```

That renders output from built-in fake data, so you can see all three
report styles and sanity-check the design before touching real credentials.

## Real setup

1. **Tag your clusters.** This tool reads team/environment off AWS tags
   (you said this is already how you organize things). By default it looks
   for tags named `Team` and `Environment`, case-insensitively -- change
   `tags.team_key` / `tags.environment_key` in the config if yours are
   named differently (`Owner`, `Stage`, whatever).

2. **Copy and edit the config:**
   ```bash
   cp config.example.yaml config.yaml
   ```
   Fill in your AWS profile(s)/regions. If your ECS and EKS clusters span
   multiple AWS accounts, add one entry per account under `aws.profiles`
   (there's a commented-out example using `sts:AssumeRole`).

3. **IAM permissions** the identity running this script needs, read-only:
   - ECS: `ecs:ListClusters`, `ecs:DescribeClusters`, `ecs:ListServices`,
     `ecs:DescribeServices`, `ecs:DescribeTaskDefinition`, and
     `ecs:ListTaskDefinitions` (the last one is only needed for
     `--mode history` / `--mode asof`, to walk a family's revisions)
   - EKS: `eks:ListClusters`, `eks:DescribeCluster`

4. **EKS workload discovery** needs two more things, because Deployments
   live in the Kubernetes API, not the AWS API:
   - the **AWS CLI v2** installed and on `PATH` (the script shells out to
     `aws eks update-kubeconfig` per cluster so you don't have to
     pre-populate kubeconfig contexts by hand), and
   - the IAM identity running the script mapped in each cluster's
     `aws-auth` ConfigMap (or EKS access entries) with at least a
     read-only `view`-style ClusterRole bound cluster-wide, so it can list
     Deployments in every namespace.

   If either of those isn't set up for a given cluster, that one cluster
   shows up in the report with a warning instead of aborting the whole run
   -- see `checkout-prod` in the demo output for what that looks like.
   The same RBAC binding covers `--mode history` / `--mode asof` too (a
   standard `view` ClusterRole already includes read access to
   ReplicaSets, which is what those modes read).

5. **GitHub linking.** By default the GitHub repo name is guessed from the
   image name (`payments-api` image -> `your-org/payments-api` repo). If
   that doesn't match your naming, add entries under `github.repo_overrides`.
   Set `GITHUB_TOKEN` (a PAT with repo read access) as an env var to raise
   the API rate limit from 60/hr to 5,000/hr -- without it the script still
   works, it just links to `github.com/.../commit/<sha>` without pulling
   the commit message/author.

6. **Run it:**
   ```bash
   python generate_report.py --config config.yaml
   ```

## How it determines "what's deployed"

- **ECS**: for each service, it reads the task definition from the
  service's `PRIMARY` deployment (i.e. what's actually serving traffic
  right now, not a stuck or rolled-back one), and pulls the image tag off
  every container in that task def.
- **EKS**: for each Deployment (all namespaces), it reads the image off
  every container in the pod template.
- **Commit resolution**: the tag is matched against a few common
  conventions in order -- the whole tag is a SHA, the tag ends in
  `-g<sha>` (a common `git describe` style), a custom regex from config,
  or (last resort) any hex-looking substring. This is a heuristic, not a
  guarantee -- a `?` next to a commit link in the report means it couldn't
  be verified against the GitHub API. If your team uses build numbers with
  no SHA in the tag at all, you'll need to either start embedding the
  commit SHA in the image tag at build time (recommended -- this is the
  most reliable fix) or add a `tag_sha_pattern` in config that matches
  however your CI encodes it.

## Date-range history and as-of snapshots

`--mode history` and `--mode asof` don't call any new AWS service -- they
read version history that ECS and EKS already keep on their own:

- **ECS**: every task definition revision ever registered for a family
  stays describable indefinitely (active or not), each stamped with
  `registeredAt`. The script walks a service's family backwards from
  today until it's covered your requested date range.
- **EKS**: every Deployment keeps its old ReplicaSets around (that's how
  `kubectl rollout undo` works), each stamped with its creation time and
  carrying the pod template's image.

```bash
# last 90 days (the default)
python generate_report.py --config config.yaml --mode history

# a specific range
python generate_report.py --config config.yaml --mode history \
    --start-date 2026-04-01 --end-date 2026-07-01

# what was live on a specific day
python generate_report.py --config config.yaml --mode asof --as-of 2026-05-15
```

Worth knowing going in:

- **Timestamps are a proxy, not an audit log.** `registeredAt` / ReplicaSet
  creation time is "when this version was created", which in a typical
  CI/CD flow (register-and-deploy together, e.g. Harness) is effectively
  "when it went live" -- but it's not a guaranteed record of the actual
  deploy action. A revision registered but never deployed would still
  show up as a leg. If you need an exact audit trail of the API calls
  themselves, the next step up is CloudTrail's `UpdateService` event
  history -- not implemented here, and capped at ~90 days unless you
  already have a long-retention trail.
- **EKS history is capped by `revisionHistoryLimit`** (default 10 old
  ReplicaSets per Deployment). A service deploying many times a day can
  exceed that within even a 90-day window; when the report can't find a
  revision from before your requested start date *and* the cap looks
  hit, it says so with a warning rather than silently showing a partial
  timeline.
- **Deleted services/deployments won't appear.** Both modes start from
  what still exists today and walk its history backwards -- a service
  that existed for part of the window but was torn down before you ran
  the report isn't in the output.
- **`--mode asof` doesn't have desired/running counts** -- those aren't
  retained historically, so the health column shows "n/a" instead of a
  status dot. Everything else (image tag, commit, links) is real.

## Cross-checking against Harness and New Relic

`--mode history` can optionally pull in two more independent sources and
show them alongside the ECS/EKS-derived timeline for each service, so you
can sanity-check the reconstructed dates against systems that recorded the
deploy directly rather than inferring it from a revision timestamp:

- **Harness pipeline execution history** -- since Harness is the thing
  actually doing the deploying, its execution records (pipeline, artifact
  version, who/what triggered it, status) are a more direct source of
  truth than "when was this task def registered."
- **New Relic deployment markers**, queried with NRQL -- independently
  timestamped by whatever recorded the marker (your Harness step, a CI
  job, etc.), so it's a useful third opinion.

Both are opt-in (`enabled: false` by default in `config.example.yaml`) and
additive -- turning them on doesn't change ECS/EKS discovery at all, and a
lookup failure for one service just shows a warning on that service rather
than breaking the report.

```bash
export HARNESS_API_KEY=...
export NEW_RELIC_API_KEY=...
python generate_report.py --config config.yaml --mode history
```

**Setup:**
- Harness: set `harness.enabled: true`, `account_id`, and at least one
  `org_id`/`project_id` under `scopes` (add more entries if your services
  are spread across multiple Harness projects). The API key needs read
  access to pipeline executions in those scopes.
- New Relic: set `newrelic.enabled: true`, `account_id` (the numeric one,
  not the account name), and use a **User API key** (starts with `NRAK-`)
  with query access to that account.
- Both assume the ECS/EKS service name matches the Harness Service
  identifier / New Relic entity name; add entries under
  `service_id_overrides` / `entity_name_overrides` where it doesn't.

**Being upfront about what's verified and what isn't:** the HTTP request
shape for both (endpoint, auth header, query/body structure) is confirmed
against current Harness and New Relic docs. What varies by account is the
*exact field layout inside each response* -- Harness's execution summary
nests service/artifact info a bit differently depending on which CD module
version and stage types you use, and New Relic deployment markers can live
in either the classic `Deployment` event type or the newer
`changeTrackingEvent` type depending on how your pipelines report them
(`newrelic.event_type` in config controls which).

Rather than guess and risk silently showing wrong data, both integrations:
- parse defensively (a record that doesn't match the expected shape is
  skipped rather than crashing the report or showing garbage), and
- come with a one-shot diagnostic to check your actual data first:
  ```bash
  python generate_report.py --config config.yaml --dump-harness-sample YOUR_SERVICE_ID
  python generate_report.py --config config.yaml --dump-newrelic-sample YOUR_ENTITY_NAME
  ```
  Each writes a small raw JSON file so you can confirm the field names
  match before trusting the parsed output. If they don't, `_parse_execution`
  in `harness_client.py` and `_parse_marker` in `newrelic_client.py` are
  the two places to adjust -- both are single, short functions.

## Linking to Nexus and Jira

Two more optional, additive integrations -- both off by default, both
applicable to every mode (current/history/asof) since they're about the
image itself, not about time ranges.

**Nexus.** If your images are stored in a Nexus-hosted Docker registry,
enable `nexus.enabled` and map the registry host:port that shows up in
your deployed image URIs (Nexus commonly runs one port per Docker repo)
to the Nexus repository name that serves it:

```yaml
nexus:
  enabled: true
  base_url: https://nexus.yourcompany.com
  registry_repository_map:
    "nexus.yourcompany.com:8083": team-images
```

Each deployed image then gets a "nexus ↗" link, using Nexus's documented
Search API (`/service/rest/v1/search`) rather than the Angular web UI's
undocumented, version-fragile hash routes -- so this is a stable
integration, not a guess.

Set `detect_base_image: true` to also show what an image was built FROM,
by reading the two official OCI annotations
(`org.opencontainers.image.base.name` / `.base.digest`) off the image
manifest. This only finds something if your build pipeline actually sets
them -- BuildKit does this automatically for OCI-format output, but a
plain `docker build` generally doesn't unless you add the label
yourself. No annotation found just means "not recorded", not a guess.

**Jira.** If commits or PR titles reference issues by key (`TEAM-1856:
fix the thing`), set `jira.base_url` and every such key gets extracted
and turned into a clickable link automatically -- no credentials needed
for the link itself, since the format (`{base_url}/browse/{KEY}`) is
always correct:

```yaml
jira:
  enabled: true
  base_url: https://yourcompany.atlassian.net
```

Set `fetch_details: true` (plus `JIRA_EMAIL` / `JIRA_API_TOKEN` env vars)
to also show the issue's live summary and status instead of a bare key --
this uses Atlassian Cloud's Basic-auth convention (email + API token from
id.atlassian.com). On Jira Server/Data Center, swap the `auth=` line in
`jira_client.py`'s `fetch_issue()` for a Bearer personal access token
instead -- one line, called out in that file's docstring.

## Team repo registry and coverage

Everything so far cross-checks *deployed* images. This adds the other
half: an authoritative list of which repos each team actually owns, so
the report can flag two kinds of gap that are otherwise invisible --
a repo that's registered to a team but never shows up deployed anywhere
(dead code? forgot to wire it up? wrong name somewhere?), and a deployed
image whose repo isn't registered to any team (unregistered, or a naming
mismatch worth checking). Applies to every mode.

**Start simple -- a JSON file you maintain by hand:**

```yaml
github:
  team_registry:
    mode: static
    static_file: teams.json
```

```json
{
  "Payments": ["myorg/payments-api", "myorg/payments-worker"],
  "Checkout": ["myorg/cart-service", "myorg/checkout-web"]
}
```

See `teams.example.json` for a starting point. Each team's section in the
report gets a coverage line ("6/8 registered repos seen deployed") with
expandable lists of anything that doesn't line up.

**Later -- derive it from GitHub topics instead, with nothing to keep in
sync by hand:**

```yaml
github:
  team_registry:
    mode: github_topics
    org: myorg
    team_topic_prefix: "team-"    # a repo tagged "team-payments" -> team "Payments"
```

This lists every repo in the org and buckets them by a `team-<name>`
topic (GitHub's repo-level tags) -- so the source of truth becomes
whatever topics are actually applied on GitHub, not a file someone has to
remember to update. Team name matching against your AWS `Team` tags is
case-insensitive, but the spelling still needs to line up (`team-payments`
-> "Payments" matches an AWS tag value of "Payments" or "payments", not
"Payments Team").

**Getting from the JSON file to topics:** see `admin-tools/manage_team_topics.py`
-- a deliberately separate script (it *writes* to GitHub, so it's not part
of this read-only report tool) that applies `team-<name>` topics to every
repo listed in your `teams.json`, with a dry run by default and a
`--report` flag for an audit trail. Run it once your JSON file is accurate,
then flip `team_registry.mode` to `github_topics` and stop maintaining the
file at all.

## Running this as a Harness pipeline step

(Note: this is about running the *script* from Harness -- see the section
above for querying Harness's *own* deployment data.)

Add it as a shell step, e.g. after any deploy stage, or as its own
scheduled pipeline:

```yaml
- step:
    type: ShellScript
    name: Generate Deployment Manifest
    spec:
      shell: Bash
      source:
        type: Inline
        spec:
          script: |
            pip install -r requirements.txt --break-system-packages
            export GITHUB_TOKEN=<+secrets.getValue("github_token")>
            python generate_report.py --config config.yaml --output deploy-report.html
            # then publish deploy-report.html as a pipeline artifact,
            # or aws s3 cp it somewhere your team can bookmark
```

## Files

```
generate_report.py       CLI entry point (current / history / asof modes)
discovery/
  common.py              tag lookup, commit-SHA extraction, container parsing
  ecs.py                 ECS current-state discovery
  eks.py                 EKS current-state discovery
  ecs_history.py         ECS history via task definition revisions
  eks_history.py         EKS history via ReplicaSet revisions
github_lookup.py         GitHub commit resolution (cached, rate-limit aware)
harness_client.py        Harness execution history (optional, --mode history)
newrelic_client.py       New Relic deployment markers via NRQL (optional, --mode history)
nexus_client.py          Nexus image links + base-image detection (optional, all modes)
jira_client.py           Jira issue key extraction/linking (optional, all modes)
team_registry.py         loads team -> repos, from a JSON file or GitHub topics
enrichment.py            attaches Harness/New Relic/Nexus data onto services
report_renderer.py       groups data + renders the HTML templates
templates/
  _base_styles.html      shared CSS, included by both templates below
  report_template.html   current-state / as-of report
  history_template.html  date-range history report
demo_data.py             fake data for --demo (all three modes + all cross-checks)
config.example.yaml      copy to config.yaml and edit
teams.example.json       copy to teams.json and edit -- team -> repos registry
requirements.txt
admin-tools/
  manage_team_topics.py  writes team-* topics to GitHub from teams.json (separate, has its own README)
  README.md
```

## Known limitations / next steps

- Multi-container tasks (sidecars) show one row per container -- useful
  for spotting a stale log-forwarder, but can make dense task defs noisy.
- GitHub Enterprise Server (not github.com) isn't wired up yet -- swap the
  API base URL in `github_lookup.py` if that's your setup.
- This is a one-off script today. If you later want it running on a
  schedule instead of on demand, the natural next step is a small Lambda
  (or a scheduled Harness pipeline) that runs `generate_report.py` and
  uploads the HTML to S3 behind a fixed URL your team can bookmark --
  happy to help wire that up once the on-demand version is proven out.
