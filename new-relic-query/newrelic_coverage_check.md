# New Relic Coverage Check -- AWS Database Services

Run these in Query Builder, in order. Goal: confirm data is landing for
RDS, Aurora, and Redshift, and capture the exact dimension names your
account uses -- these can vary slightly by Metric Stream config version,
so don't assume the names below are exact until you've confirmed them.

---

## 1. What AWS namespaces are landing at all?

```sql
FROM Metric SELECT uniques(metricName) WHERE metricName LIKE 'aws.%' SINCE 1 day ago LIMIT 500
```

Scan the result for `aws.rds.*` and `aws.redshift.*`. If either is
completely absent, stop here and go back to `verify_metric_streams.sh` --
it's an AWS-side filter problem, not a New Relic problem.

---

## 2. Per-service presence + volume

```sql
FROM Metric SELECT uniqueCount(metricName) AS 'distinct RDS metrics'
WHERE metricName LIKE 'aws.rds%' SINCE 1 day ago
```

```sql
FROM Metric SELECT uniqueCount(metricName) AS 'distinct Redshift metrics'
WHERE metricName LIKE 'aws.redshift%' SINCE 1 day ago
```

Both should return non-zero. Zero on either = confirmed gap.

---

## 3. Exact dimension (tag) names per service

This is the important one -- it tells you what to FACET on in the dashboard.

```sql
FROM Metric SELECT keyset() WHERE metricName = 'aws.rds.CPUUtilization' SINCE 1 hour ago
```
Expect something like `aws.rds.dbInstanceIdentifier` for instance-level
metrics. If you have Aurora clusters, also check for a cluster-level key:
```sql
FROM Metric SELECT keyset() WHERE metricName = 'aws.rds.VolumeBytesUsed' SINCE 1 hour ago
```
Aurora cluster metrics typically key on `aws.rds.dbClusterIdentifier`
instead of (or in addition to) the instance identifier.

```sql
FROM Metric SELECT keyset() WHERE metricName = 'aws.redshift.CPUUtilization' SINCE 1 hour ago
```
Expect `aws.redshift.clusterIdentifier`, and for node-level metrics,
`aws.redshift.nodeID` as well.

**Write down the exact field names you get back here.** The dashboard
JSON uses the documented defaults -- if yours differ, find/replace before
importing.

---

## 4. Count distinct instances/clusters reporting per service

Useful both now (sanity check) and later (canary -- if this count drops
unexpectedly, something stopped reporting).

```sql
FROM Metric SELECT uniqueCount(aws.rds.dbInstanceIdentifier)
WHERE metricName = 'aws.rds.CPUUtilization' SINCE 1 day ago
```

```sql
FROM Metric SELECT uniqueCount(aws.rds.dbClusterIdentifier)
WHERE metricName = 'aws.rds.VolumeBytesUsed' SINCE 1 day ago
```

```sql
FROM Metric SELECT uniqueCount(aws.redshift.clusterIdentifier)
WHERE metricName = 'aws.redshift.CPUUtilization' SINCE 1 day ago
```

Compare these counts against what you know exists in the AWS console
(RDS instance list, Redshift cluster list). Mismatches point to either a
partial stream filter or an instance/cluster that just spun up and hasn't
reported yet.

---

## 5. Ongoing canary query (optional, but recommended)

Save this as a dashboard widget or a scheduled alert condition so a
future silent stream-filter change gets caught automatically instead of
being discovered when the customer asks why a database disappeared:

```sql
FROM Metric SELECT
  uniqueCount(aws.rds.dbInstanceIdentifier) AS 'RDS instances reporting',
  uniqueCount(aws.rds.dbClusterIdentifier) AS 'Aurora clusters reporting',
  uniqueCount(aws.redshift.clusterIdentifier) AS 'Redshift clusters reporting'
SINCE 1 hour ago
```

A NRQL alert condition on any of these three dropping to zero (or below
an expected baseline) will catch a stream misconfiguration same-day
instead of weeks later.

---

## What "good" looks like before you move to the dashboard

- [ ] `aws.rds%` metrics present, non-zero count
- [ ] `aws.redshift%` metrics present, non-zero count
- [ ] Exact dimension names confirmed for RDS instance-level
- [ ] Exact dimension names confirmed for Aurora cluster-level
- [ ] Exact dimension names confirmed for Redshift
- [ ] Instance/cluster counts match what's actually in AWS
