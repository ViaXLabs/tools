# New Relic ← AWS Metric Stream — Diagnostics

Two standalone Python scripts that diagnose why a New Relic + AWS
CloudWatch Metric Stream (Firehose) integration isn't delivering data.
They're split so each can run on the machine that has the right access:

- **`diagnose_aws.py`** — run on the box with AWS access (e.g. an Ubuntu
  jump host). Needs `boto3` only.
- **`diagnose_newrelic.py`** — run wherever you have your New Relic User
  key (e.g. your Mac). Needs `requests` only.

Each is fully self-contained — no shared module, no dependency on the
other file. They walk the data path hop by hop and end with a
plain-English verdict plus an exit code you can gate CI on.

```
CloudWatch → Metric Stream → Firehose → NR endpoint → NRDB
    (src)         (2)           (3)         (4)        (5)
                  └──────── diagnose_aws.py ─────────┘  └ diagnose_newrelic.py ┘
```

## Why Python (not bash)

An earlier version was bash. Python fits better because the work is
mostly JSON + API calls: no `jq`, no shell-quoting games, `boto3`/`requests`
give structured data and real error handling, it's portable across
Linux/macOS with no `date` branching, and the parsing logic is unit-tested.
Tradeoff: needs a library installed per script (below).

---

## `diagnose_aws.py`  (run on the AWS-access machine, e.g. Ubuntu)

### Setup
```bash
pip install boto3
```
Authenticate with your normal AWS credential chain (`aws configure`,
`aws sso login`, or `AWS_PROFILE`). The identity needs read access to
CloudWatch, Firehose, S3 (the backup bucket), and optionally AWS Config.
Read-only — makes no changes.

### Run
```bash
./diagnose_aws.py --name prod --region us-east-1
```
- `--name` — the `var.name` suffix from your Terraform. Resource names are
  derived: `newrelic-metric-stream-<name>`, `newrelic_firehose_stream_<name>`.
- `--region` — **must match the region your metric stream lives in**, or
  every throughput/delivery check reads zero and the verdict misleads.

### Checks
| § | Check | Why |
|---|-------|-----|
| 0 | AWS credentials | Fail fast if not authenticated. |
| 1 | Metric Stream state + output format | Must be `running`; flags `opentelemetry0.7`. |
| 2 | `MetricUpdate` / `PublishErrorRate` | Stream emitting? errors → stream IAM role. |
| 3 | Firehose status, `IncomingRecords`, `DeliveryToHttpEndpoint.Success` | Localizes stream→firehose vs firehose→NR. Flags US/EU endpoint. |
| 4 | Firehose CloudWatch error logging | Are delivery errors logged? gives the read command. |
| 5 | **S3 backup object count** | Decisive: rejected records land here → NR is refusing data. |
| 6 | AWS Config recording | Off = metrics flow but entities poorly enriched. |

---

## `diagnose_newrelic.py`  (run wherever your NR key is, e.g. Mac)

### Setup
```bash
pip install requests
export NR_API_KEY="NRAK-xxxxxxxxxxxx"   # USER key, not a license/ingest key
export NR_ACCOUNT_ID="1234567"
export NR_REGION="US"                   # US or EU (default US)
```
(Or pass `--api-key` / `--account-id` / `--region`.) Read-only.

> Must be a **User key** (`NRAK-…`). Ingest/license keys won't authenticate
> against NerdGraph.

### Run
```bash
./diagnose_newrelic.py
```

### Checks
| § | Check | Why |
|---|-------|-----|
| 0 | API key / access | Fail fast on bad key or wrong region. |
| 1 | Linked AWS accounts + integrations | Did the Terraform `link_account` step register? |
| 2 | `count(*)` metric-stream data (30 min) | Is data landing in NRDB? |
| 3 | `uniques(aws.Namespace)` | Which namespaces; empty → include/exclude filters. |
| 4 | `FACET aws.MetricStreamArn` | Confirms data is from *your* stream. |
| 5 | Ingest timeseries (5 min) | Freshness — flowing now or stopped? |

---

## Exit codes (for CI / gating)

Both scripts use the same convention:

| Code | Meaning |
|------|---------|
| `0` | Healthy — data flowing / delivering. |
| `2` | Broken — a concrete pipeline problem was found. |
| `3` | Error — couldn't run (missing dep, bad/absent credentials, non-numeric account id, auth failure). |

---

## Reading the two together

Run `diagnose_aws.py` first, then `diagnose_newrelic.py`. Combine verdicts:

| AWS side | NR side | Diagnosis |
|----------|---------|-----------|
| `DeliveryToHttpEndpoint.Success` > 0 | No data in NRDB | **Region / key / account mismatch** on the Firehose endpoint. Most common. |
| S3 backup has objects | No data in NRDB | NR is **rejecting** the data — read a backup object. |
| Firehose `IncomingRecords` = 0 | — | Break is **stream → firehose**: IAM role missing `firehose:PutRecord`. |
| `MetricUpdate` = 0 | — | Stream not emitting: include/exclude filters or no source metrics. |
| Delivery succeeds | No **linked account** | The `link_account` resource never registered — re-apply. |

### Most likely culprit for the default Terraform config
The Terraform defaults to the **US** endpoint. If your New Relic account
is **EU**, Firehose silently fails into the S3 backup bucket: AWS §3 flags
the endpoint, AWS §5 shows rejected records, NR §2 shows zero data. Fix by
setting the provider `region = "EU"` and the EU Firehose URL, then re-apply.

### Inspecting a rejected record
```bash
aws s3 cp s3://<backup-bucket>/<key> - | gunzip | jq .
```

---

## Testing

Smoke test each:
```bash
python3 -m py_compile diagnose_aws.py diagnose_newrelic.py
./diagnose_aws.py --help
./diagnose_newrelic.py --help
```

The NR parsing helpers (`_gql_str`, `_nrql_results`, `_nrql_first`) are
tested against mocked NerdGraph responses (data present, empty, error,
`uniques()` shape, malformed JSON), the full render path via a mocked HTTP
layer, and the verdict→exit-code mapping across healthy / linked-no-data /
not-linked / bad-account-id.

### What was NOT tested
Neither script was run end-to-end against a live AWS account or New Relic
org during authoring (no credentials / network in the build environment).
Logic, formatting, CLI, parsing, and exit codes are verified; treat your
first live run as the real validation.
