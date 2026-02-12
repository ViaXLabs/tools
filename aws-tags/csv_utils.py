import csv
import json
from typing import Any, Dict, Iterable, List


def _compact(obj: Any) -> str:
    """Compact JSON for a CSV cell."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def write_check_report_csv(out_path: str, entries: List[Dict[str, Any]]) -> None:
    """
    Writes checker report to CSV so you can review before applying.

    Key columns:
      - missing_keys: required tags missing
      - invalid_keys: required tags present but invalid (we generally do NOT change these)
      - proposed_add: what we would ADD (usually missing tags)
      - proposed_replace: only populated if you ran checker with --propose-replacements
      - present_required_values: shows what required tags are already set to
    """
    fieldnames = [
        "guid",
        "name",
        "domain",
        "entityType",
        "action_needed",
        "missing_keys",
        "invalid_keys",
        "present_required_keys",
        "present_required_values",
        "proposed_add",
        "proposed_replace",
    ]

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()

        for e in entries:
            present_required = e.get("present_required") or {}
            present_keys = [k for k, v in present_required.items() if v.get("present")]
            present_vals = {k: present_required[k].get("values") for k in present_keys}

            invalid = e.get("invalid") or []
            invalid_keys = [x.get("key") for x in invalid if isinstance(x, dict)]

            row = {
                "guid": e.get("guid", ""),
                "name": e.get("name", ""),
                "domain": e.get("domain", ""),
                "entityType": e.get("entityType", ""),
                "action_needed": bool(e.get("action_needed")),
                "missing_keys": ";".join(e.get("missing") or []),
                "invalid_keys": ";".join([k for k in invalid_keys if k]),
                "present_required_keys": ";".join(sorted(present_keys)),
                "present_required_values": _compact(present_vals),
                "proposed_add": _compact((e.get("proposed") or {}).get("add") or {}),
                "proposed_replace": _compact((e.get("proposed") or {}).get("replace") or {}),
            }
            w.writerow(row)


def write_apply_log_csv(out_path: str, rows: Iterable[Dict[str, Any]]) -> None:
    """
    Apply log CSV.

    In dry-run:
      result=DRY_RUN

    In real run:
      result=OK or ERROR
    """
    fieldnames = ["timestamp", "guid", "name", "action", "key", "values", "result", "error"]

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})
