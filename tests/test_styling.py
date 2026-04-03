from webapp.styling import apply_cell_style


class _MapStyler:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, tuple[str, ...]]] = []

    def map(self, style_fn, subset):
        self.calls.append(("map", style_fn, tuple(subset)))
        return self


class _ApplymapStyler:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, tuple[str, ...]]] = []

    def applymap(self, style_fn, subset):
        self.calls.append(("applymap", style_fn, tuple(subset)))
        return self


def test_apply_cell_style_prefers_map_when_available() -> None:
    styler = _MapStyler()

    result = apply_cell_style(styler, lambda _: "color: red;", subset=["WR"])

    assert result is styler
    assert styler.calls == [("map", styler.calls[0][1], ("WR",))]


def test_apply_cell_style_falls_back_to_applymap() -> None:
    styler = _ApplymapStyler()

    result = apply_cell_style(styler, lambda _: "color: red;", subset=["WR"])

    assert result is styler
    assert styler.calls == [("applymap", styler.calls[0][1], ("WR",))]
