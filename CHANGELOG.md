# v0.1.0 — Developer preview

Independent public snapshot of Windows Semantic Bridge.

- Accessibility observer, semantic snapshots and deltas
- Fail-closed action planning; desktop actuation remains external and separately authorized
- Isolated Chrome CDP profile and optional MV3 tab-group source
- Local named-pipe observer, minimal TCP exposure
- Unit/integration tests; Chrome live tests require a local Windows environment

Caveats: optional dependencies and native host installation are not automated; no Windows MCP fork code, production settings or machine credentials are bundled. The Chrome MV3 extension is not automatically installed and may need environment-specific adjustments.
