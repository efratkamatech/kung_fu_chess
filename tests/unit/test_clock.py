import pytest

from kfchess.engine.clock import Clock


def test_starts_at_zero():
    assert Clock().now_ms == 0


def test_advance_accumulates():
    clock = Clock()
    clock.advance(1000)
    clock.advance(500)
    assert clock.now_ms == 1500


def test_negative_advance_rejected():
    with pytest.raises(ValueError):
        Clock().advance(-1)
