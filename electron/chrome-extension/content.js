/**
 * MUSEON Chrome Extension - Content Script
 * Injected into web pages for text selection and skill triggering.
 */

(function () {
  "use strict";

  // Avoid double injection
  if (window.__museon_injected) return;
  window.__museon_injected = true;

  // ── Selection Capture ──

  let selectionTooltip = null;

  function createTooltip() {
    const tooltip = document.createElement("div");
    tooltip.id = "museon-tooltip";
    tooltip.style.cssText = `
      position: absolute;
      z-index: 999999;
      background: #1a1a2e;
      color: #e0e0ff;
      border: 1px solid #4a4a8a;
      border-radius: 8px;
      padding: 4px 8px;
      font-size: 12px;
      font-family: -apple-system, BlinkMacSystemFont, sans-serif;
      box-shadow: 0 4px 12px rgba(0,0,0,0.3);
      cursor: pointer;
      display: none;
      user-select: none;
    `;
    tooltip.innerHTML = `
      <span class="museon-btn" data-action="remember" title="Remember">&#128218;</span>
      <span class="museon-btn" data-action="ask" title="Ask MUSEON" style="margin-left:6px">&#129302;</span>
    `;

    // Button hover effect
    tooltip.querySelectorAll(".museon-btn").forEach((btn) => {
      btn.style.cssText = "cursor:pointer;padding:2px 4px;border-radius:4px;";
      btn.addEventListener("mouseenter", () => (btn.style.background = "#2a2a4e"));
      btn.addEventListener("mouseleave", () => (btn.style.background = "transparent"));
    });

    document.body.appendChild(tooltip);
    return tooltip;
  }

  function showTooltip(x, y) {
    if (!selectionTooltip) selectionTooltip = createTooltip();
    selectionTooltip.style.left = x + "px";
    selectionTooltip.style.top = y + "px";
    selectionTooltip.style.display = "block";
  }

  function hideTooltip() {
    if (selectionTooltip) selectionTooltip.style.display = "none";
  }

  // ── Event Listeners ──

  document.addEventListener("mouseup", (e) => {
    const selection = window.getSelection();
    const text = selection.toString().trim();

    if (text.length > 5 && text.length < 5000) {
      const rect = selection.getRangeAt(0).getBoundingClientRect();
      showTooltip(
        rect.left + window.scrollX,
        rect.bottom + window.scrollY + 5
      );
    } else {
      hideTooltip();
    }
  });

  document.addEventListener("mousedown", (e) => {
    if (selectionTooltip && !selectionTooltip.contains(e.target)) {
      hideTooltip();
    }
  });

  // Handle tooltip button clicks
  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".museon-btn");
    if (!btn) return;

    const action = btn.dataset.action;
    const text = window.getSelection().toString().trim();

    if (!text) return;

    chrome.runtime.sendMessage({
      type: action === "remember" ? "capture_selection" : "ask_museon",
      text: text,
      query: text,
      url: window.location.href,
      title: document.title,
    });

    hideTooltip();

    // Brief visual feedback
    btn.style.background = "#4a8";
    setTimeout(() => (btn.style.background = "transparent"), 300);
  });

  // ── Keyboard Shortcut ──

  document.addEventListener("keydown", (e) => {
    // Cmd/Ctrl + Shift + M = Remember selection
    if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key === "m") {
      const text = window.getSelection().toString().trim();
      if (text) {
        chrome.runtime.sendMessage({
          type: "capture_selection",
          text: text,
          url: window.location.href,
          title: document.title,
        });
        e.preventDefault();
      }
    }
  });
})();
