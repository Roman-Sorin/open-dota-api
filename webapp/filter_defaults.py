from __future__ import annotations


DEFAULT_PATCH_BASE = "7.41"


def _patch_base(name: str) -> str:
    parts: list[str] = []
    for ch in name:
        if ch.isdigit() or ch == ".":
            parts.append(ch)
            continue
        break
    return "".join(parts) or name


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


def expand_selected_patch_names(
    selected_patches: list[str],
    patch_timeline: list[tuple[int, str]],
) -> list[str]:
    if not selected_patches or not patch_timeline:
        return selected_patches

    latest_base = _patch_base(patch_timeline[-1][1])
    family_members_by_base: dict[str, list[str]] = {}
    seen_names: set[str] = set()
    for _, patch_name in reversed(patch_timeline):
        if patch_name in seen_names:
            continue
        seen_names.add(patch_name)
        family_members_by_base.setdefault(_patch_base(patch_name), []).append(patch_name)

    expanded: list[str] = []
    for patch_name in selected_patches:
        patch_base = _patch_base(patch_name)
        if patch_name == patch_base and patch_base != latest_base and patch_base in family_members_by_base:
            for family_name in family_members_by_base[patch_base]:
                if family_name not in expanded:
                    expanded.append(family_name)
            continue
        if patch_name not in expanded:
            expanded.append(patch_name)
    return expanded
