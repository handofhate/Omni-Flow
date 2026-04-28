# Omni Flow

Omni Flow turns Flow Launcher into a browser-style URL bar.

Default trigger keyword: `GO`

## What it does

- Searches browser history with relevance ranking
- Lets you open direct URLs immediately
- Optionally switches to already-open tabs (Extension mode)

## Usage

```text
GO face
GO github.com
GO reddit.com/r/flowlauncher
```

## Tab switching modes

| Mode | Behavior |
|---|---|
| None | History + URL opening only |
| Extension | Adds open-tab detection and tab switching |

## Important behavior and security notes

When Extension mode is enabled, Omni Flow will:

- Spawn a separate persistent Python sidecar process (`server.py`)
- Listen only on `127.0.0.1` (default port `7323`) for tab updates
- Set `Access-Control-Allow-Origin: *` on that local server
- Remain local-only (not remotely accessible)

If Extension mode is disabled (`None`), the sidecar is not started.

## Extension mode setup (Chrome recommended)

1. Open `chrome://extensions`
2. Enable Developer mode
3. Click Load unpacked and select this plugin's `extension` folder
4. In Omni Flow settings, set Tab Switching Mode to `Extension`

Chrome is the officially documented setup for Extension mode.
It should also work on Chromium-based browsers like Edge, Brave, Opera, Vivaldi, and Arc, but those are best-effort and may vary by browser version.

## Browser support

History search: Chrome, Edge, Brave, Opera, Vivaldi, Arc, Firefox

Tab switching (Extension mode): Chrome (official), should also work on Chromium-based browsers (Edge, Brave, Opera, Vivaldi, Arc)

## Installation

Use Plugin Store, or install manually:

```text
pm install https://github.com/handofhate/Omni-Flow/releases/latest/download/Omni.Flow-1.0.3.zip
```
