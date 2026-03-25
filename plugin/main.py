import os
import subprocess
import webbrowser
from typing import Optional

from flox import Flox, ICON_BROWSER

from plugin.browsers import get_browser, HistoryItem
from plugin import tab_server, cdp


ICON_HISTORY = "icon.png"
ICON_OPEN_TAB = "icon_tab.png"


class BrowserOmnibox(Flox):

    def __init__(self):
        super().__init__()
        # Start the extension tab-sync server once; it lives as a daemon thread
        tab_server.start(port=self._extension_port())

    # ------------------------------------------------------------------
    # Settings helpers
    # ------------------------------------------------------------------

    def _setting(self, key: str, default: str = "") -> str:
        return self.settings.get(key, default)

    def _tab_mode(self) -> str:
        return self._setting("tab_mode", "None")

    def _cdp_port(self) -> int:
        try:
            return int(self._setting("cdp_port", "9222"))
        except ValueError:
            return 9222

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

    # ------------------------------------------------------------------
    # Open-tab detection
    # ------------------------------------------------------------------

    def _find_open_tab(self, url: str) -> Optional[dict]:
        mode = self._tab_mode_effective()
        if mode == "Extension":
            return tab_server.find_tab(url)
        if mode == "CDP":
            return cdp.find_tab(url, port=self._cdp_port())
        return None

    def _open_url(self, url: str) -> None:
        browser_name = self._browser_name()
        browser_paths = {
            "Chrome":  r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe",
            "Edge":    r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe",
            "Brave":   r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe",
            "Opera":   r"%LOCALAPPDATA%\Programs\Opera\opera.exe",
            "Vivaldi": r"%LOCALAPPDATA%\Vivaldi\Application\vivaldi.exe",
            "Arc":     r"%LOCALAPPDATA%\Arc\app\Arc.exe",
            "Firefox": r"%PROGRAMFILES%\Mozilla Firefox\firefox.exe",
        }
        path = os.path.expandvars(browser_paths.get(browser_name, ""))
        if path and os.path.exists(path):
            subprocess.Popen([path, url])
        else:
            webbrowser.open(url)

    # ------------------------------------------------------------------
    # Compatibility check
    # ------------------------------------------------------------------

    # Browsers that support Chromium CDP / extension tab switching
    _CHROMIUM_BROWSERS = {"Chrome", "Edge", "Brave", "Opera", "Vivaldi", "Arc"}

    def _tab_mode_effective(self) -> str:
        """
        Return the active tab mode, downgrading to 'None' with a warning
        if the selected browser can't support the chosen mode.
        """
        mode = self._tab_mode()
        browser = self._browser_name()
        if mode in ("CDP", "Extension") and browser not in self._CHROMIUM_BROWSERS:
            return "_incompatible"
        return mode

    # ------------------------------------------------------------------
    # Flow Launcher entry points
    # ------------------------------------------------------------------

    def query(self, query_text: str):
        query_text = query_text.strip()
        if not query_text:
            return

        # Surface a helpful warning if settings are misconfigured
        effective_mode = self._tab_mode_effective()
        if effective_mode == "Extension":
            count = tab_server.tab_count()
            if count == 0:
                self.add_item(
                    title="⚠  Extension: no tabs received yet",
                    subtitle="Make sure the Browser Omnibox extension is loaded in Chrome and Flow Launcher has been open since Chrome started.",
                    icon=ICON_HISTORY,
                )
        if effective_mode == "_incompatible":
            self.add_item(
                title=f"⚠  Tab switching unavailable for {self._browser_name()}",
                subtitle="CDP and Extension modes only work with Chromium-based browsers. Change Tab Switching Mode to None.",
                icon=ICON_HISTORY,
            )

        browser = get_browser(self._browser_name())
        if browser is None:
            self.add_item(
                title="Unknown browser",
                subtitle=f"'{self._browser_name()}' is not supported. Check plugin settings.",
                icon=ICON_HISTORY,
            )
            return

        max_results = self._max_results()
        q = query_text.lower()

        # --- Step 1: Open tabs matching the query (always shown first) ----------
        open_tab_results = []
        seen_tab_urls: set[str] = set()
        if effective_mode in ("Extension", "CDP"):
            all_tabs = (
                tab_server.get_open_tabs() if effective_mode == "Extension"
                else cdp.get_all_tabs(port=self._cdp_port())
            )
            for tab in all_tabs:
                url = tab.get("url", "")
                title = tab.get("title", "")
                if q in url.lower() or q in title.lower():
                    open_tab_results.append(tab)
                    seen_tab_urls.add(tab_server._normalize(url))

        # --- Step 2: History results, excluding URLs already shown as open tabs -
        raw_items = browser.get_history(query_text, limit=500)
        seen_history: dict[str, HistoryItem] = {}
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
            self.add_item(
                title="No results found",
                subtitle=f"No history or open tabs match '{query_text}'",
                icon=ICON_HISTORY,
            )
            return

        # --- Render open tabs --------------------------------------------------
        # Shortest URL first; score offset ensures Flow Launcher respects the order
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

        # --- Render history ----------------------------------------------------
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

    def open_result(self, url: str, tab_id: str):
        if tab_id:
            mode = self._tab_mode_effective()
            if mode == "CDP":
                if cdp.activate_tab(tab_id, port=self._cdp_port()):
                    self._focus_browser()
                    return
            elif mode == "Extension":
                if tab_server.request_activation(tab_id, port=self._extension_port()):
                    self._focus_browser()
                    return
        self._open_url(url)

    def _focus_browser(self):
        """Bring the browser window to the foreground using WScript.Shell.AppActivate."""
        proc_map = {
            "Chrome": "chrome", "Edge": "msedge", "Brave": "brave",
            "Opera": "opera", "Vivaldi": "vivaldi", "Arc": "arc",
        }
        proc = proc_map.get(self._browser_name(), "chrome")
        ps = (
            f"$p=Get-Process {proc} -EA SilentlyContinue"
            f"|?{{$_.MainWindowHandle -ne 0}}|select -first 1;"
            f"if($p){{(New-Object -COM WScript.Shell).AppActivate($p.Id)}}"
        )
        subprocess.Popen(
            ["powershell", "-WindowStyle", "Hidden", "-Command", ps],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    def context_menu(self, data):
        # data = [url, tab_id, title]
        url = data[0] if len(data) > 0 else ""
        tab_id = data[1] if len(data) > 1 else ""
        title = data[2] if len(data) > 2 else url

        if tab_id:
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
        import subprocess
        subprocess.run(["clip"], input=text.encode(), check=True)


if __name__ == "__main__":
    BrowserOmnibox()
