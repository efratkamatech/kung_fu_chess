import pytest

from kfchess.model.color import Color


def test_prefix_of_each_color():
    assert Color.WHITE.prefix == "w"
    assert Color.BLACK.prefix == "b"


def test_from_prefix_resolves_both():
    assert Color.from_prefix("w") is Color.WHITE
    assert Color.from_prefix("b") is Color.BLACK


def test_from_prefix_rejects_unknown():
    with pytest.raises(ValueError):
        Color.from_prefix("x")
