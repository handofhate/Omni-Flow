// Omni Flow Tab Sync
// Sends tab snapshots to the local plugin sidecar and polls for activation requests.

const DEFAULT_PORT = 7323;

async function getPort() {
  const result = await chrome.storage.local.get({ port: DEFAULT_PORT });
  return result.port;
}

async function syncTabs() {
  const port = await getPort();
  const tabs = await chrome.tabs.query({});

  const payload = tabs.map((tab) => ({
    id: String(tab.id),
    url: tab.url,
    title: tab.title,
    windowId: tab.windowId,
    active: tab.active,
  }));

  try {
    await fetch(`http://127.0.0.1:${port}/tabs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch {
    // Sidecar is not running.
  }
}

async function doPollOnce() {
  const port = await getPort();
  try {
    const resp = await fetch(`http://127.0.0.1:${port}/activate`);
    const data = await resp.json();

    if (!data.tabId) return;

    const tabId = parseInt(data.tabId, 10);
    if (Number.isNaN(tabId)) return;

    const tab = await chrome.tabs.get(tabId).catch(() => null);
    if (!tab) return;

    await chrome.tabs.update(tabId, { active: true });
    await chrome.windows.update(tab.windowId, { focused: true });
  } catch {
    // Sidecar is not running.
  }
}

let pollTimer = null;

function schedulePoll() {
  if (pollTimer !== null) return;
  pollTimer = setTimeout(async () => {
    pollTimer = null;
    await doPollOnce();
    schedulePoll();
  }, 500);
}

chrome.tabs.onCreated.addListener(syncTabs);
chrome.tabs.onRemoved.addListener(syncTabs);
chrome.tabs.onUpdated.addListener((_id, change) => {
  if (change.status === "complete" || change.url) syncTabs();
});
chrome.tabs.onActivated.addListener(syncTabs);
chrome.windows.onFocusChanged.addListener(syncTabs);

chrome.alarms.create("pollRestart", { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "pollRestart") schedulePoll();
});

syncTabs();
schedulePoll();
