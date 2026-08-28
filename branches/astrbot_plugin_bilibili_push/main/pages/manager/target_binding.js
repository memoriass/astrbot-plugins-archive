import {
  escapeAttribute,
  escapeHtml,
  formatTargetId,
} from "./utils.js?v=manager-target-binding";

const COMMON_PLATFORMS = ["llonebot", "aiocqhttp"];
const KIND_LABELS = {
  GroupMessage: "QQ群",
  FriendMessage: "私聊",
};

export function targetShortLabel(targetId) {
  const parsed = parseTargetId(targetId);
  if (!parsed.id) {
    return formatTargetId(targetId) || "未绑定";
  }
  return `${targetChannel(parsed.platform)}${targetKindSuffix(parsed.kind)} ${escapeSessionId(parsed)}`;
}

export function targetDetailRows(targetId, targets = []) {
  const parsed = parseTargetId(targetId);
  const rowTarget = targets.find((target) => target.target_id === targetId);
  return [
    ["实例", parsed.platform || rowTarget?.channel || "-"],
    ["类型", KIND_LABELS[parsed.kind] || parsed.kind || "-"],
    ["号码", parsed.id ? escapeSessionId(parsed) : "-"],
  ];
}

export function targetBindingFields(item, targets = []) {
  const parsed = parseTargetId(item.target_id);
  const platforms = platformOptions(targets, parsed.platform);
  const kind = parsed.kind || "GroupMessage";
  return `
    <section class="target-binding-panel">
      <div>
        <h3>绑定目标</h3>
        <p>选择机器人实例和推送目标，保存时写入完整 AstrBot 会话。</p>
      </div>
      <label class="target-field">
        <span>绑定实例</span>
        <select name="target_platform" required>
          ${platforms.map((platform) => `
            <option value="${escapeAttribute(platform)}" ${platform === (parsed.platform || platforms[0]) ? "selected" : ""}>
              ${escapeHtml(platform)}
            </option>
          `).join("")}
        </select>
      </label>
      <div class="target-kind-switch" role="group" aria-label="目标类型">
        ${targetKindChip("GroupMessage", "群", kind)}
        ${targetKindChip("FriendMessage", "个人", kind)}
      </div>
      <label class="target-field">
        <span>QQ群号 / 个人 ID</span>
        <input name="target_session_id" type="text" value="${escapeAttribute(escapeSessionId(parsed))}"
          placeholder="例如 374274729" required />
      </label>
    </section>
  `;
}

export function targetIdFromForm(formData) {
  const platform = String(formData.get("target_platform") || "").trim();
  const kind = String(formData.get("target_message_type") || "GroupMessage").trim();
  const sessionId = String(formData.get("target_session_id") || "").trim();
  if (!platform || !kind || !sessionId) {
    return "";
  }
  return `${platform}:${kind}:${sessionId}`;
}

export function renderTargetDetail(targetId, targets = []) {
  return `
    <section class="target-detail-panel" data-target-detail="1">
      <div class="target-detail-title">
        <span>推送目标</span>
      </div>
      <dl>
        ${targetDetailRows(targetId, targets).map(([label, value]) => `
          <div>
            <dt>${escapeHtml(label)}</dt>
            <dd>${escapeHtml(value)}</dd>
          </div>
        `).join("")}
      </dl>
    </section>
  `;
}

export function refreshTargetDetail(form, targets = []) {
  const detail = form.querySelector("[data-target-detail]");
  if (!detail) {
    return;
  }
  const formData = new FormData(form);
  const targetId = formData.get("mode") === "create"
    ? targetIdFromForm(formData)
    : String(formData.get("target_id") || "");
  detail.outerHTML = renderTargetDetail(targetId, targets);
}

export function parseTargetId(targetId) {
  const parts = String(targetId || "").split(":");
  return {
    platform: parts[0] || "",
    kind: parts[1] || "",
    id: parts.slice(2).join(":"),
  };
}

function targetKindChip(value, label, selected) {
  return `
    <label class="target-kind-chip">
      <input type="radio" name="target_message_type" value="${escapeAttribute(value)}"
        ${selected === value ? "checked" : ""} />
      <span>${escapeHtml(label)}</span>
    </label>
  `;
}

function platformOptions(targets, selectedPlatform) {
  const values = new Set();
  if (selectedPlatform) {
    values.add(selectedPlatform);
  }
  let hasKnownTarget = false;
  for (const target of targets || []) {
    const parsed = parseTargetId(target.target_id);
    if (parsed.platform) {
      values.add(parsed.platform);
      hasKnownTarget = true;
    }
  }
  if (!hasKnownTarget) {
    COMMON_PLATFORMS.forEach((platform) => values.add(platform));
  }
  return Array.from(values);
}

function targetChannel(platform) {
  const value = String(platform || "").toLowerCase();
  if (value.includes("cqhttp") || value.includes("onebot") || value === "qq") {
    return "QQ";
  }
  if (value.includes("telegram") || value === "tg") {
    return "TG";
  }
  if (value.includes("wechat") || value.includes("wx")) {
    return "WX";
  }
  return platform ? platform.toUpperCase() : "会话";
}

function targetKindSuffix(kind) {
  if (kind === "GroupMessage") {
    return "群";
  }
  if (kind === "FriendMessage") {
    return "私聊";
  }
  return "会话";
}

function escapeSessionId(parsed) {
  if (parsed.kind === "GroupMessage" && parsed.id.includes("_")) {
    const parts = parsed.id.split("_").filter(Boolean);
    return parts[parts.length - 1] || parsed.id;
  }
  return parsed.id || "";
}
