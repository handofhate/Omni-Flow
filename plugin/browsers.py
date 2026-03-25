import os
import re
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse


CHROMIUM_EPOCH_OFFSET = 11644473600  # seconds between 1601-01-01 and 1970-01-01

# Query-string keys that are pure tracking noise — strip before scoring
_TRACKING_PARAMS = re.compile(
    r'&?(utm_\w+|fbclid|gclid|msclkid|ref|source|mc_\w+|_ga|twclid)=[^&]*',
    re.IGNORECASE,
)


def _clean_url(url: str) -> str:
    """Strip tracking params and fragments for scoring purposes."""
    try:
        p = urlparse(url)
        query = _TRACKING_PARAMS.sub('', p.query).strip('&')
        # Rebuild without fragment; include query only if non-empty after strip
        return p._replace(query=query, fragment='').geturl()
    except Exception:
        return url


@dataclass
class HistoryItem:
    url: str
    title: str
    visit_count: int
    last_visit: datetime
    # populated later by tab detection
    open_tab_id: Optional[str] = field(default=None)

    @property
    def _parsed(self):
        return urlparse(self.url)

    @property
    def hostname(self) -> str:
        """e.g. 'www.facebook.com'"""
        return self._parsed.netloc.lower()

    @property
    def hostname_bare(self) -> str:
        """Hostname without leading 'www.'"""
        h = self.hostname
        return h[4:] if h.startswith("www.") else h

    @property
    def path_depth(self) -> int:
        """Number of non-empty path segments. Root URL = 0."""
        parts = [p for p in self._parsed.path.split("/") if p]
        return len(parts)

    @property
    def is_root(self) -> bool:
        p = self._parsed
        return self.path_depth == 0 and not p.query and not p.fragment

    def frecency_score(self) -> float:
        """
        Visit frequency × recency weight. No depth component — depth is
        handled as a hard sort tier in main.py so it can never be overcome
        by visit count.
        """
        now = datetime.now(timezone.utc)
        age_days = max((now - self.last_visit).total_seconds() / 86400, 0.01)

        if age_days <= 1:
            recency_weight = 100
        elif age_days <= 7:
            recency_weight = 70
        elif age_days <= 30:
            recency_weight = 50
        elif age_days <= 90:
            recency_weight = 30
        else:
            recency_weight = 10

        return self.visit_count * recency_weight

    @property
    def clean_url_length(self) -> int:
        """Length of the URL after stripping tracking params and fragments."""
        return len(_clean_url(self.url))

    def match_rank(self, query: str) -> int:
        """
        0 — query is a prefix of the bare hostname (best)
                 'face'  → facebook.com  ✓
        1 — query matches somewhere else in the URL
                 'face'  → bookface.com  (mid-string)
                 'login' → facebook.com/login
        2 — query only matches the page title (worst)
                 'f'     → gg.deals  with title 'Free Games - GG.deals'
        """
        q = query.lower()
        # Strip scheme and www. so 'face' matches 'facebook.com' not 'https://www.f...'
        host = self.hostname_bare
        if host.startswith(q):
            return 0
        if q in self.url.lower():
            return 1
        return 2


# ---------------------------------------------------------------------------
# Browser base class
# ---------------------------------------------------------------------------

class BrowserBase:
    name: str = ""
    history_path: str = ""  # may contain glob-style {profile} placeholder

    def get_db_path(self) -> Optional[str]:
        path = os.path.expandvars(self.history_path)
        if os.path.exists(path):
            return path
        return None

    def _copy_db(self, db_path: str) -> str:
        """Copy the locked SQLite file to a temp location before reading."""
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".sqlite")
        tmp.close()
        shutil.copy2(db_path, tmp.name)
        return tmp.name

    def get_history(self, query: str, limit: int = 500) -> list[HistoryItem]:
        raise NotImplementedError


