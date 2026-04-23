# Chrome APIs Reference

Working examples for the `chrome.*` APIs most commonly used in MV3 extensions.

## chrome.tabs

**Permission needed**: `"tabs"` for URL/title access; `"activeTab"` for current-tab scripting (user gesture required).

```js
// Get the currently active tab
const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
console.log(tab.id, tab.url, tab.title);

// Open a new tab
await chrome.tabs.create({ url: "https://example.com", active: true });

// Update (navigate) a tab
await chrome.tabs.update(tab.id, { url: "https://new-url.com" });

// Close a tab
await chrome.tabs.remove(tab.id);

// Get all open tabs
const allTabs = await chrome.tabs.query({});

// Listen for tab events
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete") { /* page loaded */ }
});
chrome.tabs.onActivated.addListener(({ tabId, windowId }) => { /* switched tab */ });
```

---

## chrome.runtime

**Permission needed**: Built-in, none required.

```js
// Get extension info
const manifest = chrome.runtime.getManifest();
const id = chrome.runtime.id;
const url = chrome.runtime.getURL("popup/popup.html");

// Open options page
chrome.runtime.openOptionsPage();

// Reload extension (dev)
chrome.runtime.reload();

// Install/update events
chrome.runtime.onInstalled.addListener(({ reason, previousVersion }) => {
  if (reason === "install") { /* first install */ }
  if (reason === "update") { /* extension updated */ }
});

// Send message to background
chrome.runtime.sendMessage({ action: "doThing" }, (response) => {
  if (chrome.runtime.lastError) { /* handle error */ return; }
  console.log(response);
});

// Listen for messages (in background/content)
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "doThing") {
    doThingAsync().then(result => sendResponse(result));
    return true; // CRITICAL for async sendResponse
  }
});
```

---

## chrome.storage

**Permission needed**: `"storage"`.

```js
// ── local (up to 10MB, not synced) ──────────────────────────────────────
await chrome.storage.local.set({ key: "value", count: 42 });
const { key, count } = await chrome.storage.local.get(["key", "count"]);
const all = await chrome.storage.local.get(null); // get everything
await chrome.storage.local.remove("key");
await chrome.storage.local.clear();

// ── sync (up to 100KB, synced across devices) ────────────────────────────
await chrome.storage.sync.set({ theme: "dark" });
const { theme } = await chrome.storage.sync.get("theme");

// ── session (up to 10MB, in-memory, cleared on browser close) ────────────
await chrome.storage.session.set({ tempData: { /* ... */ } });

// ── Listen for changes (any context) ─────────────────────────────────────
chrome.storage.onChanged.addListener((changes, area) => {
  // area: "local" | "sync" | "session"
  for (const [key, { oldValue, newValue }] of Object.entries(changes)) {
    console.log(`${area}/${key}: ${oldValue} → ${newValue}`);
  }
});
```

**Never use `localStorage` in extensions** — it is not accessible from service workers and does not persist correctly across contexts.

---

## chrome.scripting

**Permission needed**: `"scripting"` + host permissions or `"activeTab"`.

```js
// Inject a JS file
await chrome.scripting.executeScript({
  target: { tabId: tab.id },
  files: ["content/content.js"]
});

// Inject an inline function (args must be JSON-serializable)
const results = await chrome.scripting.executeScript({
  target: { tabId: tab.id },
  func: (color) => {
    document.body.style.background = color;
    return document.title;
  },
  args: ["red"]
});
console.log(results[0].result); // return value from injected function

// Inject into all frames
await chrome.scripting.executeScript({
  target: { tabId: tab.id, allFrames: true },
  files: ["content/content.js"]
});

// Access page JS globals (MAIN world — no chrome.* access)
const result = await chrome.scripting.executeScript({
  target: { tabId: tab.id },
  func: () => window.__somePageGlobal,
  world: "MAIN"
});

// Inject CSS
await chrome.scripting.insertCSS({
  target: { tabId: tab.id },
  css: "body { background: #000 !important; }"
});

// Remove injected CSS
await chrome.scripting.removeCSS({
  target: { tabId: tab.id },
  css: "body { background: #000 !important; }"
});
```

---

## chrome.action

**Permission needed**: Defined in manifest as `"action"` key — no separate permission.

```js
// Badge (overlay on extension icon)
await chrome.action.setBadgeText({ text: "3" });           // clear with ""
await chrome.action.setBadgeBackgroundColor({ color: "#FF0000" });
await chrome.action.setBadgeTextColor({ color: "#FFFFFF" });

// Enable/disable icon per tab
await chrome.action.disable(tab.id);
await chrome.action.enable(tab.id);

// Change icon dynamically
await chrome.action.setIcon({ path: { "48": "icons/icon48-active.png" } });

// Change tooltip
await chrome.action.setTitle({ title: "Extension is active" });

// Handle click (only fires when NO popup is defined)
chrome.action.onClicked.addListener((tab) => { /* handle */ });
```

---

## chrome.alarms

**Permission needed**: `"alarms"`.

```js
// One-time alarm (minutes from now)
chrome.alarms.create("myAlarm", { delayInMinutes: 1 });

// Repeating alarm
chrome.alarms.create("repeater", { periodInMinutes: 30 });

// At a specific time
chrome.alarms.create("atTime", { when: Date.now() + 60000 });

// Listen
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "myAlarm") { doSomething(); }
});

// Manage
await chrome.alarms.get("myAlarm");
await chrome.alarms.getAll();
await chrome.alarms.clear("myAlarm");
await chrome.alarms.clearAll();
```

