# System Analyzer MCP Design

## Goal

Make a separate copy of the MCP server package from `/home/btn17/Downloads/expra-connect/tools/expra_connect_mcp` and adapt only that copy into a local, read-only MCP server for this System Analyzer repository. The original Expra Connect MCP package and its configuration must not be edited. Keep the adapted copy and machine-local configuration Git-ignored rather than adding them to tracked project source.

## Surface and architecture

The MCP server will live in a dedicated `tools/system_analyzer_mcp/` directory. It will preserve applicable generic MCP scaffolding from the source package (stdio transport, structured tool results, bounded output, and focused tests), while replacing all Expra Connect-specific tools and implementation with Analyzer-specific behavior.

Expose read-only tools for:

- A complete dashboard snapshot.
- A single component summary, selected from supported component keys.
- Process candidates for inspection.
- Storage candidates, with an optional explicitly supplied scan root.

Implement these through `algo.Analyzer` and existing serialization/helpers wherever appropriate; do not duplicate scanner logic. Do not expose cleanup, process termination, file movement/deletion, preference mutation, or arbitrary command execution.

## Local setup and ignore behavior

Provide a local MCP config example and setup/run instructions. The active `.mcp.json`, private/local config, and MCP package directory are ignored by Git as requested. Configuration must use paths relative to this checkout or a clearly documented local setup, not absolute paths into `expra-connect` or its virtualenv.

## Safety and failure behavior

All exposed operations are read-only. Validate component keys and scan-root input before invoking Analyzer. Return structured, bounded results and report failures through MCP tool errors without leaking local secrets or unrelated filesystem contents. Do not return environment variables, private files, or arbitrary source paths as part of scan output.

## Verification

Add focused unit tests for tool registration, serialization, invalid component/root inputs, and failures. Follow this repository's test hygiene requirements: run the focused tests and, for Python changes, `ruff check .`, `ruff format --check .`, `pyright`, and `mypy --ignore-missing-imports`; run the repository test script if feasible.

## Scope boundary

This is a local developer integration, not an installed end-user feature. It does not change the Analyzer UI, scanner behavior, or project dependencies; MCP dependencies should remain isolated to the ignored package's own environment.
