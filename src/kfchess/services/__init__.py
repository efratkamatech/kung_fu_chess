"""Services: the state that outlives any one process, and the things that own it.

A shard owns its games and nothing else. Everything that has to be true across *all* the
shards — which room ids are taken, who is waiting for a game, where a given player is
sitting — cannot live in one process's memory as soon as there is a second process, which
would keep its own contradictory copy. The small classes here are what own that state.

Each one is handed a store rather than opening one, exactly as the gateway and the shard
are handed a message bus. That is what lets the same code run both ways: one process
keeps this state in a dictionary and needs no Redis at all, and many processes keep it in
a Redis they all agree on. **The services cannot tell which**, and neither can the game —
the rules, the pairing, and the room ids are the same either way. Redis is a deployment
detail, never a condition for playing.
"""
