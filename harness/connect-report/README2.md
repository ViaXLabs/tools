# Deployment reporting pipeline

A Harness pipeline that pulls deployment context from Harness, GitHub, AWS
(ECS/EKS), ArgoCD, Jira, and Confluence; normalizes it into one record per
deployment; drops it in S3; and publishes an HTML report to a Confluence page.

## Layout

```
harness/
  pipeline.yaml                    - the full pipeline (fetch -> normalize/store -> report)
  connectors/
    jira-connector.yaml            - confirmed schema from Harness docs
    confluence-connector.yaml      - modeled on Jira's schema, verify against your UI
fetch/
  harness.sh, github.sh, aws.sh, argocd.sh, jira.sh, confluence.sh
normalize.py                       - combines fetched/*.json into one record
store.py                           - uploads the record to S3
report.py                          - renders a static HTML report from recent S3 records
publish_confluence.py              - always publishes that report to a Confluence page
```

## Set up the two connectors first

1. In Harness, create the Jira connector using `harness/connectors/jira-connector.yaml`
   as a starting point (this schema is confirmed from Harness's docs).
2. Create a Text Secret called `jira_api_token` (ideally sourced through your
   Vault secret manager connection, not typed in directly) and point the
   connector's `passwordRef` at it.
3. For Confluence: create the connector by hand in the Harness UI first
   (search "Confluence" when adding a new connector), export it as YAML, and
   diff it against `harness/connectors/confluence-connector.yaml` - I modeled
   that file on Jira's confirmed pattern since I couldn't verify Confluence's
   exact field names. Fix `fetch/confluence.sh` and `publish_confluence.py`
   only if the actual field names change what you pass in - both scripts
   just need the secret identifier (`confluence_api_token`), not the
   connector's internal shape.
4. Same pattern for New Relic and Nexus: create `harness/connectors/newrelic-connector.yaml`
   and `harness/connectors/nexus-connector.yaml` in Harness, with secrets
   `newrelic_api_key` and `nexus_password`. New Relic's field names are
   confirmed from Harness's schema; Nexus's are modeled on the confirmed
   Docker connector pattern - same "check it against the UI once" note as
   Confluence, just lower risk since Nexus connectors are long-established.

   New Relic specifically supports two query paths (`NEW_RELIC_API_MODE`):
   `nerdgraph` (default, current/recommended) or `insights` (the older REST
   Insights Query API - **New Relic has deprecated this in favor of
   NerdGraph**, so treat it as a fallback, not the primary path). They use
   different credential types - if you want `insights` or `both`, create a
   second secret `newrelic_insights_query_key` (a Query Key, generated
   separately from the User API key `newrelic_api_key` used for NerdGraph).
5. Same secret pattern for the remaining sources: `harness_api_key`,
   `github_token`, `argocd_token` - all as Harness secrets, all backed by
   Vault where possible.

**Why connectors + scripts, not connectors alone:** Harness's native Jira
steps (Create/Update/Approval) and - as far as I could confirm - Confluence's
native capabilities don't include an arbitrary "search issues" or "list
pages" step. So the connectors give you one tested, auditable credential per
system; the actual read calls still happen in the fetch scripts, reusing
that same credential rather than a second one.

## Environment variables by script

| Script | Requires |
|---|---|
| `fetch/harness.sh` | `HARNESS_API_KEY`, `HARNESS_ACCOUNT_ID`, `HARNESS_ORG_ID`, `HARNESS_PROJECT_ID`, `HARNESS_EXECUTION_ID` |
| `fetch/github.sh` | `GITHUB_TOKEN`, `GITHUB_REPO`, `COMMIT_SHA` |
| `fetch/aws.sh` | `AWS_REGION`, `CLUSTER_TYPE` (ecs/eks), `CLUSTER_NAME`, plus `ECS_SERVICE_NAME` or `EKS_NAMESPACE`/`EKS_DEPLOYMENT_NAME` |
| `fetch/argocd.sh` | `ARGOCD_SERVER`, `ARGOCD_TOKEN`, `ARGOCD_APP_NAME` |
| `fetch/jira.sh` | `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, and either `JIRA_ISSUE_KEYS` or `JIRA_JQL` |
| `fetch/confluence.sh` | `CONFLUENCE_BASE_URL`, `CONFLUENCE_EMAIL`, `CONFLUENCE_API_TOKEN`, `CONFLUENCE_SPACE_KEY` |
| `fetch/newrelic.sh` | `NEW_RELIC_ACCOUNT_ID`, `NEW_RELIC_API_MODE` (`nerdgraph`/`insights`/`both`, default `nerdgraph`), `NEW_RELIC_API_KEY` (NerdGraph), `NEW_RELIC_INSIGHTS_QUERY_KEY` (Insights - separate credential type), `NEW_RELIC_REGION` (optional, default `us`), `NEW_RELIC_ENTITY_NAME` |
| `fetch/nexus.sh` | `NEXUS_SERVER_URL`, `NEXUS_USERNAME`, `NEXUS_PASSWORD`, `NEXUS_REPOSITORY`, `NEXUS_COMPONENT`, `NEXUS_VERSION` |
| `store.py` | `S3_BUCKET` (`S3_PREFIX` optional) |
| `report.py` | `S3_BUCKET` (`REPORT_DAYS_BACK` optional, default 7) |
| `publish_confluence.py` | `CONFLUENCE_BASE_URL`, `CONFLUENCE_EMAIL`, `CONFLUENCE_API_TOKEN`, `CONFLUENCE_SPACE_KEY` |

All secrets above (anything ending in `_TOKEN`, `_KEY`) should be Harness
secrets, not plain pipeline variables.

## Storage: deliberately lite

`store.py` writes one JSON file per deployment to S3, partitioned
`deployment-reports/YYYY/MM/DD/service/HHMMSS.json`. No database. `report.py`
lists the last N days of objects under that prefix and renders them into one
HTML page - that's the entire "query layer."

## Reporting: always goes to Confluence

`publish_confluence.py` is not gated behind a toggle - every pipeline run
creates or updates one Confluence page per report. The HTML `report.py`
writes uses inline styles rather than a `<style>` block, since Confluence's
storage format strips `<style>` blocks.

## Not yet wired in (by design, for now)

- Security/quality posture - Nexus IQ, Prisma Cloud/Twistlock, Tenable.io,
  SonarQube/Checkmarx. You said you're not worried about scan data right
  now, so `security` in the normalized record stays a placeholder.
- The rest of observability - Prometheus, Grafana, Splunk. New Relic is in;
  these three are still open questions per your last message.

Both slot in the same way everything else did: a `fetch/*.sh`, a Harness
secret (ideally reusing an existing connector's, same pattern as Jira/
Confluence/New Relic/Nexus), and a couple of lines in `normalize.py`.
`report.py`'s table doesn't surface the new `artifact`/`health` fields yet -
they're in the JSON record, just say the word if you want them as columns
too.
