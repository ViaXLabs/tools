from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def load_policy(path: str) -> Dict[str, Any]:
    import json

    with open(path, "r", encoding="utf-8") as f:
        policy = json.load(f)

    policy.setdefault("protected_keys", [])
    policy.setdefault("required", {})
    policy.setdefault("defaults", {})
    policy.setdefault("derived", {})
    policy.setdefault("suggested", {})

    return policy


def normalize_tags(raw_tags: Any) -> Dict[str, List[str]]:
    if raw_tags is None:
        return {}

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
            out[str(k)] = [str(v).strip() for v in vals if str(v).strip()]
        return out

    if isinstance(raw_tags, dict):
        out: Dict[str, List[str]] = {}
        for k, v in raw_tags.items():
            if isinstance(v, list):
                out[str(k)] = [str(x).strip() for x in v if str(x).strip()]
            else:
                s = str(v).strip()
                out[str(k)] = [s] if s else []
        return out

    return {}


def _parse_required_entry(req_entry: Any) -> Tuple[str, Optional[List[str]], Optional[List[str]]]:
    """
    Returns:
      (mode, allowed, preferred)

    preferred is used for "soft standardization" warnings (like environment).
    """
    if isinstance(req_entry, dict):
        mode = str(req_entry.get("mode", "must_exist"))

        allowed = req_entry.get("allowed")
        allowed_list: Optional[List[str]] = None
        if allowed is not None:
            if not isinstance(allowed, list):
                raise ValueError("allowed must be a list")
            allowed_list = [str(x) for x in allowed]

        preferred = req_entry.get("preferred")
        preferred_list: Optional[List[str]] = None
        if preferred is not None:
            if not isinstance(preferred, list):
                raise ValueError("preferred must be a list")
            preferred_list = [str(x) for x in preferred]

        return mode, allowed_list, preferred_list

    if isinstance(req_entry, str):
        return req_entry, None, None

    return "must_exist", None, None


def _entity_any_tag_text(tags: Dict[str, List[str]]) -> str:
    parts: List[str] = []
    for k, vals in tags.items():
        parts.append(str(k))
        parts.extend([str(v) for v in vals])
    return " ".join(parts)


def _contains_any_case_insensitive(haystack: str, needles: List[str]) -> bool:
    hs = (haystack or "").lower()
    return any((n or "").lower() in hs for n in needles)


def _equals_any_case_insensitive(values: List[str], needles: List[str]) -> bool:
    vset = {str(v).strip().lower() for v in (values or []) if str(v).strip()}
    nset = {str(n).strip().lower() for n in (needles or []) if str(n).strip()}
    return bool(vset.intersection(nset))


