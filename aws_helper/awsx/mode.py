"""
Read-only mode gate.

This is a SAFETY RAIL, not a security boundary. It's meant to stop
accidental mutation and to make a "query-only" edition easy to hand out
on a shared bastion. It is enforced entirely client-side, so anyone with
general shell/Python access on the box could bypass it.

For an actual, unbypassable guarantee, restrict this at the IAM layer:
give read-only users a role/policy that simply lacks the mutating
permissions (ec2:DeleteSnapshot, ec2:CreateTags, etc). Use this module to
make that intent obvious and to fail safe/loud in the common case, not as
a substitute for IAM.
"""
from __future__ import annotations
import os

_ENV_VAR = "AWSX_READONLY"
_TRUE_VALUES = {"1", "true", "yes", "on"}


def is_readonly() -> bool:
    return os.environ.get(_ENV_VAR, "").strip().lower() in _TRUE_VALUES


def lock_readonly() -> None:
    """Force read-only mode for the rest of this process.

    Overwrites any value the calling user's shell may have set, so this is
    safe to call unconditionally at the top of a locked-down entrypoint
    like `awsx-ro`.
    """
    os.environ[_ENV_VAR] = "1"
