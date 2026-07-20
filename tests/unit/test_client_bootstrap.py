"""Test that the thin client wires together into a runnable app."""

from kfchess.client.app import ThinClientApp
from kfchess.client.bootstrap import build_thin_client_app
from kfchess.client.net_client import NetClient


def test_build_thin_client_app_returns_a_wired_app():
    app = build_thin_client_app(NetClient(), white_name="Efrat", black_name="Dan")
    assert isinstance(app, ThinClientApp)
