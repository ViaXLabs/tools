"""security.public-s3-buckets

Cross-references bucket ACLs, bucket policies, and account/bucket-level
Public Access Block settings to determine which buckets are ACTUALLY
publicly accessible -- a judgment call the raw API doesn't make for you.
"""
from __future__ import annotations
from awsx.registry import register
from awsx.aws import client


def _is_block_fully_on(cfg: dict) -> bool:
    return all(cfg.get(k, False) for k in (
        "BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets"
    ))


@register(
    name="public-s3-buckets",
    group="security",
    summary="Find S3 buckets that are actually publicly accessible (ACL + policy + block-settings aware)",
)
def run(session, region, dry_run, **kwargs):
    s3 = client(session, "s3", region)
    buckets = s3.list_buckets()["Buckets"]

    findings = []
    for b in buckets:
        name = b["Name"]
        reasons = []
        try:
            pab = s3.get_public_access_block(Bucket=name)["PublicAccessBlockConfiguration"]
        except s3.exceptions.ClientError:
            pab = {}
        if _is_block_fully_on(pab):
            continue  # fully blocked, skip regardless of ACL/policy

        try:
            acl = s3.get_bucket_acl(Bucket=name)
            for grant in acl.get("Grants", []):
                grantee = grant.get("Grantee", {})
                uri = grantee.get("URI", "")
                if "AllUsers" in uri or "AuthenticatedUsers" in uri:
                    reasons.append(f"ACL grants {grant.get('Permission')} to {uri.split('/')[-1]}")
        except Exception:  # noqa: BLE001
            pass

        try:
            status = s3.get_bucket_policy_status(Bucket=name)
            if status["PolicyStatus"]["IsPublic"]:
                reasons.append("Bucket policy marked public by AWS policy-status check")
        except Exception:  # noqa: BLE001
            pass

        if reasons:
            findings.append({"Bucket": name, "reasons": reasons, "public_access_block": pab})

    return {"flagged_count": len(findings), "buckets": findings}
