import pytest

from kfchess.model.piece_type import (
    PieceType,
    PieceTypeRegistry,
    standard_piece_types,
)


def test_register_get_and_contains():
    registry = PieceTypeRegistry()
    king = PieceType("K", "king")
    registry.register(king)
    assert registry.get("K") is king
    assert "K" in registry
    assert "Q" not in registry


def test_duplicate_registration_rejected():
    registry = PieceTypeRegistry()
    registry.register(PieceType("K", "king"))
    with pytest.raises(ValueError):
        registry.register(PieceType("K", "impostor"))


def test_get_unknown_letter_raises():
    registry = PieceTypeRegistry()
    with pytest.raises(KeyError):
        registry.get("Z")


def test_standard_set_has_the_six_pieces():
    registry = standard_piece_types()
    for letter in "KQRBNP":
        assert letter in registry
    assert registry.get("N").name == "knight"
