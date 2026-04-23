# Extension Security & Content Security Policy

## Default CSP for Extension Pages (MV3)

All extension pages (`popup.html`, `options.html`, etc.) are subject to:

```
script-src 'self'; object-src 'self'
```

This enforces:
- No inline `<script>alert()</script>` — use external `.js` files only
- No `eval()`, `new Function()`, `setTimeout("string")`
- No external CDN scripts (`<script src="https://...">`)
- Scripts from the extension package only (`src="popup.js"`)

---

## Customizing CSP

```json
"content_security_policy": {
  "extension_pages": "script-src 'self'; object-src 'self'",
  "sandbox": "sandbox allow-scripts; script-src 'self' 'unsafe-eval'"
}
```

- `extension_pages`: applies to popup, options, and other extension pages
- `sandbox`: applies only to registered sandboxed pages — the only place `'unsafe-eval'` is allowed

**You cannot add `'unsafe-inline'` or `'unsafe-eval'` to `extension_pages`** — Chrome Web Store will reject it. If you need `eval()`, use a sandbox page as the escape hatch (below).

---

## Sandboxed Pages (for eval use cases)

If you absolutely need `eval()` — for example to run a templating engine like Handlebars or a dynamic expression evaluator — use a sandboxed page:

```json
// manifest.json
"sandbox": {
  "pages": ["sandbox/sandbox.html"]
},
"content_security_policy": {
  "extension_pages": "script-src 'self'; object-src 'self'",
  "sandbox": "sandbox allow-scripts allow-forms; script-src 'self' 'unsafe-eval'"
}
```

**Sandboxed page limitations**:
- Cannot use `chrome.*` APIs
- Cannot access extension resources directly
- Communicates via `window.postMessage`

```js
// From popup or service worker — send code to sandbox iframe
const sandboxFrame = document.getElementById("sandbox");
sandboxFrame.contentWindow.postMessage({ code: templateStr }, "*");

// In sandbox.html
window.addEventListener("message", (e) => {
  const result = eval(e.data.code); // safe — sandboxed
  e.source.postMessage({ result }, "*");
});
```

This is the **only** supported way to run `eval`-requiring code in an MV3 extension.

---

## XSS Prevention

**Never use `innerHTML` with untrusted input:**

```js
// XSS risk
element.innerHTML = userInput;
element.innerHTML = `<span>${fetchedData}</span>`;

// Safe alternatives
element.textContent = userInput;

const span = document.createElement("span");
span.textContent = fetchedData;
element.appendChild(span);
```

**Never use `eval()` with external data:**

```js
// Never
eval(responseFromServer);
new Function(userCode)();
setTimeout(dynamicString, 1000);

// Parse data properly
const data = JSON.parse(responseText); // JSON.parse is safe
```

---

## Content Script Security

Content scripts share the DOM with the host page but run in an isolated JS world. Security considerations:

**DOM XSS**: Content scripts that write to the DOM can introduce XSS. Always sanitize:
```js
// Dangerous
document.body.innerHTML += userInput;

// Safe
const el = document.createElement("div");
el.textContent = userInput;
document.body.appendChild(el);
```

**Page script isolation**: Content scripts cannot access page JS variables, and page JS cannot access your content script variables. This is a security feature, not a bug.

**CORS from content scripts**: Content scripts run in the context of the page and are subject to its CORS policy. Make cross-origin requests from the service worker instead, where your extension's host permissions apply.

---

## Permissions Security Model

**Principle of least privilege** — only request permissions you actually use:

| Instead of | Use |
|---|---|
| `"tabs"` + host permissions | `"activeTab"` (for current-tab operations) |
| `"<all_urls>"` | Specific domains: `"https://api.example.com/*"` |
| Declaring all permissions | Optional permissions + `chrome.permissions.request()` at runtime |

**Sensitive permissions that require CWS justification:**
- `"history"` — access browsing history
- `"bookmarks"` — read/write bookmarks
- `"cookies"` — requires host permissions too
- `"tabs"` — reading tab URLs and titles
- `"clipboardRead"` — read clipboard without user gesture

---

## Web Accessible Resources

Files listed under `web_accessible_resources` can be loaded by web pages. Minimize this list:

```json
"web_accessible_resources": [
  {
    "resources": ["assets/logo.png"],     // Only what's needed
    "matches": ["https://mysite.com/*"]   // Only from specific origins
  }
]
```

Don't use `"matches": ["<all_urls>"]` for WAR unless necessary — it allows any site to load your extension resources.

---

## Data Handling Best Practices

- **Don't store sensitive data in `chrome.storage.sync`** — it can be accessed if someone has access to the user's Google account
- **Use `chrome.storage.session`** for sensitive in-memory data (cleared on browser close)
- **Never log sensitive data** to the console — it's visible to anyone with DevTools
- **Validate all external data** before using it — treat API responses and web page content as untrusted

---

_Ported from [AJAmit17/chrome-extension-builder](https://github.com/AJAmit17/chrome-extension-builder) (MIT). Last synced: 2026-04-23._
