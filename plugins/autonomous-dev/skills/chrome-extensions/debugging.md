# Extension Debugging Guide

## Where to Find DevTools for Each Context

| Context | How to open DevTools |
|---|---|
| **Popup** | Right-click extension icon → **Inspect** |
| **Service Worker** | `chrome://extensions` → click **"Service Worker"** link |
| **Content Script** | F12 on host page → Console (content script logs appear here) |
| **Options Page** | Right-click on page → **Inspect** |
| **Side Panel** | Right-click inside panel → **Inspect** |

For extension errors: `chrome://extensions` → click the red **Errors** button on your extension card.

---

## The 10 Most Common Errors — Decoded

### 1. "Could not establish connection. Receiving end does not exist."
Content script isn't present on that tab, or the tab navigated before it loaded.
```js
// Fix: handle lastError in callback
chrome.tabs.sendMessage(tab.id, msg, (response) => {
  if (chrome.runtime.lastError) { return; } // silently ignore
  useResponse(response);
});
```
Also check: does your `matches` pattern in manifest actually match the current URL?

### 2. "The message port closed before a response was received."
`sendResponse` was never called, or the listener returned without `return true` for async ops.
```js
// Fix: return true for async sendResponse
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  fetchSomething().then(data => sendResponse(data));
  return true; // ← THIS IS REQUIRED
});
```

### 3. "Extension context invalidated."
The extension was reloaded while a content script still held a reference to it.
```js
// Fix: wrap chrome.* calls in content scripts
try {
  chrome.runtime.sendMessage({ action: "ping" });
} catch (e) {
  if (e.message?.includes("Extension context invalidated")) {
    location.reload(); // or just stop
  }
}
```

### 4. "Unchecked runtime.lastError"
You called an async chrome API without handling errors in the callback.
```js
// Bad: chrome.tabs.sendMessage(tabId, msg, (r) => { use(r); });
// Good:
chrome.tabs.sendMessage(tabId, msg, (r) => {
  if (chrome.runtime.lastError) return;
  use(r);
});
```

### 5. Service worker variables reset between events
State in global variables is lost when the service worker terminates.
```js
// Wrong: let state = {};
// Right: always read from storage
chrome.runtime.onMessage.addListener(async (msg, sender, sendResponse) => {
  const stored = await chrome.storage.local.get("state");
  // use stored.state
  return true;
});
```

### 6. "Refused to execute inline script" (CSP violation)
Extension HTML pages cannot have `<script>` tags with content.
```html
<!-- Wrong: <script>alert(1)</script> -->
<!-- Right: --> <script src="popup.js"></script>
```

### 7. "Refused to load the script from ... (Content Security Policy)"
External CDN scripts are not allowed in extension pages.
```html
<!-- Wrong: <script src="https://cdn.jsdelivr.net/npm/jquery/dist/jquery.min.js"> -->
<!-- Right: download and bundle locally -->
<script src="lib/jquery.min.js"></script>
```

### 8. Content script can't access page JS variables
Content scripts run in an isolated world — different JS context from page scripts.
```js
// Wrong: const x = window.pageVariable; (undefined)
// Right: use world: "MAIN" injection or postMessage bridge
await chrome.scripting.executeScript({
  target: { tabId },
  func: () => window.pageVariable,
  world: "MAIN"
});
```

### 9. Manifest fails to load — "Manifest file is missing or unreadable"
Almost always a JSON syntax error.
```bash
# Quick check
node -e "JSON.parse(require('fs').readFileSync('manifest.json','utf8'))" && echo "Valid"
# Or use: https://jsonlint.com
```

### 10. Service worker doesn't activate
- Check `chrome://extensions` → Errors for syntax errors in service-worker.js
- Verify the path in manifest matches the actual file: `"service_worker": "background/service-worker.js"`
- Try clicking the "Service Worker" link on the extension card to force-start it

---

## Useful Chrome Internal Pages

```
chrome://extensions                 Extension management, errors, reload
chrome://extensions-internals       Low-level extension state
chrome://serviceworker-internals    All registered service workers
chrome://inspect                    Inspect tabs and workers
chrome://net-internals              Network request debugging
```

---

## Debugging Service Workers Step by Step

1. Go to `chrome://extensions`
2. Find your extension → click **"Service Worker"** link → DevTools opens
3. Set breakpoints in the **Sources** tab
4. Trigger an event (send message, click icon, fire alarm)
5. Inspect variables and call stack

If the SW link shows "stopped" — click it to restart, then try again.

---

## Debugging Content Scripts Step by Step

1. Open DevTools on the target page (F12)
2. Go to **Sources** tab
3. In file tree: look for your extension under the **"Content scripts"** section
4. Set breakpoints in your `content.js`
5. Reload the page to re-inject

Content script `console.log` output appears in the **page's** DevTools console, not the extension's.

---

## Force-Reload Everything During Development

After any code change:
1. Go to `chrome://extensions`
2. Click the **↺** (reload) button on your extension card
3. Close and reopen any affected tabs (content scripts need a page reload)
4. Close and reopen the popup

For faster development, consider using [web-ext](https://github.com/mozilla/web-ext) which auto-reloads on file changes.

---

_Ported from [AJAmit17/chrome-extension-builder](https://github.com/AJAmit17/chrome-extension-builder) (MIT). Last synced: 2026-04-23._
