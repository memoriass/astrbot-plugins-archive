export function unwrap(response) {
  if (response?.status === "ok") {
    return response.data || {};
  }
  if (response?.status === "error") {
    throw new Error(response.message || "请求失败");
  }
  return response || {};
}

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function escapeAttribute(value) {
  return escapeHtml(value);
}

export function formatTime(timestamp) {
  if (!timestamp) {
    return "-";
  }
  return new Date(timestamp * 1000).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatBytes(value) {
  const size = Number(value || 0);
  if (size >= 1024 * 1024) {
    return `${(size / 1024 / 1024).toFixed(1)} MB`;
  }
  if (size >= 1024) {
    return `${Math.round(size / 1024)} KB`;
  }
  return `${size} B`;
}

export function formatTargetId(targetId) {
  const [platform, kind, id] = String(targetId || "").split(":");
  if (!id) {
    return compactTargetId(targetId);
  }
  const channel = channelName(platform);
  const targetKind = kind === "GroupMessage" ? "群" : kind === "FriendMessage" ? "私聊" : "会话";
  return `${channel}${targetKind} ${id}`;
}

export function emptyState(text) {
  return `<div class="empty">${escapeHtml(text)}</div>`;
}

export function placeholderFace(label = "BILI") {
  const safeLabel = String(label || "BILI").slice(0, 8);
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="360" height="360" viewBox="0 0 360 360">
      <defs>
        <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stop-color="#dfffb1"/>
          <stop offset=".52" stop-color="#f8fff0"/>
          <stop offset="1" stop-color="#b7d78d"/>
        </linearGradient>
        <linearGradient id="shade" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="rgba(255,255,255,.2)"/>
          <stop offset="1" stop-color="rgba(20,25,20,.72)"/>
        </linearGradient>
      </defs>
      <rect width="360" height="360" fill="url(#bg)"/>
      <circle cx="180" cy="136" r="58" fill="rgba(255,255,255,.82)"/>
      <rect x="92" y="220" width="176" height="84" rx="42" fill="rgba(255,255,255,.62)"/>
      <path d="M42 70c54-24 88 8 138-12 56-22 92-8 138 18" fill="none" stroke="rgba(79,127,60,.28)" stroke-width="18" stroke-linecap="round"/>
      <rect width="360" height="360" fill="url(#shade)"/>
      <text x="180" y="322" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="30" font-weight="900" fill="#fff">${escapeHtml(safeLabel)}</text>
    </svg>
  `;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

export function typeBadge(value) {
  const text = value === "live" ? "直播" : "动态";
  return `<span class="badge ${escapeAttribute(value)}">${text}</span>`;
}

export function statusPill(text, ok) {
  return `<span class="pill ${ok ? "ok" : "bad"}">${escapeHtml(text)}</span>`;
}

const ICONS = {
  settings: `
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z" />
      <path d="M19.4 15a1.8 1.8 0 0 0 .36 1.98l.05.05a2.1 2.1 0 0 1-2.97 2.97l-.05-.05a1.8 1.8 0 0 0-1.98-.36 1.8 1.8 0 0 0-1.1 1.65V21a2.1 2.1 0 0 1-4.2 0v-.08a1.8 1.8 0 0 0-1.18-1.65 1.8 1.8 0 0 0-1.98.36l-.05.05a2.1 2.1 0 0 1-2.97-2.97l.05-.05a1.8 1.8 0 0 0 .36-1.98 1.8 1.8 0 0 0-1.65-1.1H3a2.1 2.1 0 0 1 0-4.2h.08a1.8 1.8 0 0 0 1.65-1.18 1.8 1.8 0 0 0-.36-1.98l-.05-.05A2.1 2.1 0 0 1 7.29 3.2l.05.05a1.8 1.8 0 0 0 1.98.36H9.4a1.8 1.8 0 0 0 1.1-1.65V2a2.1 2.1 0 0 1 4.2 0v.08a1.8 1.8 0 0 0 1.18 1.65 1.8 1.8 0 0 0 1.98-.36l.05-.05a2.1 2.1 0 0 1 2.97 2.97l-.05.05a1.8 1.8 0 0 0-.36 1.98v.08a1.8 1.8 0 0 0 1.65 1.1H22a2.1 2.1 0 0 1 0 4.2h-.08a1.8 1.8 0 0 0-1.65 1.18Z" />
    </svg>
  `,
  trash: `
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M3 6h18" />
      <path d="M8 6V4h8v2" />
      <path d="M19 6l-1 15H6L5 6" />
      <path d="M10 11v6" />
      <path d="M14 11v6" />
    </svg>
  `,
};

export function icon(name) {
  return ICONS[name] || "";
}

export function bindDataset(root, selector, handler) {
  root.querySelectorAll(selector).forEach((button) => {
    button.addEventListener("click", () => handler(button.dataset));
  });
}

function channelName(platform = "") {
  const key = platform.toLowerCase();
  if (key.includes("cqhttp") || key === "aiohttp" || key === "qq") {
    return "QQ";
  }
  if (key.includes("telegram") || key === "tg") {
    return "TG";
  }
  if (key.includes("wechat") || key.includes("wx")) {
    return "WX";
  }
  return platform.toUpperCase() || "群";
}

function compactTargetId(targetId) {
  const value = String(targetId || "");
  return value.length > 24 ? `${value.slice(0, 12)}...${value.slice(-8)}` : value;
}
