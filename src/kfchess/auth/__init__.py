"""Auth: the one part of logging in that is expensive, on a thread that owns no games.

Checking a password costs 36.5 ms of CPU here — PBKDF2 at a hundred thousand rounds,
chosen deliberately because a cheap password check is not a password check. Until this
package existed that cost was paid on the thread running the games, which measured out at
about twelve admissions a second per shard and did not improve by having fewer games.

Nothing here holds state between requests, which is what makes the fix work: any replica
can answer any login, so the admission rate is a number you raise by starting another
container.
"""
