from __future__ import annotations


DEFAULT_PATCH_BASE = "7.41"


def default_patch_selection(
    patch_options: list[str],
    *,
    preferred_base: str = DEFAULT_PATCH_BASE,
) -> list[str]:
    selected = [
        name
        for name in patch_options
        if name == preferred_base or (name.startswith(preferred_base) and len(name) > len(preferred_base))
    ]
    if selected:
        return selected
    return patch_options[:1]
