Let me check what's available in the environment before building this out.Got it — this is a real, buildable system. Let me lay out my understanding and the assumptions I'm making, then give you working code.

**What I heard:** Your Harness pipeline needs to pull down XLSX files from (at least) two S3 buckets in the non-prod AWS account, then run a transform that:

- normalizes a "team" label to "program"
- normalizes a "measured" label to "coverage"
- pulls the coverage % out of a "score" field
- flags rows where score = 0 as needing remediation
- filters/drops irrelevant rows
- merges the two sources into one final workbook for your customer

Since you said you're recalling this from a friend's doc rather than having it in front of you, I built this so the _exact_ column names and relabeling rules live in one small CONFIG block at the top — you can fix those in 30 seconds once you check the doc, without touching the pipeline logic.

Let me build and test it against synthetic data first so I know the logic actually works.The mechanics work — but running it against realistic sample data exposed a real fork in the road, so let me flag that before finalizing.**How the system fits together:**

- `harness_pipeline_stage.yaml` — a Harness stage that installs deps and runs the script against your non-prod AWS account (via your existing AWS connector or delegate role).
- `coverage_metrics_pipeline.py` — downloads each bucket's XLSX with boto3, cleans/normalizes it, flags zero-score rows for remediation, merges everything, and writes a final workbook (with a separate "Remediation" tab and red-highlighted rows) — optionally uploading it back to S3.

I tested the transform logic end-to-end against fake data and it runs cleanly — but that test surfaced a real ambiguity I don't want to guess wrong on, since it changes the actual parsing code (not just a config tweak):

**Shape A — "wide" table** (what I built for): each row is already one team/metric record, e.g.

| Team     | Measured | Score |
| -------- | -------- | ----- |
| checkout | coverage | 82    |
| billing  | coverage | 0     |

**Shape B — "key-value" blocks**: the words "team", "measured", "score" are literally _labels in a column_, and the real values (the actual team name, the actual metric name) live in a separate value column, e.g.

| Field    | Value    |
| -------- | -------- |
| team     | checkout |
| measured | coverage |
| score    | 82       |

Your phrasing ("the row that has team... select that to program") actually reads more like Shape B. If your source file looks like Shape B, I need to rewrite `normalize()` to pivot those key-value blocks into records first — the S3 download, merge, and output/highlighting logic stay exactly the same either way.

Good — that's exactly the shape the script was built for, so no rewrite needed. Let me re-verify with more realistic sample data (my first test used literal placeholder values that accidentally could have masked a real bug).Confirmed — with real team names in the data, it comes out correctly: actual team names preserved in the `Program` column, only the coverage-type rows kept, `billing` and `payments` correctly flagged with `Needs Remediation = True` since their score is 0. The "bugs" row got filtered out as it should. The files I already sent you are good to go as-is — no changes needed.

**Before you run it for real, three things to fix in the `CONFIG` block at the top of `coverage_metrics_pipeline.py`:**

1. `SOURCES` — swap in your two real bucket names and object keys.
2. `RAW_CATEGORY_COLUMN` / `RAW_METRIC_COLUMN` / `RAW_SCORE_COLUMN` — confirm these three header names match your file exactly (case matters).
3. `OUTPUT_BUCKET` / `OUTPUT_KEY_TEMPLATE` — where the finished customer report lands, or set `UPLOAD_TO_S3 = False` if Harness should just grab it as a build artifact instead (there's a commented step for that in the YAML).

One more thing worth deciding: right now if the same team shows up in _both_ buckets, the report keeps both rows side-by-side (tagged by `Source`) rather than merging them into one line. If your customer wants one row per team instead, that's a small change to `merge_sources()` — just let me know which behavior you want once you've seen it against real data.
