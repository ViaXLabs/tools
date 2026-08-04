"""
Session helpers: multi-account (assume-role) and multi-region fan-out.

Kept separate from recipes so any recipe can reuse the same cross-account /
cross-region plumbing without re-implementing it.
"""
from __future__ import annotations
import boto3
from botocore.config import Config
from concurrent.futures import ThreadPoolExecutor, as_completed

_BOTO_CONFIG = Config(retries={"max_attempts": 10, "mode": "adaptive"})


def base_session(profile: str | None = None) -> boto3.Session:
    """Build a session from the ambient credential chain.

    Deliberately does NOT default to any particular profile or role. If
    --profile isn't passed, boto3's normal resolution order applies:
    env vars -> ~/.aws/credentials -> SSO -> EC2/ECS instance role -> etc.
    This is what makes "each user's own permissions flow through" work on
    a shared bastion: whatever identity the person is already logged in
    as (their assumed role, their SSO session, their instance profile) is
    exactly what awsx uses. awsx never carries its own credentials.
    """
    return boto3.Session(profile_name=profile)


def get_caller_identity(session: boto3.Session) -> dict:
    """Resolve who awsx is actually running as right now.

    Used by `awsx whoami` and by the audit log, so it's always clear
    whose permissions a given command actually ran under.
    """
    sts = session.client("sts", config=_BOTO_CONFIG)
    try:
        ident = sts.get_caller_identity()
        return {
            "Account": ident.get("Account"),
            "Arn": ident.get("Arn"),
            "UserId": ident.get("UserId"),
        }
    except Exception as e:  # noqa: BLE001 - identity resolution must never crash a command
        return {"error": f"could not resolve caller identity: {e}"}


def assumed_session(base: boto3.Session, role_arn: str, session_name: str = "awsx") -> boto3.Session:
    """Return a new boto3 Session using credentials from an assumed role."""
    sts = base.client("sts", config=_BOTO_CONFIG)
    creds = sts.assume_role(RoleArn=role_arn, RoleSessionName=session_name)["Credentials"]
    return boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
    )


def client(session: boto3.Session, service: str, region: str | None = None):
    return session.client(service, region_name=region, config=_BOTO_CONFIG)


def all_regions(session: boto3.Session, service_check: str = "ec2") -> list[str]:
    """List enabled regions for the account."""
    ec2 = client(session, "ec2")
    resp = ec2.describe_regions(AllRegions=False)
    return sorted(r["RegionName"] for r in resp["Regions"])


def fan_out_regions(session: boto3.Session, regions: list[str], fn, max_workers: int = 8) -> dict:
    """Run fn(session, region) across many regions concurrently.

    fn should return a JSON-serializable result for that region.
    Returns {region: result_or_error}.
    """
    results: dict = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(fn, session, r): r for r in regions}
        for fut in as_completed(futures):
            region = futures[fut]
            try:
                results[region] = fut.result()
            except Exception as e:  # noqa: BLE001 - surface all errors per-region
                results[region] = {"error": str(e)}
    return results


def fan_out_accounts(base_session_obj: boto3.Session, role_arns: dict[str, str], fn, max_workers: int = 8) -> dict:
    """Run fn(session) across many accounts concurrently via assume-role.

    role_arns: {account_label: role_arn}
    Returns {account_label: result_or_error}.
    """
    results: dict = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {}
        for label, arn in role_arns.items():
            sess = assumed_session(base_session_obj, arn, session_name=f"awsx-{label}")
            futures[pool.submit(fn, sess)] = label
        for fut in as_completed(futures):
            label = futures[fut]
            try:
                results[label] = fut.result()
            except Exception as e:  # noqa: BLE001
                results[label] = {"error": str(e)}
    return results
