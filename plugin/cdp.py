"""
Chrome DevTools Protocol tab detection and switching.
Requires the target browser to be launched with --remote-debugging-port=<port>.
"""

import json
import urllib.request
import urllib.error
from typing import Optional


def get_open_tabs(port: int = 9222) -> list[dict]:
    """Fetch the list of open tabs from the CDP /json endpoint."""
    try:
        url = f"http://127.0.0.1:{port}/json/list"
        with urllib.request.urlopen(url, timeout=0.5) as resp:
            data = json.loads(resp.read())
            # Filter to page targets only (exclude devtools, workers, etc.)
            return [t for t in data if t.get("type") == "page"]
    except Exception:
        return []


def find_tab(url: str, port: int = 9222) -> Optional[dict]:
    """Return the CDP tab object whose URL matches exactly, or None."""
    for tab in get_open_tabs(port):
        if tab.get("url") == url:
            return tab
    return None


def activate_tab(tab_id: str, port: int = 9222) -> bool:
    """
    Send Target.activateTarget via CDP WebSocket to bring a tab to focus.
    Returns True on success.
    """
    import json
    try:
        # Use the simpler /json/activate/<id> HTTP endpoint — no WebSocket needed
        url = f"http://127.0.0.1:{port}/json/activate/{tab_id}"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            return resp.status == 200
    except Exception:
        return False


def is_available(port: int = 9222) -> bool:
    """Return True if a CDP endpoint is reachable on the given port."""
    return bool(get_open_tabs(port))
