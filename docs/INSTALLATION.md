# Installation and verification

Windows Semantic Bridge is an experimental Python companion for Windows AI agents. It is NOT a replacement for Windows MCP Server. Nothing installs as a Windows service.

## Prerequisites and clean installation

Windows 11, Git, Python 3.12+ with Windows launcher, and optionally Chrome for Browser Lane.

~~~powershell
git clone https://github.com/DannyGi82/windows-semantic-bridge.git
cd windows-semantic-bridge
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q tests browser_lane/tests
~~~

Without a compiled Native Messaging proxy, two optional tests may be skipped.

## Isolated Chrome (no extension required)

~~~powershell
.\.venv\Scripts\python.exe browser_lane\browser_cli.py start
.\.venv\Scripts\python.exe browser_lane\browser_cli.py new https://example.org
.\.venv\Scripts\python.exe browser_lane\browser_cli.py list
.\.venv\Scripts\python.exe browser_lane\browser_cli.py shutdown
~~~

Uses a separate browser user-data directory and a localhost-only Chrome debugging port. It does not attach to existing Chrome tabs.

## Reproduce the real-window GIF

~~~powershell
.\.venv\Scripts\python.exe scripts\record_browser_demo.py
~~~

The recorder creates a disposable Chrome profile, opens a local fixture at 127.0.0.1 and temporarily displays its own Chrome window to record real tabs and the address bar. It restores the previous foreground app. It refuses to save any frame when an unexpected window is focused.

## Read-only desktop observer (optional)

Download and verify a compatible Windows executable of Munim Computer Use from https://github.com/munimtechnologies/munim-computer-use/releases . It is a separately installed third-party dependency not distributed here.

~~~powershell
$env:SEMANTIC_BRIDGE_MUNIM_EXE = "C:\absolute\path\to\munim-computer-use.exe"
.\.venv\Scripts\python.exe server.py
~~~

This process is an MCP stdio server. Register the executable and its arguments in your trusted MCP client; it starts passive and exposes read-only observation. Actual Windows actions must be carried out by an independently authorized executor.

## Advanced: optional Chrome MV3 Native Messaging host

The extension source is under browser_lane/extension. NativeMessaging requires a locally built proxy and manual installation; it is not enabled by the Python installation.

Compile the proxy on Windows using the .NET Framework C# compiler:

~~~powershell
$csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path $csc)) { throw "C# compiler not found" }
& $csc /nologo /target:exe "/out:$PWD\browser_lane\native_host_proxy.exe" "browser_lane\native_host_proxy.cs"
if ($LASTEXITCODE -ne 0) { throw "Proxy build failed" }
~~~

Create adjacent file browser_lane/native_host_paths.txt with exactly two absolute paths: first the virtual environment Python executable, second browser_lane/native_host.py. This machine-specific file is ignored by Git.

In Chrome visit chrome://extensions, enable Developer mode, select Load unpacked and choose browser_lane/extension. Note the extension ID.

Create a private Native Messaging manifest, outside the repository, with the following JSON. Replace BOTH placeholders:

~~~json
{
  "name": "com.semanticbridge.browserlane",
  "description": "Windows Semantic Bridge native host",
  "path": "C:\\absolute\\path\\to\\browser_lane\\native_host_proxy.exe",
  "type": "stdio",
  "allowed_origins": ["chrome-extension://YOUR_INSTALLED_EXTENSION_ID/"]
}
~~~

Set the unnamed default REG_SZ value at

    HKEY_CURRENT_USER\Software\Google\Chrome\NativeMessagingHosts\com.semanticbridge.browserlane

to the absolute manifest file path. Do not alter other Native Messaging hosts, machine-wide registry keys, or Chrome profiles.

Restart the extension, then check:

~~~powershell
.\.venv\Scripts\python.exe browser_lane\queue_cli.py status
~~~

To uninstall, remove this exact extension and registry key, then delete the locally built proxy, paths file, and manifest. This extension path is experimental: headless Browser Lane is the simpler reproducible mode.

## Troubleshooting

- Missing Python module: use this checkout's virtual environment, then reinstall requirements.
- Chrome unavailable: observer functions do not require Chrome; browser modes do.
- BROWSER_LANE_NOT_STARTED: start the isolated browser CLI first.
- MV3 not connected: compare the installed extension ID, host manifest, registry path, and two local proxy paths.
- Blank remote-session screenshot: not evidence of a successful capture; inspect the reported error instead.
- Never include tokens, passwords, personal screenshots or Chrome profiles in an issue.

Related: [Architecture](ARCHITECTURE.md), [Security](../SECURITY.md), [Contributing](../CONTRIBUTING.md).