def derive_tag_value(key: str, entity: Dict[str, Any], tags: Dict[str, List[str]], policy: Dict[str, Any]) -> Optional[str]:
    """
    Derive missing tag values from policy["derived"] rules.

    Supported rule "source":
      - "entity_name"
      - "any_tag_text"
      - "tag_value"   (rule.tag_key required)

    Supported rule "match":
      - "contains_any"
      - "equals_any"
      - "exists"      (true if tag_key has ANY value; needles ignored)
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

        if not isinstance(value, str) or not value.strip():
            continue

        if source == "entity_name":
            if match == "contains_any":
                if _contains_any_case_insensitive(entity_name, [str(x) for x in needles]):
                    return value

        elif source == "any_tag_text":
            if match == "contains_any":
                if _contains_any_case_insensitive(tag_text, [str(x) for x in needles]):
                    return value

        elif source == "tag_value":
            tag_key = rule.get("tag_key")
            if not isinstance(tag_key, str) or not tag_key.strip():
                continue

            vals = tags.get(tag_key, [])

            if match == "exists":
                if vals:
                    return value

            elif match == "equals_any":
                if _equals_any_case_insensitive(vals, [str(x) for x in needles]):
                    return value

            elif match == "contains_any":
                joined = " ".join(vals)
                if _contains_any_case_insensitive(joined, [str(x) for x in needles]):
                    return value

        else:
            continue

    return None


def _preferred_warning_if_needed(key: str, current_vals: List[str], preferred: Optional[List[str]]) -> Optional[Dict[str, Any]]:
    """
    If tag is present but not in preferred values => warning.
    No changes proposed here.
    """
    if not preferred or not current_vals:
        return None

    preferred_lower = {str(p).strip().lower() for p in preferred if str(p).strip()}
    current_lower = {str(v).strip().lower() for v in current_vals if str(v).strip()}

    if current_lower.intersection(preferred_lower):
        return None

    return {
        "key": key,
        "current": current_vals,
        "preferred": preferred,
        "reason": "value is not in preferred standard set (no changes applied; FYI only)"
    }


def suggest_environment(tags: Dict[str, List[str]], policy: Dict[str, Any]) -> Optional[str]:
    req_env = (policy.get("required") or {}).get("environment") or {}
    preferred = req_env.get("preferred") if isinstance(req_env, dict) else None
    preferred_list = [str(x) for x in preferred] if isinstance(preferred, list) else []

    env_vals = tags.get("environment", [])
    if not env_vals:
        return None

    env_raw = str(env_vals[0]).strip()
    env_l = env_raw.lower()

    for p in preferred_list:
        if env_l == p.lower():
            return p

    env_map = (policy.get("suggested") or {}).get("environment_map") or {}
    if isinstance(env_map, dict):
        for k, v in env_map.items():
            if str(k).strip().lower() == env_l:
                return str(v).strip() or None

    return None


def suggest_team(tags: Dict[str, List[str]], entity: Dict[str, Any], policy: Dict[str, Any]) -> Optional[str]:
    derived_val = derive_tag_value("team", entity, tags, policy)
    if derived_val:
        return derived_val

    team_vals = tags.get("team", [])
    if not team_vals:
        return None

    current = str(team_vals[0]).strip()
    cur_l = current.lower()

    norm_map = (policy.get("suggested") or {}).get("team_normalize") or {}
    if isinstance(norm_map, dict):
        for k, v in norm_map.items():
            if str(k).strip().lower() == cur_l:
                return str(v).strip() or None

    return cur_l if cur_l else None


def suggest_system(tags: Dict[str, List[str]], entity: Dict[str, Any], policy: Dict[str, Any]) -> Optional[str]:
    """
    Report-only suggestion for system.

    Uses derived.system.rules to infer canonical values like:
      Verifications/SAVE
      Verifications/CoreServices

    This does NOT overwrite existing tags; it just shows up in the CSV as suggested_system.
    """
    return derive_tag_value("system", entity, tags, policy)


def evaluate_entity(
    entity: Dict[str, Any],
    policy: Dict[str, Any],
    *,
    propose_replacements: bool = False,
) -> Dict[str, Any]:
    protected = set(policy.get("protected_keys") or [])
    required = policy.get("required") or {}
    defaults = policy.get("defaults") or {}

    tags = normalize_tags(entity.get("tags"))
    all_current_tags = tags.copy()

    present_required: Dict[str, Dict[str, Any]] = {}
    missing: List[str] = []
    invalid: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    proposed_add: Dict[str, List[str]] = {}
    proposed_replace: Dict[str, List[str]] = {}

    # Suggestions (report-only)
    suggested_env = suggest_environment(tags, policy)
    suggested_team_val = suggest_team(tags, entity, policy)
    suggested_system_val = suggest_system(tags, entity, policy)

    suggested: Dict[str, Any] = {
        "environment": suggested_env,
        "team": suggested_team_val,
        "system": suggested_system_val
    }

    for key, req_entry in required.items():
        if key in protected:
            continue

        mode, allowed, preferred = _parse_required_entry(req_entry)
        current_vals = tags.get(key, [])
        present = (key in tags) and len(current_vals) > 0

        present_required[key] = {"present": present, "values": current_vals}

        warn = _preferred_warning_if_needed(key, current_vals, preferred)
        if warn is not None:
            if key == "environment" and suggested_env:
                warn["suggested"] = suggested_env
            warnings.append(warn)

        default_val = defaults.get(key)
        default_list = [str(default_val)] if default_val is not None else None

        # ADD-only behavior: derive only when missing
        derived_val = derive_tag_value(key, entity, tags, policy) if not present else None
        derived_list = [derived_val] if derived_val is not None else None

        if mode == "must_exist":
            if not present:
                missing.append(key)
                if derived_list is not None:
                    proposed_add[key] = derived_list
                elif default_list is not None:
                    proposed_add[key] = default_list

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
                            "reason": "must be exactly one value and it must be in allowed list"
                        }
                    )
                    if propose_replacements and default_list is not None:
                        if allowed is None or default_list[0] in allowed:
                            proposed_replace[key] = default_list

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
                            "reason": "must include at least one allowed value"
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
                    "reason": f"unknown mode '{mode}'"
                }
            )

    action_needed = bool(missing or invalid or warnings or proposed_add or proposed_replace)

    return {
        "guid": entity.get("guid"),
        "name": entity.get("name"),
        "entityType": entity.get("entityType") or entity.get("type"),
        "domain": entity.get("domain"),
        "all_current_tags": all_current_tags,
        "present_required": present_required,
        "missing": missing,
        "invalid": invalid,
        "warnings": warnings,
        "suggested": suggested,
        "proposed": {"add": proposed_add, "replace": proposed_replace},
        "action_needed": action_needed
    }
