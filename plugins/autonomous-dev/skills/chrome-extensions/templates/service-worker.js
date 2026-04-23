// service-worker.js — Background script (Manifest V3)
// Runs as an event-driven service worker — NOT persistent
// State resets every time the worker wakes up — use chrome.storage for persistence
// No DOM access, no window object
// Full chrome.* API access
// Can use fetch()

"use strict";

// ─── Install / Update ─────────────────────────────────────────────────────
chrome.runtime.onInstalled.addListener(async ({ reason, previousVersion }) => {
  if (reason === "install") {
    console.log("[SW] Extension installed for the first time");
    // Set default storage values
    await chrome.storage.local.set({
      enabled: true,
      settings: {
        theme: "auto",
        notifications: true
      }
    });
    // Optionally open onboarding page
    // chrome.tabs.create({ url: "onboarding/onboarding.html" });
  }

  if (reason === "update") {
    console.log(`[SW] Updated from ${previousVersion} to`, chrome.runtime.getManifest().version);
  }
});

// ─── Startup ─────────────────────────────────────────────────────────────
chrome.runtime.onStartup.addListener(() => {
  console.log("[SW] Browser started, re-initializing state from storage");
  // Re-init anything that needs it from storage
});

// ─── Message Handler ──────────────────────────────────────────────────────
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log("[SW] Message received:", message.action, "from tab:", sender.tab?.id);

  // Dispatch to handlers
  switch (message.action) {
    case "fetchData":
      handleFetchData(message, sendResponse);
      return true; // async

    case "saveData":
      handleSaveData(message, sendResponse);
      return true; // async

    case "getStatus":
      handleGetStatus(sendResponse);
      return true; // async

    default:
      console.warn("[SW] Unknown action:", message.action);
      sendResponse({ error: "Unknown action" });
  }
});

// ─── Action Click (when no popup defined) ────────────────────────────────
chrome.action.onClicked.addListener(async (tab) => {
  // Only fires if manifest has NO default_popup in "action"
  const { enabled } = await chrome.storage.local.get("enabled");
  await chrome.storage.local.set({ enabled: !enabled });
  await updateBadge(!enabled);
});

// ─── Tab Events ───────────────────────────────────────────────────────────
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status !== "complete") return;
  // Tab finished loading — do something if needed
});

// ─── Alarm Handler ────────────────────────────────────────────────────────
chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === "periodicTask") {
    await runPeriodicTask();
  }
});

// Create a periodic alarm (call this from onInstalled)
async function setupAlarms() {
  await chrome.alarms.create("periodicTask", { periodInMinutes: 60 });
}

// ─── Context Menu ─────────────────────────────────────────────────────────
// Set up context menus in onInstalled (they persist across sessions)
// chrome.contextMenus.create({ id: "myMenu", title: "Do Something", contexts: ["selection"] });

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === "myMenu") {
    const selectedText = info.selectionText;
    // handle selection
  }
});

// ─── Handler Functions ────────────────────────────────────────────────────
async function handleFetchData(message, sendResponse) {
  try {
    const response = await fetch(message.url, {
      headers: { "Content-Type": "application/json" }
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    sendResponse({ success: true, data });
  } catch (err) {
    console.error("[SW] Fetch error:", err);
    sendResponse({ success: false, error: err.message });
  }
}

async function handleSaveData(message, sendResponse) {
  try {
    await chrome.storage.local.set({ [message.key]: message.value });
    sendResponse({ success: true });
  } catch (err) {
    sendResponse({ success: false, error: err.message });
  }
}

async function handleGetStatus(sendResponse) {
  const { enabled = false } = await chrome.storage.local.get("enabled");
  sendResponse({ enabled });
}

async function runPeriodicTask() {
  console.log("[SW] Running periodic task...");
  // Do background work here
}

// ─── Badge Helpers ────────────────────────────────────────────────────────
async function updateBadge(enabled) {
  await chrome.action.setBadgeText({ text: enabled ? "ON" : "" });
  await chrome.action.setBadgeBackgroundColor({ color: enabled ? "#10B981" : "#6B7280" });
}
