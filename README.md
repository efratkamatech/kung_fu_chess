# Kung Fu Chess

[![CI](https://github.com/efratkamatech/kung_fu_chess/actions/workflows/ci.yml/badge.svg)](https://github.com/efratkamatech/kung_fu_chess/actions/workflows/ci.yml)

Real-time (no-turn) chess variant in Python: pieces move independently with a
per-piece cooldown; capturing the enemy king ends the game. Single server
process, in-memory state.

**Repository:** https://github.com/efratkamatech/kung_fu_chess.git

This iteration series builds the **text / stdin→stdout core** one file at a time,
following a layered architecture (Model → Movement → RuleEngine → GameEngine →
RealTimeArbiter → Controller → Text I/O). The program reads commands from
standard input and writes board output to standard output; output is exact
(no prompts, no debug text).

The full backend design is documented in [docs/architecture.md](docs/architecture.md).

## Layout

```
src/kfchess/     # source, organized by layer
tests/           # unit tests (mirror src) + integration fixtures
```

## Setup

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate      POSIX:  source .venv/bin/activate
pip install -e ".[dev]"
```

## Run

```bash
python -m kfchess.main < path/to/fixture.in
```

## Test

```bash
pytest                                   # run the suite
pytest --cov=kfchess --cov-report=html   # coverage + HTML report in htmlcov/
```
