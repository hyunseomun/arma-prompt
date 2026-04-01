"""
Exception-safe module constant override via context manager.

Replaces the manual try/finally monkeypatch pattern with a composable,
typo-catching context manager. If an override key doesn't exist as an
attribute on the target module, raises ValueError immediately — no more
silent no-ops from typos like "l3_compressiom_prompt".
"""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Any


class PromptContext:
    """Override module-level constants for the duration of a block.

    Usage::

        with PromptContext(l3_module, {"COMPRESSION_PROMPT": new_prompt}):
            result = content_compression(...)
        # originals restored here, even if content_compression raised

    Catches typos::

        with PromptContext(l3_module, {"COMPRESSIOM_PROMPT": new_prompt}):
            # ^ raises ValueError: Unknown attribute 'COMPRESSIOM_PROMPT' on module ...
    """

    def __init__(
        self,
        module: ModuleType | str,
        overrides: dict[str, Any],
    ):
        if isinstance(module, str):
            module = importlib.import_module(module)
        self.module = module
        self.overrides = overrides
        self._originals: dict[str, Any] = {}

    def __enter__(self) -> "PromptContext":
        for key, value in self.overrides.items():
            if not hasattr(self.module, key):
                available = [
                    a for a in dir(self.module)
                    if not a.startswith("_") and a.isupper()
                ]
                raise ValueError(
                    f"Unknown attribute '{key}' on module {self.module.__name__}. "
                    f"Available constants: {available}"
                )
            self._originals[key] = getattr(self.module, key)
            setattr(self.module, key, value)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        for key, original in self._originals.items():
            setattr(self.module, key, original)
        self._originals.clear()

    @property
    def originals(self) -> dict[str, Any]:
        """Read-only access to saved originals (useful for logging)."""
        return dict(self._originals)
