// Browser Omnibox – Tab Sync + Activation
// Pushes the current tab list to the local plugin server on any tab change,
// and polls for activation requests from the plugin.

const DEFAULT_PORT = 7323;

async function getPort() {
  const result = await chrome.storage.local.get({ port: DEFAULT_PORT });
  return result.port;
}

async function syncTabs() {
  const port = await getPort();
  const tabs = await chrome.tabs.query({});

  const payload = tabs.map(tab => ({
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
    // Plugin server not running — silently ignore
  }
}

async function pollActivation() {
  const port = await getPort();
  try {
    const resp = await fetch(`http://127.0.0.1:${port}/activate`);
    const data = await resp.json();
    if (data.tabId) {
      const tabId = parseInt(data.tabId, 10);
      if (!isNaN(tabId)) {
        const tab = await chrome.tabs.get(tabId).catch(() => null);
        if (tab) {
          await chrome.tabs.update(tabId, { active: true });
          await chrome.windows.update(tab.windowId, { focused: true });
        }
      }
    }
  } catch {
    // Server not running — ignore
  }
  setTimeout(pollActivation, 500);
}

// Sync on any tab lifecycle event
chrome.tabs.onCreated.addListener(syncTabs);
chrome.tabs.onRemoved.addListener(syncTabs);
chrome.tabs.onUpdated.addListener((_id, change) => {
  if (change.status === "complete" || change.url) syncTabs();
});
chrome.tabs.onActivated.addListener(syncTabs);
chrome.windows.onFocusChanged.addListener(syncTabs);

// Initial sync and start activation polling
syncTabs();
pollActivation();
