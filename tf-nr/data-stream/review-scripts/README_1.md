# New Relic ← AWS Metric Stream — Diagnostics

A single Python tool (`nr_aws_diag.py`) that diagnoses why a New Relic +
AWS CloudWatch Metric Stream (Firehose) integration isn't delivering
data. It walks the data path hop by hop and ends each side with a
plain-English verdict telling you *which* hop is broken.

```
CloudWatch → Metric Stream → Firehose → NR endpoint → NRDB
    (src)         (2)           (3)         (4)        (5)
                  └────────── aws subcommand ─────────┘  └── nr subcommand ──┘
```

## Why Python (not bash)

An earlier version of this was two bash scripts. Python is the better fit
here because the work is mostly JSON handling and API calls:

- **No `jq`, no shell-quoting games.** NerdGraph/NRQL payloads are built
  with real dicts; the fragile quote-escaping that bash needed is gone.
- **`boto3` instead of shelling out to the AWS CLI** — structured objects
  and real per-call error handling instead of parsing text with `2>/dev/null`.
- **Portable by default** — no GNU-vs-BSD `date` branching.
- **Testable** — the parsing logic has real unit tests (see below).

The only tradeoff: Python needs two libraries installed. Bash only needed
the AWS CLI. For correctness and maintainability Python wins.

---

## Prerequisites

- **Python 3.8+**
- `boto3` — for the `aws` subcommand
- `requests` — for the `nr` subcommand

```bash
pip install boto3 requests
```

Each subcommand only needs its own library, and the tool degrades
gracefully (clear "run pip install …" message) if one is missing.

---

## Authentication

### AWS side

Uses your normal AWS credential chain — any of:

```bash
aws configure           # static keys
aws sso login           # SSO
export AWS_PROFILE=...   # named profile
```

The IAM identity needs read access to CloudWatch, Firehose, S3 (the
backup bucket), and optionally AWS Config. The tool is **read-only**.

### New Relic side

```bash
export NR_API_KEY="NRAK-xxxxxxxxxxxx"   # USER key, not a license/ingest key
export NR_ACCOUNT_ID="1234567"
export NR_REGION="US"                   # US or EU (default US)
```

(You can also pass `--api-key` / `--account-id` / `--region` on the CLI.)

> Must be a **User key** (`NRAK-…`). Ingest/license keys won't
> authenticate against NerdGraph.

---

## Usage

```bash
# AWS side only
./nr_aws_diag.py aws --name prod --region us-east-1

# New Relic side only (creds from env)
./nr_aws_diag.py nr

# Both, in one run
NR_API_KEY=NRAK-xxx NR_ACCOUNT_ID=1234567 NR_REGION=US \
  ./nr_aws_diag.py all --name prod --region us-east-1
```

`--name` is the `var.name` suffix from your Terraform. Resource names are
derived from it:
- metric stream → `newrelic-metric-stream-<name>`
- firehose → `newrelic_firehose_stream_<name>`

---

## What it checks

### `aws` subcommand

| Section | Check | Why it matters |
|---------|-------|----------------|
| 0 | AWS credentials | Fail fast if not authenticated. |
| 1 | Metric Stream state + output format | Must be `running`; flags `opentelemetry0.7` (1.0 is current). |
| 2 | `MetricUpdate` / `PublishErrorRate` | Confirms the stream emits; errors point at the stream IAM role. |
| 3 | Firehose status, `IncomingRecords`, `DeliveryToHttpEndpoint.Success` | Localizes stream→firehose vs firehose→NR breaks. Flags US/EU endpoint. |
| 4 | Firehose CloudWatch error logging | Tells you if delivery errors are logged (and the command to read them). |
| 5 | **S3 backup bucket object count** | The decisive check — rejected records land here. Objects present = NR is refusing the data. |
| 6 | AWS Config recording | Off = metrics still flow but entities are poorly enriched. |

### `nr` subcommand

| Section | Check | Why it matters |
|---------|-------|----------------|
| 0 | API key / access | Fail fast on bad key or wrong region. |
| 1 | Linked AWS accounts + integrations | Confirms the Terraform `link_account` step registered. No link = nothing else matters. |
| 2 | `count(*)` of metric-stream data (30 min) | Is data actually landing in NRDB? |
| 3 | `uniques(aws.Namespace)` | Which namespaces arrive; empty points at include/exclude filters. |
| 4 | `FACET aws.MetricStreamArn` | Confirms the data is from *your* stream. |
| 5 | Ingest timeseries (per 5 min) | Freshness — flowing now, or stopped? |

---

## Reading the two sides together

Run `aws` first, then `nr` (or `all`). Combine the verdicts:

| AWS side | NR side | Diagnosis |
|----------|---------|-----------|
| `DeliveryToHttpEndpoint.Success` > 0 | No data in NRDB | **Region / key / account mismatch** on the Firehose endpoint. Most common. |
| S3 backup has objects | No data in NRDB | NR is **rejecting** the data. Read a backup object for the reason. |
| Firehose `IncomingRecords` = 0 | — | Break is **stream → firehose**: IAM role missing `firehose:PutRecord`. |
| `MetricUpdate` = 0 | — | Stream isn't emitting: **include/exclude filters** or no source metrics. |
| Delivery succeeds | No **linked account** | The `link_account` resource never registered — re-apply. |

### Most likely culprit for the default Terraform config

The Terraform defaults to the **US** endpoint. If your New Relic account
is **EU**, the Firehose silently fails into the S3 backup bucket:

- `aws` section 3 flags the endpoint region.
- `aws` section 5 shows rejected records.
- `nr` section 2 shows zero data.

Fix: set the New Relic provider `region = "EU"` and the EU Firehose URL,
then re-apply.

---

## Inspecting a rejected record

When `aws` section 5 reports objects in the backup bucket, pull one and
read New Relic's HTTP response:

```bash
aws s3 cp s3://<backup-bucket>/<key> - | gunzip | jq .
```

The body contains the rejection reason (bad key, wrong format, etc.).

---

## Exit codes (for CI / gating)

The tool's exit code reflects the verdict, so it can gate a pipeline:

| Code | Meaning |
|------|---------|
| `0` | Healthy — data is flowing (or, for the AWS side, delivering successfully). |
| `2` | Broken — a concrete pipeline problem was found (see the section verdicts). |
| `3` | Error — the check couldn't run (missing dependency, bad credentials, non-numeric account id, auth failure). |

For `all`, the worst status across both sides wins (error > broken > healthy).
Running `all` **without** New Relic credentials reports the AWS result rather
than failing solely because NR creds were absent.

---

## Testing

The JSON/NerdGraph parsing — the part that was fragile in bash — has unit
coverage. Quick smoke test:

```bash
python3 -m py_compile nr_aws_diag.py     # compiles
python3 nr_aws_diag.py --help            # CLI parses
```

The parsing helpers (`_gql_str`, `_nrql_results`, `_nrql_first`) were
tested against mocked NerdGraph responses covering: data present, empty
results, error responses, `uniques()` shape, and malformed JSON. The full
`nr` render path was exercised end-to-end with a mocked HTTP layer.

### What was NOT tested

The tool was **not** run end-to-end against a live AWS account or New
Relic org during authoring (no credentials / network in the build
environment). Logic, formatting, CLI, and parsing are verified; treat
your first live run as the real validation. If a section returns empty
where you expect data, it's usually a permissions gap (AWS) or wrong
key/region (NR) rather than a tool bug.
