from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any


CellStyleFunction = Callable[[Any], str]


def apply_cell_style(styler: Any, style_fn: CellStyleFunction, subset: Sequence[str]) -> Any:
    """Apply a per-cell style using the pandas Styler API available at runtime."""

    if hasattr(styler, "map"):
        return styler.map(style_fn, subset=subset)
    if hasattr(styler, "applymap"):
        return styler.applymap(style_fn, subset=subset)
    raise AttributeError("Styler does not support map or applymap.")
