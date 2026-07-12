import pytest

from kfchess.movement.primitives import SlideMovement
from kfchess.movement.rules import MovementRuleSet, standard_movement_rules


def test_register_get_and_contains():
    rules = MovementRuleSet()
    movement = SlideMovement(((0, 1),))
    rules.register("X", movement)
    assert rules.get("X") is movement
    assert "X" in rules
    assert "Y" not in rules


def test_duplicate_registration_rejected():
    rules = MovementRuleSet()
    rules.register("X", SlideMovement(((0, 1),)))
    with pytest.raises(ValueError):
        rules.register("X", SlideMovement(((0, 1),)))


def test_standard_set_has_all_six_pieces():
    rules = standard_movement_rules()
    for letter in "KRBQNP":
        assert letter in rules
    assert "Z" not in rules  # an unregistered letter
