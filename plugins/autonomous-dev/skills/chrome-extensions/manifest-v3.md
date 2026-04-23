# Manifest V3 Reference

Manifest V3 (MV3) is the required format for all new Chrome extensions. MV2 was removed from the Web Store (June 2024) and stopped running in Chrome stable (January 2025).

Key changes from MV2:
- Background pages → **service workers** (ephemeral, event-driven, not persistent)
- `chrome.tabs.executeScript` → `chrome.scripting.executeScript`
- `webRequest` blocking → `declarativeNetRequest`
- Stricter CSP — no remotely hosted code, no `eval()`
- `browser_action` / `page_action` merged into `action`

---

## Full Manifest V3 Field Reference

```jsonc
{
  // ─── Required ────────────────────────────────────────────────────────────
  "manifest_version": 3,            // Must be 3
  "name": "My Extension",           // Up to 45 chars (75 for localized)
  "version": "1.0.0",               // Dot-separated integers, e.g. "1.2.3"

  // ─── Recommended ─────────────────────────────────────────────────────────
  "description": "What it does",    // Up to 132 chars
  "icons": {
    "16":  "icons/icon16.png",      // Toolbar, favicon
    "48":  "icons/icon48.png",      // Extensions management page
    "128": "icons/icon128.png"      // Chrome Web Store, install dialog
  },

  // ─── Browser Action (toolbar icon + popup) ────────────────────────────────
  "action": {
    "default_popup": "popup/popup.html",
    "default_icon": {
      "16": "icons/icon16.png",
      "48": "icons/icon48.png"
    },
    "default_title": "My Extension"
  },

  // ─── Background Service Worker ────────────────────────────────────────────
  "background": {
    "service_worker": "background/service-worker.js",
    "type": "module"                // Optional: enables ES modules in the SW
  },

  // ─── Content Scripts ──────────────────────────────────────────────────────
  "content_scripts": [
    {
      "matches": ["https://*.example.com/*"],  // URL patterns
      "js": ["content/content.js"],
      "css": ["content/content.css"],          // Optional CSS injection
      "run_at": "document_end",                // "document_start" | "document_end" | "document_idle"
      "all_frames": false,                     // Run in iframes too?
      "match_about_blank": false,
      "world": "ISOLATED"                      // "ISOLATED" (default) | "MAIN"
    }
  ],

  // ─── Permissions ──────────────────────────────────────────────────────────
  "permissions": [
    "activeTab",       // Scripting access to current tab (user gesture)
    "storage",         // chrome.storage.*
    "scripting",       // chrome.scripting.*
    "contextMenus",
    "notifications",
    "alarms",
    "identity",
    "tabs",            // Read tab URL/title (sensitive — justify to CWS)
    "history",         // (sensitive)
    "bookmarks",       // (sensitive)
    "downloads",
    "clipboardRead",
    "clipboardWrite",
    "webNavigation",
    "declarativeNetRequest",
    "sidePanel",
    "offscreen",
    "unlimitedStorage"
  ],

  // ─── Host Permissions ─────────────────────────────────────────────────────
  "host_permissions": [
    "https://api.example.com/*",    // Specific domain
    "https://*.example.com/*",      // Wildcard subdomain
    "<all_urls>"                    // All URLs (requires CWS justification)
  ],

  // ─── Optional Permissions (requested at runtime) ──────────────────────────
  "optional_permissions": ["history", "bookmarks"],
  "optional_host_permissions": ["https://*/*"],

  // ─── Pages ────────────────────────────────────────────────────────────────
  "options_page": "options/options.html",
  // OR:
  "options_ui": {
    "page": "options/options.html",
    "open_in_tab": false            // Show inline in chrome://extensions
  },

  // ─── Side Panel (Chrome 114+) ─────────────────────────────────────────────
  "side_panel": {
    "default_path": "sidepanel/sidepanel.html"
  },

  // ─── DevTools ─────────────────────────────────────────────────────────────
  "devtools_page": "devtools/devtools.html",

  // ─── Sandbox (for eval-needing pages) ────────────────────────────────────
  "sandbox": {
    "pages": ["sandbox/sandbox.html"]
  },

  // ─── Web Accessible Resources ─────────────────────────────────────────────
  "web_accessible_resources": [
    {
      "resources": ["assets/*", "icons/*", "content/injected.js"],
      "matches": ["<all_urls>"]      // Which pages can load these resources
    }
  ],

  // ─── Network Interception (replaces webRequest blocking) ──────────────────
  "declarative_net_request": {
    "rule_resources": [
      {
        "id": "ruleset1",
        "enabled": true,
        "path": "rules/rules.json"
      }
    ]
  },

  // ─── Content Security Policy ──────────────────────────────────────────────
  "content_security_policy": {
    "extension_pages": "script-src 'self'; object-src 'self'",
    "sandbox": "sandbox allow-scripts; script-src 'self' 'unsafe-eval'"
  },

  // ─── Internationalization ─────────────────────────────────────────────────
  "default_locale": "en",           // Required if using _locales/

  // ─── OAuth2 ───────────────────────────────────────────────────────────────
  "oauth2": {
    "client_id": "YOUR_CLIENT_ID.apps.googleusercontent.com",
    "scopes": ["https://www.googleapis.com/auth/userinfo.email"]
  },

  // ─── External Connections ─────────────────────────────────────────────────
  "externally_connectable": {
    "matches": ["https://*.example.com/*"]
  },

  // ─── Short Name ───────────────────────────────────────────────────────────
  "short_name": "MyExt"             // Up to 12 chars, shown in tight spaces
}
```

