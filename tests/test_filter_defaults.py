from webapp.filter_defaults import default_patch_selection, expand_selected_patch_names


def test_default_patch_selection_prefers_741_family() -> None:
    patch_options = ["7.42", "7.41c", "7.41b", "7.41", "7.40"]

    assert default_patch_selection(patch_options) == ["7.41c", "7.41b", "7.41"]


def test_default_patch_selection_falls_back_to_first_option_when_741_missing() -> None:
    patch_options = ["7.42", "7.40c", "7.40"]

    assert default_patch_selection(patch_options) == ["7.42"]


def test_expand_selected_patch_names_expands_completed_patch_family() -> None:
    patch_timeline = [
        (1, "7.40"),
        (2, "7.40a"),
        (3, "7.40b"),
        (4, "7.40c"),
        (5, "7.41"),
        (6, "7.41a"),
    ]

    assert expand_selected_patch_names(["7.40"], patch_timeline) == ["7.40c", "7.40b", "7.40a", "7.40"]


def test_expand_selected_patch_names_keeps_latest_patch_selection_granular() -> None:
    patch_timeline = [
        (1, "7.40"),
        (2, "7.40a"),
        (3, "7.41"),
        (4, "7.41a"),
        (5, "7.41b"),
    ]

    assert expand_selected_patch_names(["7.41"], patch_timeline) == ["7.41"]
    assert expand_selected_patch_names(["7.41b"], patch_timeline) == ["7.41b"]
