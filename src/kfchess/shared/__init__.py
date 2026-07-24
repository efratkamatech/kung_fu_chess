"""Shared vocabulary: the language the client and the server both speak.

These modules belong to neither side alone — they are the wire protocol, the
serialisable game snapshot, and the token/algebraic notations used to build and read
them. Grouping them here makes the shared boundary explicit: the server *produces* this
vocabulary and the client *consumes* it, and nothing here depends on either side's
engine, graphics, or sockets (only on the model).
"""
