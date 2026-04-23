---
name: chrome-extensions
description: "Build, scaffold, debug, and publish Chrome Manifest V3 extensions — manifest fields, chrome.* APIs, architecture, CSP, debugging, and Web Store publishing. Use when authoring a Chrome extension, migrating MV2 to MV3, or diagnosing extension errors. TRIGGER when: chrome extension, manifest.json, chrome.*, content script, service worker, MV3, CRX, Chrome Web Store. DO NOT TRIGGER when: generic web dev, Node.js server, non-extension frontend, plain browser JS."
allowed-tools: [Read]
---

# Chrome Extensions (Manifest V3)

Complete reference for building, debugging, and publishing Chrome browser extensions using Manifest V3. This skill activates for any task that touches `manifest.json`, `chrome.*` APIs, service workers, content scripts, popup/options pages, or Chrome Web Store submissions.

Manifest V2 is end-of-life. All new extensions MUST use MV3. MV2 extensions stopped running in Chrome stable in January 2025.

---

## Quick Decision Guide

| What you need | Where to go |
|---|---|
| Manifest field reference, MV2→MV3 migration | `manifest-v3.md` |
| Use a specific `chrome.*` API | `chrome-apis.md` |
| Understand extension contexts (popup, content script, SW, options, side panel) | `architecture.md` |
| CSP rules, `eval` ban, sandbox escape hatch | `security-csp.md` |
| Diagnose the 10 most common runtime errors | `debugging.md` |
| Publish to the Chrome Web Store | `publishing.md` |
| Starter manifest, popup, content script, service worker | `templates/` |

---

## Workflow: Scaffold a New Extension

**Step 1 — Identify the extension type**

Ask the user (or infer from context) which surfaces the extension needs:
- **Popup** — UI in a small window when clicking the toolbar icon
- **Content Script** — Runs code injected into web pages
- **Background Service Worker** — Persistent logic, no UI
- **DevTools Panel** — Panel inside Chrome DevTools
- **Options Page** — Settings page accessible from the extension menu
- **Side Panel** — Persistent panel on the right side (Chrome 114+)
- **Combo** — Most real-world extensions combine multiple surfaces

**Step 2 — Start from the manifest template**

Always start from `templates/manifest-v3.json` and customize. Key fields to configure:
```json
{
  "manifest_version": 3,
  "name": "Your Extension",
  "version": "1.0.0",
  "description": "What it does",
  "permissions": [],
  "host_permissions": [],
  "action": {},
  "background": { "service_worker": "background/service-worker.js" },
  "content_scripts": []
}
```

**Step 3 — Scaffold the file structure**

```
my-extension/
├── manifest.json          ← Required. The brain of the extension.
├── popup/
│   ├── popup.html
│   ├── popup.css
│   └── popup.js
├── content/
│   └── content.js
├── background/
│   └── service-worker.js
├── options/
│   ├── options.html
│   └── options.js
├── icons/
│   ├── icon16.png
│   ├── icon48.png
│   └── icon128.png
└── _locales/
    └── en/
        └── messages.json
```

**Step 4 — Apply least-privilege permissions**

Only request what you actually need. The Chrome Web Store will reject overly broad permissions, and users see scary warnings. See `chrome-apis.md` for per-API permission requirements.

Common patterns:
- Read/modify current tab → `"activeTab"`
- Access all URLs → `"<all_urls>"` in `host_permissions` (justify in CWS listing)
- Store data → `"storage"`
- Make network requests from background → list domains in `host_permissions`
- Read/write clipboard → `"clipboardRead"` / `"clipboardWrite"`

**Step 5 — Write code per context**

Each extension context has strict rules. See `architecture.md` for full details.

| Context | Can access DOM? | Can use `chrome.*` APIs? | Has `window`? |
|---|---|---|---|
| Popup | Own DOM only | Yes | Yes |
| Content Script | Page's DOM | Limited subset | Page's window |
| Service Worker | No | Full | No |
| Options Page | Own DOM | Yes | Yes |

**Step 6 — Test locally**

1. Open `chrome://extensions`
2. Enable **Developer Mode** (top-right toggle)
3. Click **Load unpacked** → select your extension folder
4. Test and reload after changes
5. Check the console: popup → right-click icon → Inspect; service worker → click the "Service Worker" link

**Step 7 — Debug issues**

See `debugging.md` for decoded error messages and step-by-step DevTools workflows for each context.

**Step 8 — Package and publish**

See `publishing.md` for the Chrome Web Store submission checklist and review-friendly practices.

---

## Key Principles

**Security first**: Never use `eval()`, `innerHTML` with untrusted input, or `unsafe-eval` in the `extension_pages` CSP. Use `textContent` and DOM APIs instead. See `security-csp.md` for the sandbox-page escape hatch when `eval` is genuinely required.

**Message passing is the only state-sharing mechanism**: Popup and content scripts cannot directly share state. Use `chrome.runtime.sendMessage()` / `chrome.tabs.sendMessage()`. The service worker acts as the broker.

**The service worker dies**: MV3 service workers are ephemeral. Never store state in SW variables — always read and write `chrome.storage`.

**Storage**: Use `chrome.storage.local` (or `.sync` / `.session`) for persistence across contexts. **Never use `localStorage`** — it is not accessible from service workers.

---

## Common Patterns (Quick Reference)

### Send a message from popup to content script
```js
// popup.js
const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
chrome.tabs.sendMessage(tab.id, { action: "doSomething" }, (response) => {
  if (chrome.runtime.lastError) return; // no content script on that page
  console.log(response);
});
```

### Listen in the content script
```js
// content.js
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "doSomething") {
    // do it
    sendResponse({ success: true });
  }
  return true; // keep channel open for async
});
```

### Store and retrieve data
```js
await chrome.storage.local.set({ key: value });
const result = await chrome.storage.local.get(["key"]);
console.log(result.key);
```

### Inject a script into the active tab (from popup or background)
```js
const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
await chrome.scripting.executeScript({
  target: { tabId: tab.id },
  files: ["content/content.js"]
});
```
Requires `"scripting"` permission and `"activeTab"` or host permissions.

---

## See

Knowledge docs:
- [manifest-v3.md](manifest-v3.md) — Manifest fields, MV2→MV3 migration
- [chrome-apis.md](chrome-apis.md) — Full `chrome.*` API usage with examples
- [architecture.md](architecture.md) — Extension contexts, lifecycle, communication, storage, permissions
- [security-csp.md](security-csp.md) — CSP rules, XSS prevention, sandbox pages
- [debugging.md](debugging.md) — The 10 most common errors, DevTools workflow per context
- [publishing.md](publishing.md) — Chrome Web Store submission, rejection fixes, versioning

Templates:
- [templates/manifest-v3.json](templates/manifest-v3.json) — Base manifest template
- [templates/popup.html](templates/popup.html) — Popup UI starter
- [templates/content.js](templates/content.js) — Content script with message listener
- [templates/service-worker.js](templates/service-worker.js) — Background service worker

---

> **Ported from**: [AJAmit17/chrome-extension-builder](https://github.com/AJAmit17/chrome-extension-builder) (MIT)
> **Last synced**: 2026-04-23
> **Verify manifest/API**: https://developer.chrome.com/docs/extensions/reference/manifest
> **Verify Web Store policy**: https://developer.chrome.com/docs/webstore/program-policies
