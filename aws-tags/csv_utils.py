import csv
import json
from typing import Any, Dict, Iterable, List, Set


def _compact(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _merge_values_unique(existing: List[str], incoming: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for v in (existing or []):
        if v not in seen:
            out.append(v)
            seen.add(v)
    for v in (incoming or []):
        if v not in seen:
            out.append(v)
            seen.add(v)
    return out


def compute_would_be_tags(entry: Dict[str, Any]) -> Dict[str, List[str]]:
    current = entry.get("all_current_tags") or {}
    if not isinstance(current, dict):
        current = {}

    proposed = entry.get("proposed") or {}
    add_map = proposed.get("add") or {}
    rep_map = proposed.get("replace") or {}

    out: Dict[str, List[str]] = {}
    for k, vals in current.items():
        if isinstance(vals, list):
            out[str(k)] = [str(x) for x in vals]
        else:
            out[str(k)] = [str(vals)]

    for k, vals in rep_map.items():
        if not isinstance(vals, list):
            vals = [vals]
        out[str(k)] = [str(x) for x in vals]

    for k, vals in add_map.items():
        if not isinstance(vals, list):
            vals = [vals]
        key = str(k)
        out[key] = _merge_values_unique(out.get(key, []), [str(x) for x in vals])

    return out


def _values_to_cell(vals: List[str]) -> str:
    if not vals:
        return ""
    return "|".join(str(v) for v in vals)


def _collect_required_tag_keys_from_policy(policy: Dict[str, Any]) -> List[str]:
    req = policy.get("required") or {}
    if not isinstance(req, dict):
        return []
    keys = [str(k) for k in req.keys()]
    return sorted(keys, key=lambda s: s.lower())


def _collect_all_tag_keys_from_entries(entries: List[Dict[str, Any]]) -> List[str]:
    keys: Set[str] = set()
    for e in entries:
        would = compute_would_be_tags(e)
        keys.update(would.keys())
    return sorted(keys, key=lambda s: s.lower())


def _collect_all_keys_required_first(entries: List[Dict[str, Any]], policy: Dict[str, Any]) -> List[str]:
    """
    Friendly order for WIDE ALL:
      - required keys first (policy order, normalized to alpha but still first)
      - then all other keys alphabetically
    """
    required_keys = _collect_required_tag_keys_from_policy(policy)
    all_keys = _collect_all_tag_keys_from_entries(entries)

    required_lower = {k.lower() for k in required_keys}

    others = [k for k in all_keys if k.lower() not in required_lower]
    # keep required first, then others
    return required_keys + others


def write_check_report_csv(out_path: str, entries: List[Dict[str, Any]]) -> None:
    fieldnames = [
        "guid",
        "name",
        "domain",
        "entityType",
        "action_needed",
        "all_current_tags",
        "would_be_tags",
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
            present_keys = [k for k, v in present_required.items() if isinstance(v, dict) and v.get("present")]
            present_vals = {k: present_required[k].get("values") for k in present_keys}

            invalid = e.get("invalid") or []
            invalid_keys = [x.get("key") for x in invalid if isinstance(x, dict)]

            would_be = compute_would_be_tags(e)

            row = {
                "guid": e.get("guid", ""),
                "name": e.get("name", ""),
                "domain": e.get("domain", ""),
                "entityType": e.get("entityType", ""),
                "action_needed": bool(e.get("action_needed")),
                "all_current_tags": _compact(e.get("all_current_tags") or {}),
                "would_be_tags": _compact(would_be),
                "missing_keys": ";".join(e.get("missing") or []),
                "invalid_keys": ";".join([k for k in invalid_keys if k]),
                "present_required_keys": ";".join(sorted(present_keys)),
                "present_required_values": _compact(present_vals),
                "proposed_add": _compact((e.get("proposed") or {}).get("add") or {}),
                "proposed_replace": _compact((e.get("proposed") or {}).get("replace") or {}),
            }
            w.writerow(row)


def write_check_report_csv_wide_required(out_path: str, entries: List[Dict[str, Any]], policy: Dict[str, Any]) -> None:
    required_keys = _collect_required_tag_keys_from_policy(policy)

    base_fields = [
        "guid",
        "name",
        "domain",
        "entityType",
        "action_needed",
        "missing_keys",
        "invalid_keys",
        "proposed_add",
        "proposed_replace",
    ]
    fieldnames = base_fields + required_keys

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()

        for e in entries:
            invalid = e.get("invalid") or []
            invalid_keys = [x.get("key") for x in invalid if isinstance(x, dict)]
            would_be = compute_would_be_tags(e)

            row = {
                "guid": e.get("guid", ""),
                "name": e.get("name", ""),
                "domain": e.get("domain", ""),
                "entityType": e.get("entityType", ""),
                "action_needed": bool(e.get("action_needed")),
                "missing_keys": ";".join(e.get("missing") or []),
                "invalid_keys": ";".join([k for k in invalid_keys if k]),
                "proposed_add": _compact((e.get("proposed") or {}).get("add") or {}),
                "proposed_replace": _compact((e.get("proposed") or {}).get("replace") or {}),
            }

            for k in required_keys:
                row[k] = _values_to_cell(would_be.get(k, []))

            w.writerow(row)


def write_check_report_csv_wide_all(out_path: str, entries: List[Dict[str, Any]], policy: Dict[str, Any]) -> None:
    """
    WIDE ALL with friendly ordering:
      required tags first, then everything else.
    """
    tag_keys = _collect_all_keys_required_first(entries, policy)

    base_fields = [
        "guid",
        "name",
        "domain",
        "entityType",
        "action_needed",
        "missing_keys",
        "invalid_keys",
        "proposed_add",
        "proposed_replace",
    ]
    fieldnames = base_fields + tag_keys

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()

        for e in entries:
            invalid = e.get("invalid") or []
            invalid_keys = [x.get("key") for x in invalid if isinstance(x, dict)]
            would_be = compute_would_be_tags(e)

            row = {
                "guid": e.get("guid", ""),
                "name": e.get("name", ""),
                "domain": e.get("domain", ""),
                "entityType": e.get("entityType", ""),
                "action_needed": bool(e.get("action_needed")),
                "missing_keys": ";".join(e.get("missing") or []),
                "invalid_keys": ";".join([k for k in invalid_keys if k]),
                "proposed_add": _compact((e.get("proposed") or {}).get("add") or {}),
                "proposed_replace": _compact((e.get("proposed") or {}).get("replace") or {}),
            }

            for k in tag_keys:
                row[k] = _values_to_cell(would_be.get(k, []))

            w.writerow(row)


def write_apply_log_csv(out_path: str, rows: Iterable[Dict[str, Any]]) -> None:
    fieldnames = ["timestamp", "guid", "name", "action", "key", "values", "result", "error"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})
