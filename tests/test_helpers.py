from utils.helpers import calculate_kda_ratio


def test_calculate_kda_normal() -> None:
    assert calculate_kda_ratio(10, 5, 15) == 5.0


def test_calculate_kda_zero_deaths() -> None:
    assert calculate_kda_ratio(12, 0, 8) == 20.0
