from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class Filters:
    include_guids: List[str]
    include_name_contains: List[str]
    include_domains: List[str]
    include_entityTypes: List[str]

    exclude_guids: List[str]
    exclude_name_contains: List[str]
    exclude_domains: List[str]
    exclude_entityTypes: List[str]


def _lower_list(xs: Any) -> List[str]:
    if not xs or not isinstance(xs, list):
        return []
    return [str(x).strip().lower() for x in xs if str(x).strip()]


def load_filters(path: Optional[str]) -> Optional[Filters]:
    if not path:
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    inc = data.get("include") or {}
    exc = data.get("exclude") or {}

    return Filters(
        include_guids=_lower_list(inc.get("guids")),
        include_name_contains=_lower_list(inc.get("name_contains")),
        include_domains=_lower_list(inc.get("domains")),
        include_entityTypes=_lower_list(inc.get("entityTypes")),
        exclude_guids=_lower_list(exc.get("guids")),
        exclude_name_contains=_lower_list(exc.get("name_contains")),
        exclude_domains=_lower_list(exc.get("domains")),
        exclude_entityTypes=_lower_list(exc.get("entityTypes")),
    )


def _contains_any(haystack: str, needles: List[str]) -> bool:
    hs = (haystack or "").lower()
    return any(n in hs for n in needles)


def entity_matches_filters(entity: Dict[str, Any], flt: Optional[Filters]) -> bool:
    """
    True = process entity, False = skip.

    Excludes always win.
    Includes apply only when non-empty.
    Includes are AND across dimensions.
    """
    if flt is None:
        return True

    guid = str(entity.get("guid") or "").lower()
    name = str(entity.get("name") or "")
    domain = str(entity.get("domain") or "").lower()
    etype = str(entity.get("entityType") or entity.get("type") or "").lower()

    # Excludes
    if guid and guid in flt.exclude_guids:
        return False
    if flt.exclude_name_contains and _contains_any(name, flt.exclude_name_contains):
        return False
    if domain and domain in flt.exclude_domains:
        return False
    if etype and etype in flt.exclude_entityTypes:
        return False

    # Includes
    if flt.include_guids and guid not in flt.include_guids:
        return False
    if flt.include_name_contains and not _contains_any(name, flt.include_name_contains):
        return False
    if flt.include_domains and domain not in flt.include_domains:
        return False
    if flt.include_entityTypes and etype not in flt.include_entityTypes:
        return False

    return True
