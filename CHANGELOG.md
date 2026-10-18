# Changelog

## v0.1.0 — Windows developer preview

First independent public release.

### Included
- Read-only Windows accessibility observation with process identity checks, reconciliation, bounded snapshots and semantic deltas
- Fail-closed semantic action planning; actual desktop actuation remains external and separately authorized
- Isolated Chrome DevTools browser lane restricted to agent-created tab IDs
- Optional Chrome MV3 extension / native messaging host source for agent-owned tab groups
- Real Chrome window GIF recorded from a disposable local fixture
- Clean-clone setup, architecture guide, contributor guidelines and structured issue templates
- Native Messaging test proxy compilation and browser end-to-end tests in Windows CI

### Limits
- Windows-first developer preview; standalone observer exposes no desktop action MCP tools
- External Munim is a separate dependency for desktop observations
- MV3 Native Messaging requires explicit local installation and configuration
- GIF capture temporarily foregrounds its own isolated Chrome browser window
- No guarantee of security against hostile processes running as the same Windows user

Read docs/INSTALLATION.md and docs/ARCHITECTURE.md before deployment.
