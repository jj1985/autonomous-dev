# Chrome Extension Architecture

Chrome extensions run in multiple isolated JavaScript contexts. Understanding context boundaries is critical — most MV3 bugs come from assuming the popup and content script share memory or the service worker stays alive.

## 1. Extension Contexts

### Popup (Browser Action)
- **Triggered**: User clicks the extension icon
- **Lifecycle**: Created when opened, destroyed when closed — do NOT store state here
- **Has DOM**: Yes (its own HTML document)
- **chrome.* access**: Full (except `chrome.devtools`)
- **Can access page DOM**: No (use content scripts for that)
- **Window object**: Yes

### Content Script
- **Triggered**: Page load matching `matches` patterns in manifest, or programmatic injection via `chrome.scripting.executeScript`
- **Lifecycle**: Tied to the page's lifetime
- **Has DOM**: Yes — the **host page's DOM** (shared)
- **chrome.* access**: Limited — only `chrome.runtime`, `chrome.storage`, `chrome.i18n`, `chrome.identity` (partial), `chrome.alarms`
- **Can talk to page JS**: Via `window.postMessage()` or shared DOM (not directly — different JS worlds)
- **Isolated world**: Yes — runs in an isolated JS context from page scripts (use `world: "MAIN"` in `executeScript` to share the page's JS context)

### Background Service Worker
- **Triggered**: Browser events (install, alarm, message, network request, etc.)
- **Lifecycle**: Ephemeral — spun up on demand, terminated when idle (~30s). **Never store state in variables** — use `chrome.storage`.
- **Has DOM**: No (use `chrome.offscreen` if you need DOM APIs)
- **chrome.* access**: Full
- **Persistent**: No (MV3 removed persistent background pages)
- **Common mistake**: Assuming it stays alive. Always re-initialize state from storage on every event.

### Options Page
- Full extension page (`chrome-extension://<id>/options.html`)
- Full chrome.* access
- Persistent while the tab is open

> **Options page scaffold**: The options page uses the same HTML + JS scaffold as `popup.html`. Use the popup template as a starting point — just wire it up via `"options_page": "options/options.html"` or `"options_ui"` in the manifest:
>
> ```html
> <!-- options/options.html -->
> <!DOCTYPE html>
> <html>
>   <head><meta charset="UTF-8"><title>Settings</title></head>
>   <body>
>     <form id="settings">…</form>
>     <script src="options.js"></script>
>   </body>
> </html>
> ```

### Side Panel (Chrome 114+)
- Persistent panel on the right side of the browser
- Requires `"sidePanel"` permission
- Full chrome.* access, persists while user keeps it open
- Register: `"side_panel": { "default_path": "sidepanel.html" }`

### DevTools Panel
- Only accessible when DevTools is open
- Access to `chrome.devtools.*` APIs
- Cannot use most other chrome.* APIs
- Register via devtools page: `"devtools_page": "devtools.html"`

---

## 2. Lifecycle & Events

### Extension Install / Update
```js
// service-worker.js
chrome.runtime.onInstalled.addListener(({ reason }) => {
  if (reason === "install") {
    // First install — set defaults
    chrome.storage.local.set({ enabled: true });
  }
  if (reason === "update") {
    // Extension updated
  }
});
```

### Service Worker Keepalive Pattern
Service workers can be terminated at any time. For long-running operations:
```js
// Use chrome.alarms to wake the service worker periodically
chrome.alarms.create("keepAlive", { periodInMinutes: 0.4 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "keepAlive") { /* no-op, just keeps it alive */ }
});
```
Even with alarms, do not rely on in-memory state. Always persist to `chrome.storage`.

### Tab Events
```js
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete") {
    // Page finished loading
  }
});

chrome.tabs.onActivated.addListener(({ tabId }) => {
  // User switched to this tab
});
```

---

## 3. Communication Patterns

### Popup ↔ Service Worker (one-time message)
```js
// popup.js — send
chrome.runtime.sendMessage({ action: "fetchData", url: "..." }, (response) => {
  console.log(response.data);
});

// service-worker.js — receive
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "fetchData") {
    fetch(message.url).then(r => r.json()).then(data => {
      sendResponse({ data });
    });
    return true; // CRITICAL: return true for async sendResponse
  }
});
```

### Popup → Content Script (via tabs)
```js
// popup.js
const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
chrome.tabs.sendMessage(tab.id, { action: "highlight" }, (response) => {
  if (chrome.runtime.lastError) {
    console.warn("No content script on this page");
  }
});
```

### Content Script → Service Worker
```js
// content.js
chrome.runtime.sendMessage({ action: "save", data: extractedData }, (response) => {
  console.log("Saved:", response.ok);
});
```

### Long-lived connections (ports)
```js
// content.js — connect
const port = chrome.runtime.connect({ name: "pageStream" });
port.onMessage.addListener((msg) => console.log(msg));
port.postMessage({ type: "start" });

// service-worker.js — accept
chrome.runtime.onConnect.addListener((port) => {
  if (port.name === "pageStream") {
    port.onMessage.addListener((msg) => {
      port.postMessage({ status: "received", msg });
    });
  }
});
```

### Content Script ↔ Page JavaScript
Since content scripts run in an isolated world from page JS, use `window.postMessage`:
```js
// content.js → page
window.postMessage({ source: "my-extension", type: "init" }, "*");

// page JS → content script listener
window.addEventListener("message", (event) => {
  if (event.source !== window) return;
  if (event.data.source !== "my-extension") return;
  // handle
});
```

---

## 4. Storage Architecture

| API | Size | Sync'd | Lifetime | Use for |
|---|---|---|---|---|
| `chrome.storage.local` | 10 MB (unlimited with `"unlimitedStorage"`) | No | Persistent | Feature data, cache |
| `chrome.storage.sync` | 100 KB total, 8 KB/item, 512 items | Yes (Google account) | Persistent | User preferences (keep small) |
| `chrome.storage.session` | 10 MB | No | In-memory, cleared on browser close | Sensitive tokens, temp state |
| `localStorage` | — | — | — | **Never use** — not accessible from service workers |

---

## 5. Permissions Model

### Declared vs. Optional Permissions
```json
{
  "permissions": ["storage", "activeTab"],
  "optional_permissions": ["history", "bookmarks"],
  "host_permissions": ["https://api.example.com/*"],
  "optional_host_permissions": ["https://*/*"]
}
```

Request optional permissions at runtime:
```js
chrome.permissions.request({
  permissions: ["history"],
  origins: ["https://*/*"]
}, (granted) => {
  if (granted) { /* use the permission */ }
});
```

### Least Privilege
- Use `"activeTab"` instead of `"<all_urls>"` when you only need the current tab
- Use `"scripting"` + `"activeTab"` instead of broad host permissions for injection
- Chrome Web Store reviewers check for over-broad permissions — minimise or expect rejection

---

_Ported from [AJAmit17/chrome-extension-builder](https://github.com/AJAmit17/chrome-extension-builder) (MIT). Last synced: 2026-04-23._
