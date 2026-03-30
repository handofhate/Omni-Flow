"""
Manages the tab-sync sidecar process and reads its output file.
The sidecar (server.py) is a persistent process that owns the HTTP server;
this module just spawns it if needed and reads tabs_cache.json on each query.
"""

import json
import os
import subprocess
import sys
from typing import Optional
from urllib.parse import urlparse, urlunparse


def _plugin_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _tabs_file() -> str:
    return os.path.join(_plugin_dir(), "tabs_cache.json")

def _pid_file() -> str:
    return os.path.join(_plugin_dir(), "server.pid")

def _server_script() -> str:
    return os.path.join(_plugin_dir(), "plugin", "server.py")


def _normalize(url: str) -> str:
    try:
        p = urlparse(url)
        path = p.path.rstrip("/") or "/"
        return urlunparse((p.scheme.lower(), p.netloc.lower(), path, "", p.query, ""))
    except Exception:
        return url.rstrip("/").lower()


def _sidecar_running() -> bool:
    pid_file = _pid_file()
    if not os.path.exists(pid_file):
        return False
    try:
        with open(pid_file) as f:
            pid = int(f.read().strip())
        # os.kill(pid, 0) checks existence without sending a signal
        os.kill(pid, 0)
        return True
    except (OSError, ValueError, SystemError):
        return False


def start(port: int = 7323) -> None:
    """Ensure the sidecar server is running. Safe to call on every plugin init."""
    if _sidecar_running():
        return
    script = _server_script()
    if not os.path.exists(script):
        return
    subprocess.Popen(
        [sys.executable, script, str(port)],
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )


def tab_count() -> int:
    return len(_read_tabs())


def _read_tabs() -> list[dict]:
    try:
        with open(_tabs_file(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def get_open_tabs() -> list[dict]:
    return _read_tabs()


def request_activation(tab_id: str, port: int = 7323) -> bool:
    """Tell the extension to focus a specific tab. Returns True if the request was sent."""
    import json as _json
    import urllib.request
    try:
        body = _json.dumps({"tabId": tab_id}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/activate",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=1)
        return True
    except Exception:
        return False


def find_tab(url: str) -> Optional[dict]:
    needle = _normalize(url)
    for tab in _read_tabs():
        if _normalize(tab.get("url", "")) == needle:
            return tab
    return None
