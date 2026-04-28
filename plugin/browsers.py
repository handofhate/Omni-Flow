import os
import re
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import urlparse


CHROMIUM_EPOCH_OFFSET = 11644473600

_TRACKING_PARAMS = re.compile(
    r"&?(utm_\w+|fbclid|gclid|msclkid|ref|source|mc_\w+|_ga|twclid)=[^&]*",
    re.IGNORECASE,
)


def _escape_like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _clean_url(url: str) -> str:
    try:
        p = urlparse(url)
        query = _TRACKING_PARAMS.sub("", p.query).strip("&")
        return p._replace(query=query, fragment="").geturl()
    except Exception:
        return url


@dataclass
class HistoryItem:
    url: str
    title: str
    visit_count: int
    last_visit: datetime
    open_tab_id: Optional[str] = field(default=None)

    @property
    def _parsed(self):
        return urlparse(self.url)

    @property
    def hostname(self) -> str:
        return self._parsed.netloc.lower()

    @property
    def hostname_bare(self) -> str:
        h = self.hostname
        return h[4:] if h.startswith("www.") else h

    @property
    def path_depth(self) -> int:
        parts = [p for p in self._parsed.path.split("/") if p]
        return len(parts)

    def frecency_score(self) -> float:
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
        return len(_clean_url(self.url))

    def match_rank(self, query: str) -> int:
        q = query.lower()
        host = self.hostname_bare
        if host.startswith(q):
            return 0
        if q in self.url.lower():
            return 1
        return 2


class BrowserBase:
    name: str = ""
    history_path: str = ""

    def get_db_path(self) -> Optional[str]:
        path = os.path.expandvars(self.history_path)
        if os.path.exists(path):
            return path
        return None

    def _copy_db(self, db_path: str) -> str:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".sqlite")
        tmp.close()
        shutil.copy2(db_path, tmp.name)
        return tmp.name

    def get_history(self, query: str, limit: int = 500) -> List[HistoryItem]:
        raise NotImplementedError


class ChromiumBrowser(BrowserBase):
    def get_history(self, query: str, limit: int = 500) -> List[HistoryItem]:
        db_path = self.get_db_path()
        if not db_path:
            return []

        tmp_path = self._copy_db(db_path)
        items: List[HistoryItem] = []

        try:
            conn = sqlite3.connect(tmp_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            like = "%{0}%".format(_escape_like(query))
            cur.execute(
                """
                SELECT url, title, visit_count, last_visit_time
                FROM urls
                WHERE (url LIKE ? ESCAPE '\\' OR title LIKE ? ESCAPE '\\')
                  AND hidden = 0
                ORDER BY last_visit_time DESC
                LIMIT ?
                """,
                (like, like, limit),
            )

            for row in cur.fetchall():
                raw_ts = row["last_visit_time"]
                unix_ts = (raw_ts / 1000000) - CHROMIUM_EPOCH_OFFSET
                try:
                    last_visit = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
                except (OSError, OverflowError, ValueError):
                    last_visit = datetime.now(timezone.utc)

                items.append(
                    HistoryItem(
                        url=row["url"],
                        title=row["title"] or row["url"],
                        visit_count=max(row["visit_count"], 1),
                        last_visit=last_visit,
                    )
                )

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

    def get_history(self, query: str, limit: int = 500) -> List[HistoryItem]:
        db_path = self.get_db_path()
        if not db_path:
            return []

        tmp_path = self._copy_db(db_path)
        items: List[HistoryItem] = []

        try:
            conn = sqlite3.connect(tmp_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            like = "%{0}%".format(_escape_like(query))
            cur.execute(
                """
                SELECT p.url, p.title, p.visit_count, p.last_visit_date
                FROM moz_places p
                WHERE (p.url LIKE ? ESCAPE '\\' OR p.title LIKE ? ESCAPE '\\')
                  AND p.hidden = 0
                ORDER BY p.last_visit_date DESC
                LIMIT ?
                """,
                (like, like, limit),
            )

            for row in cur.fetchall():
                raw_ts = row["last_visit_date"]
                try:
                    last_visit = datetime.fromtimestamp(raw_ts / 1000000, tz=timezone.utc)
                except (OSError, OverflowError, ValueError, TypeError):
                    last_visit = datetime.now(timezone.utc)

                items.append(
                    HistoryItem(
                        url=row["url"],
                        title=row["title"] or row["url"],
                        visit_count=max(row["visit_count"] or 1, 1),
                        last_visit=last_visit,
                    )
                )

            conn.close()
        except sqlite3.Error:
            pass
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        return items


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


BROWSERS: Dict[str, BrowserBase] = {
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
