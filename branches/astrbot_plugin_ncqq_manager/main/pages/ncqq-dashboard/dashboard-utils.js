(function () {
  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function fmtAge(seconds) {
    const value = Number(seconds || 0);
    if (value < 60) return `${value}s`;
    if (value < 3600) return `${Math.floor(value / 60)}m`;
    return `${Math.floor(value / 3600)}h`;
  }

  function maskQQ(value) {
    const text = String(value || "").trim();
    if (text.length < 7) return text || "-";
    return `${text.slice(0, 3)}****${text.slice(-3)}`;
  }

  function shortUrl(value) {
    const text = String(value || "").trim();
    if (!text || text === "-") return "-";
    try {
      return new URL(text).host;
    } catch {
      return text.replace(/^https?:\/\//, "").replace(/^wss?:\/\//, "");
    }
  }

  function instanceState(item) {
    if (item.bot_online) return { key: "online", text: "在线" };
    if (item.running) return { key: "warn", text: "心跳丢失" };
    return { key: "offline", text: "离线" };
  }

  function managerState(health) {
    const warn = Boolean((health.degraded_reasons || []).length);
    return health.ok ? (warn ? "warn" : "online") : "offline";
  }

  function empty(text, error) {
    return `<div class="empty${error ? " error" : ""}">${escapeHtml(text)}</div>`;
  }

  function assetUrl(path) {
    const url = new URL(path, window.location.href);
    const pageParams = new URLSearchParams(window.location.search);
    ["asset_token", "theme"].forEach((key) => {
      const value = pageParams.get(key);
      if (value && !url.searchParams.has(key)) {
        url.searchParams.set(key, value);
      }
    });
    return url.href;
  }

  window.NcqqDashboardUtils = {
    assetUrl,
    empty,
    escapeHtml,
    fmtAge,
    instanceState,
    managerState,
    maskQQ,
    shortUrl,
  };
})();
