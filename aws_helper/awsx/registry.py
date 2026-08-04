"""
Recipe registry.

A "recipe" is one intricate, multi-step AWS operation. Each recipe lives in
its own file under awsx/recipes/ and registers itself with @register().

This is the ONLY thing new recipes need to know about. It's what keeps the
tool flexible as AWS changes: you never touch cli.py or core code, you just
add a new file and it's auto-discovered.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Any

_REGISTRY: dict[str, "Recipe"] = {}


@dataclass
class Recipe:
    name: str                 # CLI-facing name, e.g. "cleanup.orphaned-snapshots"
    group: str                # top-level group: cleanup | security | cost | crossaccount
    summary: str              # one-line help text
    func: Callable[..., Any]  # the recipe's run function
    params: list = field(default_factory=list)  # click.Option objects, optional
    mutating: bool = False    # True if this recipe can ever call a mutating AWS API
                              # (delete/tag/modify/etc). Read-only mode refuses these
                              # regardless of --execute. Query-only recipes (describe/
                              # list/get calls only) should leave this False.


def register(name: str, group: str, summary: str, params: list | None = None, mutating: bool = False):
    """Decorator to register a new recipe.

    Set mutating=True if the recipe can ever call a create/delete/modify/tag
    API - this is what the --readonly / awsx-ro locked-down edition uses to
    decide what to hide. Leave it False (default) for pure describe/list/get
    query recipes.

    Example:
        @register(
            name="orphaned-snapshots",
            group="cleanup",
            summary="Find EBS snapshots with no parent volume",
            mutating=True,  # this recipe can delete snapshots with --execute
        )
        def run(session, region, dry_run, **kwargs):
            ...
            return {"findings": [...]}
    """
    def decorator(func):
        key = f"{group}.{name}"
        if key in _REGISTRY:
            raise ValueError(f"Recipe '{key}' already registered")
        _REGISTRY[key] = Recipe(
            name=name, group=group, summary=summary, func=func,
            params=params or [], mutating=mutating,
        )
        return func
    return decorator


def all_recipes() -> dict[str, Recipe]:
    return dict(_REGISTRY)


def get(group: str, name: str) -> Recipe | None:
    return _REGISTRY.get(f"{group}.{name}")


def groups() -> list[str]:
    return sorted({r.group for r in _REGISTRY.values()})
