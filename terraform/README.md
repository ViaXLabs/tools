Good, CLI structure checks out. Let me also verify the `clear --index` flow against a fake cached report.Both flows work correctly.Two subcommands, one script:

**`report`** — scans whatever DynamoDB tables and S3 buckets you point it at, finds every lock in both places, and prints a numbered table (age, who, path). It also saves that list to `~/.tf_lock_report_cache.json` so the next step doesn't need you to retype anything.

```bash
python3 tf_lock_manager.py report \
    --dynamo-table tf-locks-nonprod --dynamo-table tf-locks-prod \
    --s3-bucket my-tf-bucket
```

**`clear`** — acts on one lock, either by its `--index` from the report, or by giving the type/table/key directly. Two modes:

```bash
# Actually delete it (with confirmation prompt)
python3 tf_lock_manager.py clear --index 2

# Just print the manual AWS CLI command instead of deleting
python3 tf_lock_manager.py clear --index 2 --instructions-only
```

`--instructions-only` is the "give guidance instead of doing it" mode you asked for — useful if you want a teammate to run the delete themselves, or if you want to eyeball the exact command before it runs. `--force` skips the y/n prompt for scripted use later.

A few notes on how it maps to your setup:

- **DynamoDB side**: reads the `LockID` and `Info` JSON that Terraform writes into each lock item — same fields you'd see in a `force-unlock` error (who, operation, created time). Since you're migrating off DynamoDB, this lets you confirm a table is actually empty (safe to decommission) before you tear it down.
- **S3 side**: reuses the same `.tflock` scanning logic from the last script, just now across a whole bucket/prefix instead of one known key.
- **The cache file** is what lets `report` and `clear` be two separate steps — run report, look at the numbered list, come back later (or hand it to someone else) and clear by index without re-scanning.

One thing worth flagging: DynamoDB `scan()` reads the whole table, which is fine for a lock table (should only ever have a handful of items — a lock table with a lot of rows usually means something's stuck), but if any of your tables are large for some other reason, let me know and I'll swap in a query instead.
