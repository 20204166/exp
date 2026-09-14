# OpenCode Loader
- Current repo instructions are in `../AGENTS.md`.
- OpenCode-specific config lives in `../opencode.json` and `./agents/` if you need to change agent behavior.
- BugGuard reviewer routing: use separate independent BugGuard fallback sessions for every required reviewer role, including Agent 5, rather than having the main OpenCode agent perform or simulate those roles. If registered `bugguard-opposer-*` or `bugguard-agent5` agents are unavailable, use separate independent general-agent sessions for the exact roles; each reviewer/fallback writes only its owned section directly into the opposition artifact, and the main auditor must not simulate or backfill reviewer evidence.
