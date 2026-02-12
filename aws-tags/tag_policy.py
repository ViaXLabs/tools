from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def load_policy(path: str) -> Dict[str, Any]:
    """
    Loads tag policy JSON.

    Maintainability tip:
      Most of what you change will be in tag_policy.json, not in this file.
    """
    import json

    with open(path, "r", encoding="utf-8") as f:
        policy = json.load(f)

    policy.setdefault("protected_keys", [])
    policy.setdefault("required", {})
    policy.setdefault("defaults", {})
    policy.setdefault("derived", {})

    return policy


def normalize_tags(raw_tags: Any) -> Dict[str, List[str]]:
    """
    Convert NerdGraph tags to a consistent dict[str, list[str]] format.
    """
    if raw_tags is None:
        return {}

    if isinstance(raw_tags, dict):
        out: Dict[str, List[str]] = {}
        for k, v in raw_tags.items():
            if v is None:
                out[str(k)] = []
            elif isinstance(v, list):
                out[str(k)] = [str(x).strip() for x in v if str(x).strip()]
            else:
                s = str(v).strip()
                out[str(k)] = [s] if s else []
        return out

    if isinstance(raw_tags, list):
        out: Dict[str, List[str]] = {}
        for t in raw_tags:
            if not isinstance(t, dict):
                continue
            k = t.get("key")
            vals = t.get("values") or []
            if k is None:
                continue
            if not isinstance(vals, list):
                vals = [vals]
            out[str(k)] = [str(x).strip() for x in vals if str(x).strip()]
        return out

    return {}


def _parse_required_entry(req_entry: Any) -> Tuple[str, Optional[List[str]]]:
    """
    Reads one required tag rule from policy.

    Supported modes:
      - must_exist
      - must_equal_one_of
      - must_include_one_of
    """
    if isinstance(req_entry, dict):
        mode = str(req_entry.get("mode", "must_exist"))
        allowed = req_entry.get("allowed")
        if allowed is None:
            return mode, None
        if not isinstance(allowed, list):
            raise ValueError("allowed must be a list")
        return mode, [str(x) for x in allowed]

    if isinstance(req_entry, str):
        return req_entry, None

    return "must_exist", None


def _entity_any_tag_text(tags: Dict[str, List[str]]) -> str:
    """
    Build a searchable blob from tag keys + values.
    Used by derived mapping rules.
    """
    parts: List[str] = []
    for k, vals in tags.items():
        parts.append(str(k))
        parts.extend([str(v) for v in vals])
    return " ".join(parts)


def _contains_any_case_insensitive(haystack: str, needles: List[str]) -> bool:
    hs = (haystack or "").lower()
    return any((n or "").lower() in hs for n in needles)


def derive_tag_value(key: str, entity: Dict[str, Any], tags: Dict[str, List[str]], policy: Dict[str, Any]) -> Optional[str]:
    """
    If a required tag is missing, we may be able to derive it (like team mapping).

    This is intentionally policy-driven so you mostly edit tag_policy.json.
    """
    derived = policy.get("derived") or {}
    spec = derived.get(key)
    if not isinstance(spec, dict):
        return None

    rules = spec.get("rules") or []
    if not isinstance(rules, list):
        return None

    entity_name = str(entity.get("name") or "")
    tag_text = _entity_any_tag_text(tags)

    for rule in rules:
        if not isinstance(rule, dict):
            continue

        source = rule.get("source")
        match = rule.get("match")
        needles = rule.get("needles") or []
        value = rule.get("value")

        if not isinstance(needles, list) or not needles:
            continue
        if not isinstance(value, str) or not value.strip():
            continue

        # Choose what text we search
        if source == "entity_name":
            haystack = entity_name
        elif source == "any_tag_text":
            haystack = tag_text
        else:
            continue

        # Match strategy
        if match == "contains_any":
            if _contains_any_case_insensitive(haystack, [str(x) for x in needles]):
                return value
        else:
            continue

    return None