class ChromiumBrowser(BrowserBase):
    """Shared implementation for all Chromium-based browsers."""

    def get_history(self, query: str, limit: int = 500) -> list[HistoryItem]:
        db_path = self.get_db_path()
        if not db_path:
            return []

        tmp_path = self._copy_db(db_path)
        items: list[HistoryItem] = []

        try:
            conn = sqlite3.connect(tmp_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            like = f"%{query}%"
            cur.execute(
                """
                SELECT url, title, visit_count, last_visit_time
                FROM urls
                WHERE (url LIKE ? OR title LIKE ?)
                  AND hidden = 0
                ORDER BY last_visit_time DESC
                LIMIT ?
                """,
                (like, like, limit),
            )

            for row in cur.fetchall():
                # Chromium stores time as microseconds since 1601-01-01
                raw_ts = row["last_visit_time"]
                unix_ts = (raw_ts / 1_000_000) - CHROMIUM_EPOCH_OFFSET
                try:
                    last_visit = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
                except (OSError, OverflowError, ValueError):
                    last_visit = datetime.now(timezone.utc)

                items.append(HistoryItem(
                    url=row["url"],
                    title=row["title"] or row["url"],
                    visit_count=max(row["visit_count"], 1),
                    last_visit=last_visit,
                ))

            conn.close()
        except sqlite3.Error:
            pass
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        return items


class FirefoxBrowser(BrowserBase):
    name = "Firefox"

    def get_db_path(self) -> Optional[str]:
        base = os.path.expandvars(r"%APPDATA%\Mozilla\Firefox\Profiles")
        if not os.path.isdir(base):
            return None
        for entry in os.scandir(base):
            if entry.is_dir():
                candidate = os.path.join(entry.path, "places.sqlite")
                if os.path.exists(candidate):
                    return candidate
        return None

    def get_history(self, query: str, limit: int = 500) -> list[HistoryItem]:
        db_path = self.get_db_path()
        if not db_path:
            return []

        tmp_path = self._copy_db(db_path)
        items: list[HistoryItem] = []

        try:
            conn = sqlite3.connect(tmp_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            like = f"%{query}%"
            cur.execute(
                """
                SELECT p.url, p.title, p.visit_count,
                       p.last_visit_date
                FROM moz_places p
                WHERE (p.url LIKE ? OR p.title LIKE ?)
                  AND p.hidden = 0
                ORDER BY p.last_visit_date DESC
                LIMIT ?
                """,
                (like, like, limit),
            )

            for row in cur.fetchall():
                raw_ts = row["last_visit_date"]
                try:
                    # Firefox stores microseconds since Unix epoch
                    last_visit = datetime.fromtimestamp(raw_ts / 1_000_000, tz=timezone.utc)
                except (OSError, OverflowError, ValueError, TypeError):
                    last_visit = datetime.now(timezone.utc)

                items.append(HistoryItem(
                    url=row["url"],
                    title=row["title"] or row["url"],
                    visit_count=max(row["visit_count"] or 1, 1),
                    last_visit=last_visit,
                ))

            conn.close()
        except sqlite3.Error:
            pass
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        return items


# ---------------------------------------------------------------------------
# Concrete Chromium browser definitions
# ---------------------------------------------------------------------------

class Chrome(ChromiumBrowser):
    name = "Chrome"
    history_path = r"%LOCALAPPDATA%\Google\Chrome\User Data\Default\History"

class Edge(ChromiumBrowser):
    name = "Edge"
    history_path = r"%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\History"

class Brave(ChromiumBrowser):
    name = "Brave"
    history_path = r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data\Default\History"

class Opera(ChromiumBrowser):
    name = "Opera"
    history_path = r"%APPDATA%\Opera Software\Opera Stable\History"

class Vivaldi(ChromiumBrowser):
    name = "Vivaldi"
    history_path = r"%LOCALAPPDATA%\Vivaldi\User Data\Default\History"

class Arc(ChromiumBrowser):
    name = "Arc"
    history_path = r"%LOCALAPPDATA%\Arc\User Data\Default\History"


BROWSERS: dict[str, BrowserBase] = {
    "Chrome": Chrome(),
    "Edge": Edge(),
    "Brave": Brave(),
    "Opera": Opera(),
    "Vivaldi": Vivaldi(),
    "Arc": Arc(),
    "Firefox": FirefoxBrowser(),
}


def get_browser(name: str) -> Optional[BrowserBase]:
    return BROWSERS.get(name)
