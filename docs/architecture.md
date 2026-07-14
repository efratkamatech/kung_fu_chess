# Kung Fu Chess — Backend Architecture (Final, Design Only)

Python, real-time (no-turn) chess variant: pieces move independently with a
per-piece cooldown; king capture ends the game. Single server process,
in-memory state (v1). Design goals: multi-user, low-latency, reliable
(reconnect), and easy to extend (new pieces, roles, even user-authored rules)
without rewriting the core.

## Layers (dependencies point downward only)

| Layer | Owns | Must not own |
|---|---|---|
| Model | Board (encapsulated internal storage — swappable to binary later), positions, pieces, piece states (idle/moving/resting/jumping/captured), PieceType/Role/ActionType registries | Pixels, clicks, rendering, movement rules, timing, network identity |
| Movement rules | Movement geometry per piece type, built from composable primitives (slide-until-blocked, jump-to-offset, move-N-in-direction, on-reach-rank-effect) so new pieces/effects are registered, not coded | Game commands, timing, animation, rendering, input |
| RuleEngine | Read-only legality validation for a requested move/action | Board mutation, animation, click interpretation, game-over state |
| GameEngine | Game-over guard, validation delegation, starting legal motions, wait delegation, snapshots | Piece-specific logic, rendering, input parsing, network/identity concerns |
| RealTimeArbiter | Active motions, simulated time, arrival resolution, mid-path meetings (later entrant eats an enemy and continues, or is blocked one cell short by a friend; ties to the earlier start), captures, promotion effect, jump-vs-attacker timing race, king-capture reporting | Chess legality, clicks, rendering |
| Session Actor | One command queue/task per game — single-writer into GameEngine/RealTimeArbiter; drives the cooldown/tick scheduler; timestamps events on arrival | Chess legality, rendering, wire format, persistence format |
| Role & Access | Identity → role (player/spectator/referee/...) → permission, via Role registry | Board mutation, movement legality, rendering |
| Session/Match Manager | Create/destroy Session Actors, matchmaking, role assignment, reconnection-token mapping | Movement rules, rendering, wire protocol details |
| Transport/Protocol | Transport-agnostic messages (MoveRequest/MoveAccepted/MoveRejected/StateSync/Heartbeat/Reconnect) + reliability (idempotent move ids, acks, heartbeats) | Game rules, board mutation, rendering |
| ScoreKeeper | Per-player running score, subscribed to capture/promotion events, using a piece-value registry (pawn 1, knight/bishop 3, rook 5, queen 9, king ∞) | Game rules, board mutation |
| MoveHistory | Per-color move log in algebraic notation, server-timestamped, subscribed to move events | Game rules, rendering |
| Controller | Click interpretation, selected-cell state — one command source among several feeding Session Actor | Chess legality, board mutation, rendering |
| Renderer | Draws from read-only GameSnapshot (same snapshot Transport serializes remotely) | Game rules, board mutation, input parsing |
| Text I/O | BoardParser/BoardPrinter | Movement rules, command execution, rendering |
| TextTestRunner | Script-driven integration tests over the public command path | Movement rules, direct board mutation |

## Confirmed feature additions
- **Promotion** (in scope): pluggable "on-reach-special-square" effect on a
  piece's rule definition, default = promote to queen (parameterizable).
- **Score system**: ScoreKeeper as above.
- **Move history**: MoveHistory as above.
- **Jump-in-place**: second `ActionType` (shorter cooldown; if attacker
  arrives exactly as jump completes, jumper captures attacker instead of the
  reverse).
- **Extended piece states**: idle/moving/resting/jumping/captured.

## Future-proofing constraints (not implemented now, must stay possible)
- **Binary board representation**: only Board may know its internal storage
  layout; every other layer uses Board's public interface only.
- **User-defined custom games**: movement = composable primitives; RuleSet
  is data (pieces + primitives + win conditions + arrival effects), not
  Python-only, so new pieces/rules are additive configuration.

## Cross-cutting principles (apply now, every layer, from day one)
- **Code quality**: DRY, SRP, no hardcoded constants/strings in business
  logic (use config/registries), strict encapsulation between classes.
- **Testing**: dependency injection everywhere (no monkeypatching), target
  100% unit coverage per layer with HTML reports, git repo URL comment in
  main entry file.

## Open (decide later)
- Wire format (JSON vs binary), Session Actor concurrency primitive
  (asyncio vs other), snapshot/event-log frequency, multi-process scaling.
- **Unify the collision passes**: the RealTimeArbiter resolves collisions in a
  mid-path pass (moving-vs-moving on a shared cell or a head-on swap, plus
  moving-vs-*settled* along a mover's path, using a per-cell settle time) and an
  arrival pass (landing, promotion, and capturing a settled piece on a destination).
  The mid-path settled check has one granularity limitation: if a piece settles onto
  a mover's path and the mover then passes it **within the same `resolve` call**, the
  settle is recorded only after that call's mid-path pass, so it is missed until the
  next `resolve`. In the real command path `resolve` runs once per `wait`, so this
  only bites a single coarse wait that spans both events. Closing it fully (or the
  cleaner single time-window model) is deferred as its own refactor.
