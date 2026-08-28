const mockState = createMockOverview();
let mockQrPollCount = 0;

export function createLocalBridge() {
  return {
    ready: async () => ({}),
    apiGet: async (endpoint, params = {}) => {
      return ok(mockState);
    },
    apiPost: async (endpoint, payload = {}) => {
      if (endpoint === "subscriptions/create") {
        const subscription = mockSubscription(payload);
        mockState.subscriptions.push(subscription);
        ensureTarget(subscription.target_id);
        refreshDiagnostics();
        return ok({ subscription: payload });
      }
      if (endpoint === "subscriptions/update") {
        const sub = findSubscription(payload, "original_");
        if (sub) {
          Object.assign(sub, mockSubscription(payload));
          ensureTarget(sub.target_id);
        }
        refreshDiagnostics();
        return ok({ subscription: sub });
      }
      if (endpoint === "subscriptions/enabled") {
        const sub = findSubscription(payload);
        if (sub) {
          sub.enabled = Boolean(payload.enabled);
        }
        refreshDiagnostics();
        return ok({ updated: true, enabled: Boolean(payload.enabled) });
      }
      if (endpoint === "subscriptions/delete") {
        mockState.subscriptions = mockState.subscriptions.filter(
          (sub) =>
            !(
              String(sub.uid) === String(payload.uid) &&
              sub.sub_type === payload.sub_type &&
              sub.target_id === payload.target_id
            ),
        );
        refreshDiagnostics();
        return ok({ removed: true });
      }
      if (endpoint === "bilibili/user") {
        return ok(mockBiliUser(payload.uid));
      }
      if (endpoint === "accounts/upsert") {
        const account = {
          uid: String(payload.uid || "10003"),
          name: payload.name || "Web Account",
          face: payload.face || "",
          valid: payload.valid !== false,
        };
        const index = mockState.accounts.findIndex((item) => item.uid === account.uid);
        if (index >= 0) {
          mockState.accounts[index] = account;
        } else {
          mockState.accounts.push(account);
        }
        refreshDiagnostics();
        return ok({ account });
      }
      if (endpoint === "accounts/delete") {
        mockState.accounts = mockState.accounts.filter(
          (account) => String(account.uid) !== String(payload.uid),
        );
        refreshDiagnostics();
        return ok({ removed: true });
      }
      if (endpoint === "accounts/valid") {
        const account = mockState.accounts.find((item) => String(item.uid) === String(payload.uid));
        if (account) {
          account.valid = Boolean(payload.valid);
        }
        refreshDiagnostics();
        return ok({ updated: true, valid: Boolean(payload.valid) });
      }
      if (endpoint === "accounts/qr/start") {
        mockQrPollCount = 0;
        return ok({
          qrcode_key: "mock-qr-key",
          image: mockQrImage(),
          status: "pending",
          message: "请使用 B 站 App 扫码登录。",
        });
      }
      if (endpoint === "accounts/qr/poll") {
        mockQrPollCount += 1;
        if (mockQrPollCount >= 4) {
          return ok({ status: "expired", message: "二维码已失效，请重新获取。" });
        }
        if (mockQrPollCount >= 2) {
          return ok({ status: "scanned", message: "已扫码，请在 B 站 App 确认。" });
        }
        return ok({ status: "pending", message: "等待扫码确认。" });
      }
      if (endpoint === "checks/live") {
        if (payload.target_id === "__all__") {
          return ok({ pushed: 2, targets: 2 });
        }
        return ok({ pushed: 1 });
      }
      return ok({ removed: true, updated: true, cleared: 1 });
    },
  };
}

function mockBiliUser(uid) {
  const known = mockState.subscriptions.find((sub) => String(sub.uid) === String(uid));
  return {
    uid: String(uid || ""),
    username: known?.username || `UP ${uid || "0000"}`,
    face: known?.face || mockFace("UP", "#0f766e"),
  };
}

