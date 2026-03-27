# Omni Flow

A faux omnibox for [Flow Launcher](https://www.flowlauncher.com/) — turns your search bar into an intelligent browser address bar with frecency-ranked history, open tab detection, and direct URL opening.

## Features

- **Frecency-ranked history** — results are scored by visit frequency and recency, not just alphabetical order
- **Smart result ordering** — root URLs always surface before deep paths, hostname prefix matches beat mid-string matches
- **Open tab detection** — already-open tabs are highlighted at the top of results so you switch instead of opening a duplicate
- **Direct URL opening** — type any URL and hit enter even if it's not in your history
- **Multi-browser support** — Chrome, Edge, Brave, Opera, Vivaldi, Arc (history), Firefox (history only)

## Usage

Type `of` followed by any part of a URL or page title.

```
of face        → facebook.com (and any open Facebook tabs)
of github.com  → your GitHub history sorted by frecency
of             → opens any URL you type directly
```

## Tab Switching Modes

By default the plugin searches history only. To enable open tab detection and one-keystroke tab switching, choose a mode in plugin settings:

| Mode | Setup | Browser support |
|---|---|---|
| **None** | Nothing | All browsers (history only) |
| **Extension** | Install the companion Chrome extension | Chrome, Edge, Brave, Opera, Vivaldi, Arc |
| **CDP** | Run `setup_cdp.ps1` once to patch your Chrome shortcut | Chrome, Edge, Brave, Opera, Vivaldi, Arc |

### Extension Mode (recommended)

1. Open Chrome and go to `chrome://extensions`
2. Enable **Developer mode** (top-right toggle)
3. Click **Load unpacked** and select the `extension` folder inside the plugin directory:
   ```
   %APPDATA%\FlowLauncher\Plugins\Omni Flow-1.0.0\extension
   ```
4. Set **Tab Switching Mode** to `Extension` in plugin settings

### CDP Mode

1. Open PowerShell and run:
   ```powershell
   & "$env:APPDATA\FlowLauncher\Plugins\Omni Flow-1.0.0\setup_cdp.ps1"
   ```
2. Fully close and reopen Chrome
3. Set **Tab Switching Mode** to `CDP` in plugin settings

> CDP opens a local-only debugging port on your machine. Nothing is exposed to the internet.

## Settings

| Setting | Default | Description |
|---|---|---|
| Browser | Chrome | Browser to pull history from |
| Tab Switching Mode | None | None / Extension / CDP |
| Max Results | 20 | Number of results to show |
| Extension Port | 7323 | Port for the extension sync server |
| CDP Port | 9222 | Port for Chrome remote debugging |

## Installation

Install via the Flow Launcher plugin store, or manually:

```
pm install https://github.com/handofhate/Omni-Flow/releases/latest/download/Omni.Flow-1.0.0.zip
```
