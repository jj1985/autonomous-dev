// content.js — Injected into web pages matching `matches` in manifest
// Shares DOM with the page but runs in an isolated JS world
// chrome.* access is LIMITED — only: runtime, storage, i18n, alarms

"use strict";

// ─── Guard: Prevent double-injection ─────────────────────────────────────
if (window.__myExtensionInjected) {
  // Already running on this page — stop here
  throw new Error("Extension already injected");
}
window.__myExtensionInjected = true;

// ─── Init ─────────────────────────────────────────────────────────────────
console.log("[MyExtension] Content script loaded on:", window.location.href);

// ─── Message Listener ─────────────────────────────────────────────────────
// Listens for messages from popup or service worker
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log("[MyExtension] Received message:", message);

  if (message.action === "doSomething") {
    try {
      const result = doSomethingOnPage();
      sendResponse({ success: true, data: result });
    } catch (err) {
      sendResponse({ success: false, error: err.message });
    }
    return; // sync — no return true needed
  }

  if (message.action === "extractData") {
    extractDataAsync().then((data) => {
      sendResponse({ success: true, data });
    }).catch((err) => {
      sendResponse({ success: false, error: err.message });
    });
    return true; // CRITICAL: return true for async sendResponse
  }
});

// ─── Page Interaction Functions ───────────────────────────────────────────
function doSomethingOnPage() {
  // Example: highlight all paragraphs
  const paragraphs = document.querySelectorAll("p");
  paragraphs.forEach((p) => {
    p.style.outline = "2px solid red";
  });
  return { count: paragraphs.length };
}

async function extractDataAsync() {
  // Example: extract page metadata
  return {
    title: document.title,
    url: window.location.href,
    description: document.querySelector('meta[name="description"]')?.content ?? "",
    headings: [...document.querySelectorAll("h1, h2")].map((h) => h.textContent.trim())
  };
}

// ─── Storage Example ──────────────────────────────────────────────────────
async function loadSettings() {
  const { settings = {} } = await chrome.storage.local.get("settings");
  return settings;
}

// ─── Page Event Listeners ─────────────────────────────────────────────────
// Listen for DOM mutations (e.g., SPA navigation)
const observer = new MutationObserver((mutations) => {
  // Handle SPA page changes — check if URL changed
  // Implement as needed
});

// Observe body for large structural changes
// observer.observe(document.body, { childList: true, subtree: false });

// ─── Communicate with Page JS (if needed) ────────────────────────────────
// Since content script is isolated from page JS, use postMessage as a bridge
window.addEventListener("message", (event) => {
  // Only accept messages from this window (not iframes)
  if (event.source !== window) return;
  // Only handle messages tagged for this extension
  if (event.data?.source !== "__myExtension__") return;

  console.log("[MyExtension] Message from page:", event.data);
  // Handle the message...
});

// Send message to page JS
function sendToPage(type, payload) {
  window.postMessage({ source: "__myExtension__", type, payload }, "*");
}
