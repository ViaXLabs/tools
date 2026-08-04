"""
Audit logging for shared bastion/jumpbox usage.

Every recipe invocation gets one JSON line appended to a local log, so
that on a box where many people log in with their own permissions, there
is a record of who (OS user + AWS identity) ran what (recipe + params),
under which region, and whether it was dry-run or --execute.

This is best-effort and must never break the actual command: any failure
here (log dir not writable, STS unreachable, etc.) is swallowed after one
stderr warning.
"""
from __future__ import annotations
import datetime
import getpass
import json
import os
import socket
import sys

from awsx.aws import get_caller_identity

_WARNED = False


def _log_path() -> str:
    override = os.environ.get("AWSX_AUDIT_LOG")
    if override:
        return override

    system_path = "/var/log/awsx/audit.log"
    system_dir = os.path.dirname(system_path)
    try:
        os.makedirs(system_dir, exist_ok=True)
        if os.access(system_dir, os.W_OK):
            return system_path
    except OSError:
        pass

    home_dir = os.path.join(os.path.expanduser("~"), ".awsx")
    os.makedirs(home_dir, exist_ok=True)
    return os.path.join(home_dir, "audit.log")


def log_invocation(session, recipe_key: str, region: str | None, dry_run: bool, params: dict) -> None:
    global _WARNED
    try:
        identity = get_caller_identity(session)
        entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "os_user": getpass.getuser(),
            "sudo_user": os.environ.get("SUDO_USER"),
            "hostname": socket.gethostname(),
            "aws_account": identity.get("Account"),
            "aws_arn": identity.get("Arn"),
            "recipe": recipe_key,
            "region": region,
            "dry_run": dry_run,
            "params": {k: v for k, v in params.items() if v is not None},
        }
        path = _log_path()
        with open(path, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except Exception as e:  # noqa: BLE001 - audit logging must never break a command
        if not _WARNED:
            print(f"[awsx] warning: audit logging failed ({e}); continuing without it", file=sys.stderr)
            _WARNED = True
