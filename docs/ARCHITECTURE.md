# Architecture and boundaries

This is an independently packaged companion, NOT a patched distribution of deploymenttheory/windows-mcp-server.

## Read-only semantic observer

Windows app (explicit PID) -> external Munim accessibility tree -> read-only MunimClient -> SemanticBridge / PassiveObserver -> bounded snapshots and deltas -> MCP stdio server.

WindowsEventWatcher provides change hints and reconciliation; process_identity checks process creation identity against PID reuse. Observation may expose private UI text. There are no desktop action tools in the included MCP server.

## Semantic planner

semantic_actions.py, semantic_hierarchy.py, lab_action_gate.py, and mcp_label_mapper.py select targets, enforce expected revisions/roles/states, and reject ambiguous controls. A separate, authorized Windows MCP executor must independently verify current state before any desktop action. This repository does not itself guarantee focus-free interactions in every Windows application.

## Browser Lane, two alternatives

Isolated headless Chrome: browser_cli.py -> cdp_lane.py -> temporary isolated profile / localhost Chrome DevTools -> explicitly owned target IDs.

Optional Chrome extension: queue_cli.py -> bounded local command spool -> native_host.py -> MV3 extension -> extension-owned tab IDs. This needs local installation and native host registration.

The README demo shows the actual isolated Chrome browser window and native Chrome tab strip, recorded from a local test fixture. The recorder temporarily foregrounds the dedicated Chrome window for video capture, whereas normal CDP Browser Lane actions do not synthesize mouse or keyboard input.

## Claims and compatibility

Windows MCP Server and Munim already implement accessibility-oriented computer control. The contribution here is a separable observer/planner flow, explicit stale-target rejection, and a browser lane limited to its own tabs. It is experimental, not a secure sandbox against malicious processes running as the same Windows user.

For verification see [Installation](INSTALLATION.md).
