# AGENTS.md

Instructions for Codex and other coding agents working in this repository.

## Read first

1. `RULES.md`
2. `README.md`
3. `CODEX_TASK.md` for the active implementation task.

## Working style

- Prefer the smallest correct implementation.
- Keep architecture single-process and understandable.
- Do not add infrastructure unless an acceptance criterion requires it.
- Use official Telegram Bot API behavior as source of truth.
- Keep network calls outside SQLite write transactions.
- Make callbacks/admin commands fast; long work belongs in background tasks.
- Add focused tests for reliability boundaries, not speculative abstraction.
- Never log secrets or full Bot Tokens.

## Git discipline

- Work on a dedicated branch/PR unless the environment already provides one.
- Keep commits coherent.
- Do not merge, deploy, restart a real server, or contact a live production bot unless explicitly instructed.
- Do not weaken tests to obtain green status.

## Definition of done

Implementation is done only when the acceptance checks in `CODEX_TASK.md` pass and the final report lists commands run, test results, and any remaining limitations.