"""Observability: the numbers this design was built on, measured instead of assumed.

Every capacity claim in ``Server_Design_EN.md`` rests on three guesses — fifty
microseconds to resolve a tick, five hundred games to a shard, two and a half kilobits a
second to a player. They were arrived at honestly and none of them has ever been checked.
This package is what checks them.

It deliberately depends on nothing. A metrics client library would be a reasonable
choice in a larger project; here it would be a dependency added to the server so that a
handful of counters could be added up, when the whole exposition format is four kinds of
line and the registry is a dictionary.
"""
