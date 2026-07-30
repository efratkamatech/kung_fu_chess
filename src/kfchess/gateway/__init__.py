"""The WS Gateway: sockets in, subjects out, and no knowledge of chess.

Nothing under this package may import ``engine``, ``model``, ``rules`` or ``server`` —
a gateway that knows the rules is one edit away from applying them, and the whole point
of the split is that the shard is the only thing that decides anything. A test in
``tests/unit/test_gateway_boundary.py`` enforces it.
"""
