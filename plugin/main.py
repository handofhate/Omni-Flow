import os
import subprocess
import webbrowser
from typing import Dict, List, Optional, Set

from flox import Flox, ICON_BROWSER

from plugin.browsers import HistoryItem, get_browser
from plugin import tab_server


ICON_HISTORY = "icon.png"
ICON_OPEN_TAB = "icon_tab.png"
ICON_OMNI = "omni.png"


def _looks_like_url(query: str) -> Optional[str]:
    """Return normalized URL if query looks like a URL, else None."""
    q = query.strip()
    if not q or " " in q:
        return None
    if q.startswith(("http://", "https://")):
        return q
    if "." in q and not q.startswith(".") and not q.endswith("."):
        return "https://" + q
    return None


class BrowserOmnibox(Flox):
    # Keep this list narrow and predictable for tab switching behavior.
    _EXTENSION_TAB_BROWSERS = {"Chrome", "Edge", "Brave", "Opera", "Vivaldi", "Arc"}

    def __init__(self):
        super().__init__()

    def _setting(self, key: str, default: str = "") -> str:
        return self.settings.get(key, default)

    def _tab_mode(self) -> str:
        return self._setting("tab_mode", "None")

    def _extension_port(self) -> int:
        try:
            return int(self._setting("extension_port", "7323"))
        except ValueError:
            return 7323

    def _max_results(self) -> int:
        try:
            return int(self._setting("max_results", "20"))
        except ValueError:
            return 20

    def _browser_name(self) -> str:
        return self._setting("browser", "Chrome")

    def _tab_mode_effective(self) -> str:
        mode = self._tab_mode()
        browser = self._browser_name()

        if mode == "CDP":
            return "_deprecated_cdp"

        if mode == "Extension" and browser not in self._EXTENSION_TAB_BROWSERS:
            return "_incompatible"

        return mode

    def _open_url(self, url: str) -> None:
        browser_name = self._browser_name()
        browser_paths = {
            "Chrome": r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe",
            "Edge": r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe",
            "Brave": r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe",
            "Opera": r"%LOCALAPPDATA%\Programs\Opera\opera.exe",
            "Vivaldi": r"%LOCALAPPDATA%\Vivaldi\Application\vivaldi.exe",
            "Arc": r"%LOCALAPPDATA%\Arc\app\Arc.exe",
            "Firefox": r"%PROGRAMFILES%\Mozilla Firefox\firefox.exe",
        }

        path = os.path.expandvars(browser_paths.get(browser_name, ""))
        if path and os.path.exists(path):
            subprocess.Popen([path, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            webbrowser.open(url)

    def query(self, query_text: str):
        query_text = query_text.strip()
        if not query_text:
            return

        effective_mode = self._tab_mode_effective()

        if effective_mode == "_deprecated_cdp":
            self.add_item(
                title="CDP mode is disabled",
                subtitle="CDP was removed for stability. Use Extension mode or None mode.",
                icon=ICON_HISTORY,
            )
            effective_mode = "None"

        if effective_mode == "_incompatible":
            self.add_item(
                title="Tab switching unavailable for selected browser",
                subtitle="Extension tab switching is only supported on Chromium-based browsers.",
                icon=ICON_HISTORY,
            )
            effective_mode = "None"

        if effective_mode == "Extension":
            tab_server.start(port=self._extension_port())
            if tab_server.tab_count() == 0:
                self.add_item(
                    title="Extension mode: no tabs received yet",
                    subtitle="Load the companion extension and keep Flow Launcher open.",
                    icon=ICON_HISTORY,
                )

        browser = get_browser(self._browser_name())
        if browser is None:
            self.add_item(
                title="Unsupported browser",
                subtitle="Check plugin settings for a supported browser.",
                icon=ICON_HISTORY,
            )
            return

        max_results = self._max_results()
        q = query_text.lower()

        open_tab_results: List[dict] = []
        seen_tab_urls: Set[str] = set()

        if effective_mode == "Extension":
            for tab in tab_server.get_open_tabs():
                url = tab.get("url", "")
                title = tab.get("title", "")
                if q in url.lower() or q in title.lower():
                    open_tab_results.append(tab)
                    seen_tab_urls.add(tab_server._normalize(url))

        raw_items = browser.get_history(query_text, limit=500)
        seen_history: Dict[str, HistoryItem] = {}

        for item in raw_items:
            if tab_server._normalize(item.url) in seen_tab_urls:
                continue
            existing = seen_history.get(item.url)
            if existing is None or item.visit_count > existing.visit_count:
                seen_history[item.url] = item

        history_items = list(seen_history.values())
        history_items.sort(
            key=lambda i: (
                i.match_rank(query_text),
                i.path_depth,
                -i.frecency_score(),
                i.clean_url_length,
            )
        )

        if not open_tab_results and not history_items:
            url = _looks_like_url(query_text)
            if url:
                self.add_item(
                    title="Open {0}".format(url),
                    subtitle="Open URL in browser",
                    icon=ICON_OMNI,
                    method=self.open_result,
                    parameters=[url, ""],
                    score=1,
                )
            else:
                self.add_item(
                    title="No results found",
                    subtitle="No history or open tabs match '{0}'".format(query_text),
                    icon=ICON_OMNI,
                )
            return

        open_tab_results.sort(key=lambda t: len(t.get("url", "")))
        for i, tab in enumerate(open_tab_results[:max_results]):
            tab_id = str(tab.get("id", ""))
            url = tab.get("url", "")
            title = tab.get("title") or url
            self.add_item(
                title=title,
                subtitle=url,
                icon=ICON_OPEN_TAB,
                method=self.open_result,
                parameters=[url, tab_id],
                context=[url, tab_id, title],
                score=10000 - i,
            )

        remaining = max_results - len(open_tab_results)
        for i, item in enumerate(history_items[:remaining]):
            self.add_item(
                title=item.title or item.url,
                subtitle=item.url,
                icon=ICON_HISTORY,
                method=self.open_result,
                parameters=[item.url, ""],
                context=[item.url, "", item.title or item.url],
                score=5000 - i,
            )

        url = _looks_like_url(query_text)
        if url:
            self.add_item(
                title="Open {0}".format(url),
                subtitle="Open URL in browser",
                icon=ICON_OMNI,
                method=self.open_result,
                parameters=[url, ""],
                score=1,
            )

    def open_result(self, url: str, tab_id: str):
        if tab_id and self._tab_mode_effective() == "Extension":
            if tab_server.request_activation(tab_id, port=self._extension_port()):
                self._focus_browser()
                return
        self._open_url(url)

    def _focus_browser(self):
        proc_map = {
            "Chrome": "chrome",
            "Edge": "msedge",
            "Brave": "brave",
            "Opera": "opera",
            "Vivaldi": "vivaldi",
            "Arc": "arc",
        }
        proc = proc_map.get(self._browser_name(), "chrome")
        ps = (
            "$p=Get-Process {0} -EA SilentlyContinue|?{{$_.MainWindowHandle -ne 0}}|select -first 1;"
            "if($p){{(New-Object -COM WScript.Shell).AppActivate($p.Id)}}"
        ).format(proc)
        subprocess.Popen(
            ["powershell", "-WindowStyle", "Hidden", "-Command", ps],
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def context_menu(self, data):
        url = data[0] if len(data) > 0 else ""
        tab_id = data[1] if len(data) > 1 else ""

        if tab_id and self._tab_mode_effective() == "Extension":
            self.add_item(
                title="Switch to open tab",
                subtitle=url,
                icon=ICON_OPEN_TAB,
                method=self.open_result,
                parameters=[url, tab_id],
            )

        self.add_item(
            title="Open in browser",
            subtitle=url,
            icon=ICON_BROWSER,
            method=self.open_result,
            parameters=[url, ""],
        )

        self.add_item(
            title="Copy URL",
            subtitle=url,
            icon=ICON_BROWSER,
            method=self.copy_to_clipboard,
            parameters=[url],
        )

    def copy_to_clipboard(self, text: str):
        subprocess.run(["clip"], input=text.encode(), check=True)


if __name__ == "__main__":
    BrowserOmnibox()
