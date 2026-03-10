/**
 * MUSEON Chrome Extension - Background Service Worker
 * Maintains WebSocket connection to Gateway and handles context menu actions.
 */

const GATEWAY_WS_URL = "ws://127.0.0.1:8765/ws/extension";
const RECONNECT_INTERVAL = 5000;

let ws = null;
let reconnectTimer = null;

// ── WebSocket Connection ──

function connect() {
  if (ws && ws.readyState === WebSocket.OPEN) return;

  try {
    ws = new WebSocket(GATEWAY_WS_URL);

    ws.onopen = () => {
      console.log("[MUSEON] Connected to Gateway");
      clearTimeout(reconnectTimer);
      ws.send(JSON.stringify({ type: "extension_hello", version: "1.0.0" }));
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleGatewayMessage(data);
      } catch (e) {
        console.warn("[MUSEON] Invalid message:", e);
      }
    };

    ws.onclose = () => {
      console.log("[MUSEON] Disconnected, reconnecting...");
      scheduleReconnect();
    };

    ws.onerror = (err) => {
      console.error("[MUSEON] WebSocket error:", err);
      ws.close();
    };
  } catch (e) {
    console.error("[MUSEON] Connection failed:", e);
    scheduleReconnect();
  }
}

function scheduleReconnect() {
  clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(connect, RECONNECT_INTERVAL);
}

function sendToGateway(payload) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(payload));
    return true;
  }
  console.warn("[MUSEON] Not connected, queuing message");
  return false;
}

// ── Handle Gateway Messages ──

function handleGatewayMessage(data) {
  switch (data.type) {
    case "notification":
      chrome.notifications.create({
        type: "basic",
        title: data.title || "MUSEON",
        message: data.message || "",
        iconUrl: "icons/icon48.png",
      });
      break;
    case "badge_update":
      chrome.action.setBadgeText({ text: data.count ? String(data.count) : "" });
      break;
    default:
      console.log("[MUSEON] Unknown message type:", data.type);
  }
}

// ── Context Menu ──

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "museon-remember",
    title: "MUSEON: Remember this",
    contexts: ["selection"],
  });
  chrome.contextMenus.create({
    id: "museon-ask",
    title: "MUSEON: Ask about this",
    contexts: ["selection"],
  });
  chrome.contextMenus.create({
    id: "museon-capture-page",
    title: "MUSEON: Capture page",
    contexts: ["page"],
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  const payload = {
    type: "extension_capture",
    action: info.menuItemId.replace("museon-", ""),
    text: info.selectionText || "",
    url: tab.url || "",
    title: tab.title || "",
    timestamp: new Date().toISOString(),
  };

  sendToGateway(payload);
});

// ── Message from Content Script / Popup ──

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "capture_selection") {
    sendToGateway({
      type: "extension_capture",
      action: "remember",
      text: message.text,
      url: message.url,
      title: message.title,
      timestamp: new Date().toISOString(),
    });
    sendResponse({ success: true });
  } else if (message.type === "ask_museon") {
    sendToGateway({
      type: "extension_command",
      action: "ask",
      query: message.query,
      context: message.context || "",
      timestamp: new Date().toISOString(),
    });
    sendResponse({ success: true });
  } else if (message.type === "get_status") {
    sendResponse({
      connected: ws && ws.readyState === WebSocket.OPEN,
    });
  }
  return true;
});

// ── Init ──

connect();