Minimum period is 1 minute in production (0.5 minute in dev mode with DevTools open).

---

## chrome.contextMenus

**Permission needed**: `"contextMenus"`.

```js
// Create in onInstalled (persists across sessions)
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "search-text",
    title: 'Search "%s"',           // %s = selected text
    contexts: ["selection"]          // "all" | "page" | "selection" | "link" | "image" | "video" | "editable"
  });
});

// Handle clicks
chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "search-text") {
    const q = encodeURIComponent(info.selectionText);
    chrome.tabs.create({ url: `https://google.com/search?q=${q}` });
  }
});
```

---

## chrome.notifications

**Permission needed**: `"notifications"`.

```js
chrome.notifications.create("notif1", {
  type: "basic",
  iconUrl: "icons/icon48.png",
  title: "Alert",
  message: "Something happened",
  buttons: [{ title: "View" }, { title: "Dismiss" }]
});

chrome.notifications.onButtonClicked.addListener((id, buttonIndex) => { });
chrome.notifications.onClicked.addListener((id) => { });
chrome.notifications.clear("notif1");
```

---

## chrome.identity (OAuth)

**Permission needed**: `"identity"` + `"oauth2"` in manifest.

```js
// Google OAuth (user signed into Chrome)
chrome.identity.getAuthToken({ interactive: true }, (token) => {
  if (chrome.runtime.lastError) return;
  fetch("https://www.googleapis.com/oauth2/v1/userinfo", {
    headers: { Authorization: `Bearer ${token}` }
  });
});

// Non-Google OAuth (web auth flow)
const redirectUrl = chrome.identity.getRedirectURL();
chrome.identity.launchWebAuthFlow({
  url: `https://provider.com/oauth?redirect_uri=${redirectUrl}&...`,
  interactive: true
}, (redirectedTo) => {
  const token = new URL(redirectedTo).searchParams.get("access_token");
});
```

---

## chrome.declarativeNetRequest

**Permission needed**: `"declarativeNetRequest"`.

```json
// rules.json
[
  {
    "id": 1, "priority": 1,
    "action": { "type": "block" },
    "condition": { "urlFilter": "tracker.example.com", "resourceTypes": ["script"] }
  }
]
```

```json
// manifest.json
"declarative_net_request": {
  "rule_resources": [{ "id": "ruleset1", "enabled": true, "path": "rules/rules.json" }]
}
```

```js
// Dynamic rules at runtime
await chrome.declarativeNetRequest.updateDynamicRules({
  addRules: [{ id: 10, priority: 1, action: { type: "block" }, condition: { urlFilter: "ads.example.com" } }],
  removeRuleIds: [5]
});
```

---

## chrome.sidePanel (Chrome 114+)

**Permission needed**: `"sidePanel"` + `"side_panel"` in manifest.

```json
// manifest.json
"side_panel": { "default_path": "sidepanel/sidepanel.html" }
```

```js
chrome.sidePanel.open({ tabId: tab.id });
chrome.sidePanel.setOptions({ tabId: tab.id, path: "sidepanel/alt.html", enabled: true });
```

---

## chrome.offscreen (Chrome 109+)

**Permission needed**: `"offscreen"`.

Use when you need DOM access from a service worker (parsing HTML, playing audio, using canvas).

```js
// Create offscreen document
await chrome.offscreen.createDocument({
  url: "offscreen/offscreen.html",
  reasons: ["DOM_PARSER"],
  justification: "Parse HTML from the page"
});

// Communicate via standard messaging
chrome.runtime.sendMessage({ action: "parseHtml", html: rawHtml }, (result) => { });

// Close when done
await chrome.offscreen.closeDocument();
```

Available reasons: `"AUDIO_PLAYBACK"`, `"BLOBS"`, `"CLIPBOARD"`, `"DOM_PARSER"`, `"DOM_SCRAPING"`, `"GEOLOCATION"`, `"LOCAL_STORAGE"`, `"MATCH_MEDIA"`, `"TESTING"`, `"USER_MEDIA"`, `"WEB_RTC"`, `"WORKERS"`.

---

## Message Passing Patterns

### Popup → Content Script
```js
// popup.js
const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
chrome.tabs.sendMessage(tab.id, { action: "highlight" }, (response) => {
  if (chrome.runtime.lastError) { /* no content script on this page */ return; }
});
```

### Content Script → Background
```js
// content.js
chrome.runtime.sendMessage({ action: "save", data: extractedData });
```

### Long-lived connection (port)
```js
// content.js
const port = chrome.runtime.connect({ name: "stream" });
port.postMessage({ start: true });
port.onMessage.addListener((msg) => console.log(msg));

// service-worker.js
chrome.runtime.onConnect.addListener((port) => {
  if (port.name === "stream") {
    port.onMessage.addListener((msg) => port.postMessage({ ack: true }));
  }
});
```

### Content Script ↔ Page JavaScript (postMessage bridge)
```js
// content.js → page
window.postMessage({ source: "__myExt__", type: "init" }, "*");

// content.js ← page listener
window.addEventListener("message", (e) => {
  if (e.source !== window || e.data?.source !== "__myExt__") return;
  // handle
});
```

---

_Ported from [AJAmit17/chrome-extension-builder](https://github.com/AJAmit17/chrome-extension-builder) (MIT). Last synced: 2026-04-23._