function mockQrImage() {
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="240" height="240">
      <rect width="240" height="240" fill="#fff"/>
      <rect x="28" y="28" width="48" height="48" fill="#111"/>
      <rect x="164" y="28" width="48" height="48" fill="#111"/>
      <rect x="28" y="164" width="48" height="48" fill="#111"/>
      <path d="M104 40h24v24h-24zm40 24h24v24h-24zm-48 48h24v24H96zm64 8h40v24h-40zm-48 48h24v32h-24zm48-8h24v24h-24z" fill="#111"/>
    </svg>
  `;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

function ok(data) {
  return { status: "ok", data };
}

function mockFace(label, color) {
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="320" height="240">
      <rect width="320" height="240" fill="${color}"/>
      <circle cx="160" cy="92" r="44" fill="rgba(255,255,255,.86)"/>
      <rect x="86" y="146" width="148" height="72" rx="36" fill="rgba(255,255,255,.72)"/>
      <text x="160" y="224" text-anchor="middle" font-size="26" font-family="Segoe UI" font-weight="800" fill="#fff">${label}</text>
    </svg>
  `;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

function createMockOverview() {
  return {
    diagnostics: {
      subscriptions: 6,
      enabled_subscriptions: 4,
      dynamic_subscriptions: 4,
      live_subscriptions: 2,
      targets: 3,
      accounts: 2,
      valid_accounts: 1,
      pending_tasks: 2,
      check_interval: 60,
      dynamic_check_interval: 300,
      live_check_interval: 90,
      risk_cooldown_sec: 3600,
      enable_link_parser: true,
      enable_ai_tools: true,
    },
    subscriptions: [
      {
        uid: "946974",
        username: "哔哩哔哩番剧",
        sub_type: "dynamic",
        target_id: "aiocqhttp:GroupMessage:10001",
        face: mockFace("番剧", "#3b82f6"),
        is_live: false,
        categories: ["番剧", "追番"],
        tags: ["官方"],
        enabled: true,
      },
      {
        uid: "946974",
        username: "哔哩哔哩番剧",
        sub_type: "live",
        target_id: "aiocqhttp:GroupMessage:10001",
        face: mockFace("番剧", "#3b82f6"),
        is_live: false,
        categories: ["直播"],
        tags: ["官方"],
        enabled: true,
      },
      {
        uid: "19577966",
        username: "哔哩哔哩直播",
        sub_type: "live",
        target_id: "aiocqhttp:GroupMessage:10001",
        face: mockFace("直播", "#ef476f"),
        is_live: false,
        categories: ["直播"],
        tags: ["官方"],
        enabled: false,
      },
      {
        uid: "3546653759015534",
        username: "哔哩哔哩纪录片",
        sub_type: "dynamic",
        target_id: "aiocqhttp:GroupMessage:10001",
        face: mockFace("纪录", "#8b5cf6"),
        is_live: false,
        categories: ["纪录片"],
        tags: ["更新"],
        enabled: true,
      },
      {
        uid: "3537115311840851",
        username: "国创动画作品发布",
        sub_type: "dynamic",
        target_id: "aiocqhttp:GroupMessage:10002",
        face: mockFace("国创", "#f97316"),
        is_live: false,
        categories: ["国创"],
        tags: ["作品"],
        enabled: true,
      },
      {
        uid: "672328094",
        username: "哔哩哔哩电竞",
        sub_type: "live",
        target_id: "aiocqhttp:GroupMessage:10002",
        face: mockFace("电竞", "#16a34a"),
        is_live: true,
        categories: ["电竞"],
        tags: ["赛事"],
        enabled: true,
      },
      {
        uid: "5970160",
        username: "哔哩哔哩漫画",
        sub_type: "dynamic",
        target_id: "aiocqhttp:GroupMessage:10003",
        face: mockFace("漫画", "#64748b"),
        is_live: false,
        categories: ["漫画"],
        tags: ["停用"],
        enabled: false,
      },
    ],
    targets: [
      mockTarget("aiocqhttp:GroupMessage:10001"),
      mockTarget("aiocqhttp:GroupMessage:10002"),
      mockTarget("aiocqhttp:GroupMessage:10003"),
    ],
    accounts: [
      { uid: "10001", name: "Bili Account", face: "", valid: true },
      { uid: "10002", name: "Backup Account", face: "", valid: false },
    ],
    pending_tasks: [
      {
        task_id: "bili1a2b3c4d",
        kind: "up_candidates",
        workflow: "add_subscription",
        origin: "aiocqhttp:GroupMessage:10001",
        candidate_count: 3,
        expires_at: Date.now() / 1000 + 120,
      },
      {
        task_id: "bili5e6f7g8h",
        kind: "confirm_subscription",
        workflow: "remove_subscription",
        origin: "aiocqhttp:GroupMessage:10002",
        candidate_count: 1,
        expires_at: Date.now() / 1000 + 240,
      },
    ],
  };
}

function mockSubscription(payload) {
  const uid = String(payload.uid || "");
  return {
    uid,
    username: payload.username || `UP ${uid}`,
    sub_type: payload.sub_type || "dynamic",
    target_id: payload.target_id || "aiocqhttp:GroupMessage:10001",
    face: payload.face || mockFace("UP", "#0f766e"),
    is_live: Boolean(payload.is_live),
    categories: parseList(payload.categories),
    tags: parseList(payload.tags),
    enabled: payload.enabled !== false,
  };
}

function findSubscription(payload, prefix = "") {
  return mockState.subscriptions.find(
    (sub) =>
      String(sub.uid) === String(payload[`${prefix}uid`]) &&
      sub.sub_type === payload[`${prefix}sub_type`] &&
      sub.target_id === payload[`${prefix}target_id`],
  );
}

function ensureTarget(targetId) {
  if (!targetId || mockState.targets.some((target) => target.target_id === targetId)) {
    return;
  }
  mockState.targets.push(mockTarget(targetId));
}

function mockTarget(targetId) {
  return {
    target_id: targetId,
    channel: String(targetId || "").split(":", 1)[0],
    title: "",
    enabled: true,
    created_at: 0,
    updated_at: 0,
  };
}

function parseList(value) {
  if (Array.isArray(value)) {
    return value;
  }
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function refreshDiagnostics() {
  const subscriptions = mockState.subscriptions;
  const accounts = mockState.accounts;
  mockState.diagnostics.subscriptions = subscriptions.length;
  mockState.diagnostics.enabled_subscriptions = subscriptions.filter((sub) => sub.enabled).length;
  mockState.diagnostics.dynamic_subscriptions = subscriptions.filter((sub) => sub.sub_type === "dynamic").length;
  mockState.diagnostics.live_subscriptions = subscriptions.filter((sub) => sub.sub_type === "live").length;
  mockState.diagnostics.targets = mockState.targets.length;
  mockState.diagnostics.enabled_targets = mockState.targets.filter((target) => target.enabled).length;
  mockState.diagnostics.accounts = accounts.length;
  mockState.diagnostics.valid_accounts = accounts.filter((account) => account.valid).length;
}
