"""Graphics layer: the real-time OpenCV view built on top of the game core.

Everything visual lives here — image handling (``img``), sprite/animation loading,
the renderer, mouse input, the event observers (moves log, score), and the frame
loop. It depends on the core (``model``, ``engine``, ``control``) but the core does
not depend on it, so the text/stdin-stdout path is unaffected.
"""