def evaluate_entity(
    entity: Dict[str, Any],
    policy: Dict[str, Any],
    *,
    propose_replacements: bool = False,
) -> Dict[str, Any]:
    """
    Evaluate entity vs policy.

    Your preference:
      - mostly ADD required tags that are missing
      - do NOT mess with existing tags

    Therefore:
      - missing tags => propose ADD if we can derive or default
      - invalid existing tags => flag invalid, and ONLY propose REPLACE if propose_replacements=True
    """
    protected = set(policy.get("protected_keys") or [])
    required = policy.get("required") or {}
    defaults = policy.get("defaults") or {}

    tags = normalize_tags(entity.get("tags"))

    present_required: Dict[str, Dict[str, Any]] = {}
    missing: List[str] = []
    invalid: List[Dict[str, Any]] = []

    proposed_add: Dict[str, List[str]] = {}
    proposed_replace: Dict[str, List[str]] = {}

    for key, req_entry in required.items():
        if key in protected:
            # hard safety: never touch protected keys
            continue

        mode, allowed = _parse_required_entry(req_entry)
        current_vals = tags.get(key, [])
        present = (key in tags) and len(current_vals) > 0

        # Track required tags that are already present (for reporting)
        present_required[key] = {"present": present, "values": current_vals}

        default_val = defaults.get(key)
        default_list = [str(default_val)] if default_val is not None else None

        derived_val = derive_tag_value(key, entity, tags, policy) if not present else None
        derived_list = [derived_val] if derived_val is not None else None

        # ---------------- must_exist ----------------
        if mode == "must_exist":
            if not present:
                missing.append(key)
                # propose add if we can
                if derived_list is not None:
                    proposed_add[key] = derived_list
                elif default_list is not None:
                    proposed_add[key] = default_list

        # ---------------- must_equal_one_of ----------------
        elif mode == "must_equal_one_of":
            if not present:
                missing.append(key)
                candidate = derived_list or default_list
                if candidate is not None:
                    if allowed is None or candidate[0] in allowed:
                        proposed_add[key] = candidate
            else:
                is_valid = (len(current_vals) == 1) and (allowed is not None) and (current_vals[0] in allowed)
                if not is_valid:
                    invalid.append(
                        {
                            "key": key,
                            "current": current_vals,
                            "allowed": allowed,
                            "mode": mode,
                            "reason": "must be exactly one value and it must be in allowed list",
                        }
                    )
                    if propose_replacements and default_list is not None:
                        if allowed is None or default_list[0] in allowed:
                            proposed_replace[key] = default_list

        # ---------------- must_include_one_of ----------------
        elif mode == "must_include_one_of":
            if not present:
                missing.append(key)
                candidate = derived_list or default_list
                if candidate is not None:
                    if allowed is None or candidate[0] in allowed:
                        proposed_add[key] = candidate
            else:
                if allowed is None:
                    continue
                includes = any(v in allowed for v in current_vals)
                if not includes:
                    invalid.append(
                        {
                            "key": key,
                            "current": current_vals,
                            "allowed": allowed,
                            "mode": mode,
                            "reason": "must include at least one allowed value",
                        }
                    )
                    if propose_replacements and default_list is not None and default_list[0] in allowed:
                        proposed_replace[key] = default_list

        else:
            invalid.append(
                {
                    "key": key,
                    "current": current_vals,
                    "allowed": allowed,
                    "mode": mode,
                    "reason": f"unknown mode '{mode}'",
                }
            )

    action_needed = bool(missing or invalid or proposed_add or proposed_replace)

    return {
        "guid": entity.get("guid"),
        "name": entity.get("name"),
        "entityType": entity.get("entityType") or entity.get("type"),
        "domain": entity.get("domain"),
        "present_required": present_required,
        "missing": missing,
        "invalid": invalid,
        "proposed": {"add": proposed_add, "replace": proposed_replace},
        "action_needed": action_needed,
    }
