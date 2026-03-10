/**
 * MUSEON Chrome Extension - Popup Script
 */

document.addEventListener("DOMContentLoaded", () => {
  const statusDot = document.getElementById("status-dot");
  const queryInput = document.getElementById("query-input");
  const askBtn = document.getElementById("ask-btn");

  // Check connection status
  chrome.runtime.sendMessage({ type: "get_status" }, (response) => {
    if (response && response.connected) {
      statusDot.classList.add("connected");
    }
  });

  // Ask button
  askBtn.addEventListener("click", () => {
    const query = queryInput.value.trim();
    if (!query) return;

    chrome.runtime.sendMessage({
      type: "ask_museon",
      query: query,
      context: "",
    });

    queryInput.value = "";
    askBtn.textContent = "Sent!";
    setTimeout(() => (askBtn.textContent = "Ask"), 1000);
  });

  // Enter key
  queryInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") askBtn.click();
  });

  // Capture page
  document.getElementById("btn-capture").addEventListener("click", () => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (!tabs[0]) return;
      chrome.runtime.sendMessage({
        type: "capture_selection",
        text: "",
        url: tabs[0].url,
        title: tabs[0].title,
      });
    });
  });

  // Explore
  document.getElementById("btn-explore").addEventListener("click", () => {
    chrome.runtime.sendMessage({
      type: "ask_museon",
      query: "/explore",
      context: "triggered from extension",
    });
  });

  // Skills
  document.getElementById("btn-skills").addEventListener("click", () => {
    chrome.tabs.create({ url: "http://127.0.0.1:8765/dashboard" });
  });

  // System status
  document.getElementById("btn-status").addEventListener("click", () => {
    chrome.tabs.create({ url: "http://127.0.0.1:8765/api/health" });
  });
});
