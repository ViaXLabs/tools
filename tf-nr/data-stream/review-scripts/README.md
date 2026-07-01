# New Relic ← AWS Metric Stream — Diagnostics

Two scripts to diagnose why a New Relic + AWS CloudWatch Metric Stream
(Firehose) integration isn't delivering data. They walk the data path
hop by hop and end with a plain-English verdict telling you *which* hop
is broken.

```
CloudWatch → Metric Stream → Firehose → NR endpoint → NRDB
    (src)         (2)           (3)         (4)        (5)
                  └──────── diagnose_aws_side.sh ───────┘  └ diagnose_newrelic_side.sh ┘
```

- **`diagnose_aws_side.sh`** — checks everything up to and including the
  handoff to New Relic (stream state, throughput, Firehose delivery, S3
  backup, error logging, AWS Config).
- **`diagnose_newrelic_side.sh`** — checks the New Relic side (is the AWS
  account actually linked, and is metric-stream data landing in NRDB).

---

## Prerequisites

| Tool | Used by | Notes |
|------|---------|-------|
| `bash` | both | Scripts use bash-only features; run with bash, not `sh`. |
| `jq` | both | JSON parsing / safe payload building. |
| `awscli` v2 | AWS script | Must be authenticated (see below). |
| `curl` | NR script | For NerdGraph calls. |

Install `jq` if missing: `brew install jq` (macOS) / `apt-get install jq` (Debian/Ubuntu).

Portable across **Linux (GNU)** and **macOS (BSD)** — the date handling
auto-detects which environment it's on.

---

## `diagnose_aws_side.sh`

### Auth

Uses your normal AWS credentials. Any of these work:

```bash
aws configure          # static keys
aws sso login          # SSO
export AWS_PROFILE=... # named profile
```

The IAM identity you run as needs read access to CloudWatch, Firehose,
S3 (the backup bucket), and optionally AWS Config.

### Usage

```bash
./diagnose_aws_side.sh <NAME> [REGION]
```

- `<NAME>` — the `var.name` suffix used in your Terraform (e.g. `prod`).
  The script derives resource names from it:
  - metric stream: `newrelic-metric-stream-<NAME>`
  - firehose:      `newrelic_firehose_stream_<NAME>`
- `[REGION]` — AWS region. Defaults to `us-east-1`.

Example:

```bash
./diagnose_aws_side.sh prod us-east-1
```

### What it checks

| Section | Check | Why it matters |
|---------|-------|----------------|
| 0 | AWS credentials | Fail fast if not authenticated. |
| 1 | Metric Stream state + output format | Must be `running`; flags `opentelemetry0.7` (1.0 is current). |
| 2 | `MetricUpdate` / `PublishErrorRate` | Confirms the stream is actually emitting; errors point at the stream IAM role. |
| 3 | Firehose status, `IncomingRecords`, `DeliveryToHttpEndpoint.Success` | Localizes stream→firehose vs firehose→NR breaks. Flags US/EU endpoint. |
| 4 | Firehose CloudWatch error logging | Tells you if delivery errors are being logged (and the command to read them). |
| 5 | **S3 backup bucket object count** | The decisive check — rejected records land here. Objects present = NR is refusing the data. |
| 6 | AWS Config recording | Off = metrics still flow but entities are poorly enriched. |

---

## `diagnose_newrelic_side.sh`

### Auth

```bash
export NR_API_KEY="NRAK-xxxxxxxxxxxx"   # User API key (NOT a license/ingest key)
export NR_ACCOUNT_ID="1234567"
export NR_REGION="US"                   # US or EU — default US
```

> The key must be a **User key** (`NRAK-…`). Ingest/license keys will not
> authenticate against NerdGraph.

### Usage

```bash
./diagnose_newrelic_side.sh
```

### What it checks

| Section | Check | Why it matters |
|---------|-------|----------------|
| 0 | API key / access | Fail fast on bad key or wrong region. |
| 1 | Linked AWS accounts + integrations | Confirms the Terraform `link_account` step registered. No link = nothing else matters. |
| 2 | `count(*)` of metric-stream data (30 min) | Is data actually landing in NRDB? |
| 3 | `uniques(aws.Namespace)` | Which namespaces arrive; empty points at include/exclude filters. |
| 4 | `FACET aws.MetricStreamArn` | Confirms the data is from *your* stream. |
| 5 | Ingest timeseries (per 5 min) | Freshness — is it flowing *now* or did it stop? |

---

## Reading the two together

Run the **AWS script first**, then the NR script. Combine the verdicts:

| AWS side | NR side | Diagnosis |
|----------|---------|-----------|
| `DeliveryToHttpEndpoint.Success` > 0 | No data in NRDB | **Region / key / account mismatch** on the Firehose endpoint. Most common cause. |
| S3 backup has objects | No data in NRDB | NR is **rejecting** the data. Read a backup object for the exact reason. |
| Firehose `IncomingRecords` = 0 | — | Break is **stream → firehose**: metric-stream IAM role missing `firehose:PutRecord`. |
| `MetricUpdate` = 0 | — | Stream isn't emitting: **include/exclude filters** or no source metrics. |
| Delivery succeeds | No **linked account** in NR | The `link_account` resource never registered — re-apply it. |

### Most likely culprit for the default config

The Terraform defaults to the **US** endpoint. If your New Relic account
is **EU**, the Firehose silently fails into the S3 backup bucket:

- AWS section 3 will flag the endpoint region.
- AWS section 5 will show rejected records.
- NR section 2 will show zero data.

Fix by setting the New Relic provider `region = "EU"` and the EU Firehose
URL, then re-apply.

---

## Inspecting a rejected record (manual)

When section 5 reports objects in the backup bucket, pull one and read
New Relic's HTTP response:

```bash
aws s3 cp s3://<backup-bucket>/<key> - | gunzip | jq .
```

The response body contains the rejection reason (bad key, wrong format,
etc.).

---

## Limitations / honesty

- These scripts were syntax-checked and their formatting/date/escaping
  logic was tested, but they were **not** run end-to-end against a live
  AWS account or New Relic org during authoring. Treat your first run as
  the real validation.
- They are **read-only** — they make no changes to AWS or New Relic.
- If a section returns empty where you expect data, it's usually a
  permissions gap (AWS) or a wrong key/region (NR) rather than a script
  bug — but if output looks wrong, capture it and it's easy to adjust.
