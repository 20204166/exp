# OpenCode Loader
- Current repo instructions are in `../AGENTS.md`.
- OpenCode-specific config lives in `../opencode.json` and `./agents/` if you need to change agent behavior.
- BugGuard fallback: when registered `bugguard-opposer-*` or `bugguard-agent5` agents are unavailable, use separate independent general-agent sessions for the exact reviewer roles; each fallback must write only its owned section directly into the opposition artifact, and the main auditor must not simulate or backfill reviewer evidence.
