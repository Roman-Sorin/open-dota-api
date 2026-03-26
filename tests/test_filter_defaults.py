from webapp.filter_defaults import default_patch_selection


def test_default_patch_selection_prefers_741_family() -> None:
    patch_options = ["7.42", "7.41c", "7.41b", "7.41", "7.40"]

    assert default_patch_selection(patch_options) == ["7.41c", "7.41b", "7.41"]


def test_default_patch_selection_falls_back_to_first_option_when_741_missing() -> None:
    patch_options = ["7.42", "7.40c", "7.40"]

    assert default_patch_selection(patch_options) == ["7.42"]
