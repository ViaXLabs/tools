"""
Auto-discovery: every .py file in this folder is imported on startup so its
@register()-decorated function adds itself to the registry.

To add a new recipe: drop a new file in this folder. Nothing else to touch.
"""
from __future__ import annotations
import importlib
import pkgutil

for _, module_name, _ in pkgutil.iter_modules(__path__):
    importlib.import_module(f"{__name__}.{module_name}")