---

## MV2 → MV3 Migration Cheatsheet

| MV2 | MV3 |
|---|---|
| `"manifest_version": 2` | `"manifest_version": 3` |
| `"browser_action": { ... }` | `"action": { ... }` |
| `"page_action": { ... }` | `"action": { ... }` |
| `"background": { "scripts": ["bg.js"] }` | `"background": { "service_worker": "sw.js" }` |
| `"background": { "persistent": true }` | Not available — use storage + events |
| `chrome.browserAction.*` | `chrome.action.*` |
| `chrome.pageAction.*` | `chrome.action.*` |
| `chrome.tabs.executeScript(tabId, details)` | `chrome.scripting.executeScript({ target, func/files })` |
| `chrome.tabs.insertCSS(tabId, details)` | `chrome.scripting.insertCSS({ target, css/files })` |
| `webRequest` with blocking | `declarativeNetRequest` |
| `XMLHttpRequest` in background | `fetch()` in service worker |
| Remote scripts: `<script src="https://...">` | Bundle locally — no remote code allowed |
| `chrome.extension.getBackgroundPage()` | Gone — use message passing |
| Inline `<script>` in HTML | Not allowed — use external `.js` files |
| `eval()` / `new Function()` | Not allowed in extension pages (use sandbox page) |

---

## URL Pattern Reference

Used in `content_scripts.matches` and `host_permissions`:

```
https://example.com/            # Exact URL
https://example.com/*           # All paths on this domain
https://*.example.com/*         # All subdomains
https://*/*                     # All HTTPS URLs
http://*/*                      # All HTTP URLs
<all_urls>                      # HTTP + HTTPS + file + ftp
file:///*                       # Local files (requires user to enable)
```

Common mistake: `https://example.com` (no trailing slash or wildcard) only matches the root URL exactly, not pages like `https://example.com/about`.

---

## `run_at` Timing

| Value | When it runs | Use when |
|---|---|---|
| `"document_start"` | Before DOM is built | Injecting CSS, modifying `<head>` |
| `"document_end"` | After DOM is built, before resources load | Default — safe for DOM access |
| `"document_idle"` | After load event | Non-urgent scripts |

---

_Ported from [AJAmit17/chrome-extension-builder](https://github.com/AJAmit17/chrome-extension-builder) (MIT). Last synced: 2026-04-23._
