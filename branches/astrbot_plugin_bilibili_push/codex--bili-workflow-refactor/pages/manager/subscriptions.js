import {
  bindDataset,
  emptyState,
  escapeAttribute,
  escapeHtml,
  icon,
  placeholderFace,
} from "./utils.js?v=manager-live-modal";

const NO_FACE = placeholderFace("UP");
const CATEGORY_OPTIONS = {
  dynamic: [
    [1, "一般动态"],
    [2, "专栏文章"],
    [3, "视频"],
    [4, "纯文字"],
    [5, "转发"],
    [6, "直播推送"],
  ],
  live: [
    [1, "开播提醒"],
    [2, "标题更新"],
    [3, "下播提醒"],
  ],
};
const PAGE_SIZE = 12;

export function renderSubscriptionCards(
  panel,
  subscriptions,
  filters,
  actions,
  editor,
  deleteConfirm,
  pagination = {},
) {
  const filtered = filterSubscriptions(subscriptions, filters);
  const enabledCount = filtered.filter((sub) => sub.enabled).length;
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const page = clamp(Number(pagination.page || 1), 1, totalPages);
  const pageItems = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  panel.innerHTML = `
    <section class="subscription-summary">
      <div>
        <h2>订阅卡片</h2>
        <p>当前匹配 ${escapeHtml(filtered.length)} 个订阅，启用 ${escapeHtml(enabledCount)} 个。</p>
      </div>
      <div class="subscription-summary-badges">
        ${summaryBadge("动态", filtered.filter((sub) => sub.sub_type === "dynamic").length)}
        ${summaryBadge("直播", filtered.filter((sub) => sub.sub_type === "live").length)}
        <button class="ghost-button" type="button" data-create-subscription="1">新增订阅</button>
      </div>
    </section>
    <section class="subscription-card-grid">
      ${pageItems.length ? pageItems.map(subscriptionCard).join("") : emptyState("没有匹配的订阅")}
    </section>
    ${paginationBar(page, totalPages, filtered.length)}
    ${editor ? `<div class="manager-modal-backdrop">${editorForm(editor)}</div>` : ""}
    ${deleteConfirm ? deleteModal(deleteConfirm.item || deleteConfirm) : ""}
  `;
  panel.querySelector("[data-create-subscription]").addEventListener("click", actions.onCreate);
  bindDataset(panel, "[data-edit]", actions.onEdit);
  bindDataset(panel, "[data-delete]", actions.onDelete);
  bindDataset(panel, "[data-confirm-delete]", actions.onConfirmDelete);
  bindDataset(panel, "[data-cancel-delete]", actions.onCancelDelete);
  bindDataset(panel, "[data-page]", actions.onPage);
  const form = panel.querySelector("#subscriptionEditorForm");
  if (form) {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      actions.onSubmit(editorPayload(form));
    });
    panel.querySelector("[data-cancel-subscription]").addEventListener("click", actions.onCancel);
    form.querySelectorAll("[name='sub_type']").forEach((input) => {
      input.addEventListener("change", (event) => {
        const type = event.target.value;
        form.querySelector(".category-options").innerHTML = categoryControls(
          type,
          defaultCategories(type),
        );
        updatePreviewType(form, type);
      });
    });
  }
}

function updatePreviewType(form, type) {
  const badge = form.querySelector(".subscription-editor-preview .media-badge");
  if (!badge) {
    return;
  }
  badge.className = `media-badge ${type === "live" ? "live" : "dyn"}`;
  badge.textContent = type === "live" ? "LIVE" : "DYNAMIC";
}

function paginationBar(page, totalPages, total) {
  return `
    <nav class="subscription-pagination" aria-label="订阅分页">
      <button class="ghost-button" type="button" data-page="${escapeAttribute(page - 1)}" ${page <= 1 ? "disabled" : ""}>上一页</button>
      <span>第 ${escapeHtml(page)} / ${escapeHtml(totalPages)} 页 · 共 ${escapeHtml(total)} 个</span>
      <button class="ghost-button" type="button" data-page="${escapeAttribute(page + 1)}" ${page >= totalPages ? "disabled" : ""}>下一页</button>
    </nav>
  `;
}

function clamp(value, min, max) {
  if (!Number.isFinite(value)) {
    return min;
  }
  return Math.min(max, Math.max(min, value));
}

function filterSubscriptions(subscriptions, filters) {
  return subscriptions.filter((sub) => {
    const labels = [...(sub.categories || []), ...(sub.tags || [])].join(" ");
    const haystack = `${sub.uid} ${sub.username} ${sub.target_id} ${labels}`.toLowerCase();
    const typeMatched = filters.type === "all" || sub.sub_type === filters.type;
    return typeMatched && (!filters.query || haystack.includes(filters.query));
  });
}

function subscriptionCard(sub) {
  return `
    <article class="subscription-card ${sub.enabled ? "" : "is-disabled"}">
      <div class="subscription-media">
        <img src="${escapeAttribute(sub.face || NO_FACE)}" alt="" onerror="this.src='${NO_FACE}'" />
        <div class="subscription-card-badges">
          ${sub.sub_type === "live" ? `<span class="media-badge live">LIVE</span>` : ""}
          ${sub.sub_type === "dynamic" ? `<span class="media-badge dyn">DYNAMIC</span>` : ""}
        </div>
        <div class="card-icon-actions">
          <button class="icon-button" type="button" data-edit="1"
            data-uid="${escapeAttribute(sub.uid)}" data-sub-type="${escapeAttribute(sub.sub_type)}"
            data-target-id="${escapeAttribute(sub.target_id)}" aria-label="编辑订阅">${icon("settings")}</button>
          <button class="icon-button danger" type="button" data-delete="1"
            data-uid="${escapeAttribute(sub.uid)}" data-sub-type="${escapeAttribute(sub.sub_type)}"
            data-target-id="${escapeAttribute(sub.target_id)}" aria-label="删除订阅">${icon("trash")}</button>
        </div>
        <div class="subscription-media-overlay">
          <h2>${escapeHtml(sub.username || "未命名 UP 主")}</h2>
          <p>UID: ${escapeHtml(sub.uid || "-")}</p>
        </div>
      </div>
    </article>
  `;
}

function editorForm(editor) {
  const item = editor.item || {};
  const subType = item.sub_type || "dynamic";
  const isCreate = editor.mode === "create";
  return `
    <form class="subscription-editor" id="subscriptionEditorForm" role="dialog" aria-modal="true">
      <input type="hidden" name="mode" value="${escapeAttribute(editor.mode || "create")}" />
      <input type="hidden" name="original_uid" value="${escapeAttribute(item.original_uid || item.uid || "")}" />
      <input type="hidden" name="original_sub_type" value="${escapeAttribute(item.original_sub_type || item.sub_type || "")}" />
      <input type="hidden" name="original_target_id" value="${escapeAttribute(item.original_target_id || item.target_id || "")}" />
      <input type="hidden" name="target_id" value="${escapeAttribute(item.target_id || "")}" />
      ${isCreate ? "" : `<input type="hidden" name="uid" value="${escapeAttribute(item.uid || "")}" />`}
      ${isCreate ? "" : `<input type="hidden" name="username" value="${escapeAttribute(item.username || "")}" />`}
      <div class="editor-heading">
        <div>
          <h2>${editor.mode === "edit" ? "编辑订阅" : "新增订阅"}</h2>
          <p>${isCreate ? "填写 UID 后选择订阅类型和通知类别；Cookie 和账号不在这里处理。" : "左侧卡片已包含 UID 和 UP 主信息，这里只调整订阅类型、通知类别和标签。"}</p>
        </div>
        <button class="ghost-button" type="button" data-cancel-subscription="1">取消</button>
      </div>
      <div class="subscription-editor-layout">
        ${editorPreview(item, editor.mode)}
        <div class="subscription-editor-fields">
          ${isCreate ? createIdentityFields(item) : ""}
          <section class="type-panel">
            <div>
              <h3>订阅类型</h3>
              <p>动态与直播可在这里快速切换，保存后会更新当前订阅记录。</p>
            </div>
            ${typeControls(subType)}
          </section>
          <section class="category-panel">
            <div>
              <h3>通知类别</h3>
              <p>默认已按当前类型选中常用类别，可按会话需求调整。</p>
            </div>
            <div class="category-options">
              ${categoryControls(subType, item.categories || defaultCategories(subType))}
            </div>
          </section>
          <label class="tag-field">
            <span>标签</span>
            <input name="tags" type="text" value="${escapeAttribute(listText(item.tags))}" placeholder="可选，多个标签用逗号分隔" />
          </label>
        </div>
      </div>
      <label class="editor-check">
        <input type="checkbox" name="enabled" value="true" ${item.enabled === false ? "" : "checked"} />
        启用订阅
      </label>
      <div class="editor-actions">
        <button class="ghost-button" type="submit">${editor.mode === "edit" ? "保存修改" : "创建订阅"}</button>
      </div>
    </form>
  `;
}

function createIdentityFields(item) {
  return `
    <div class="editor-grid">
      ${field("UID", "uid", item.uid || "", "text", true)}
      ${field("UP 主", "username", item.username || "", "text", false)}
    </div>
  `;
}

function typeControls(value) {
  return `
    <div class="type-switch">
      ${typeChip("dynamic", "动态", value)}
      ${typeChip("live", "直播", value)}
    </div>
  `;
}

function typeChip(value, label, current) {
  return `
    <label class="type-chip ${value}">
      <input type="radio" name="sub_type" value="${escapeAttribute(value)}" ${current === value ? "checked" : ""} />
      <span>${escapeHtml(label)}</span>
    </label>
  `;
}

function editorPreview(item, mode) {
  const subType = item.sub_type || "dynamic";
  return `
    <div class="subscription-editor-preview">
      <img src="${escapeAttribute(item.face || NO_FACE)}" alt="" onerror="this.src='${NO_FACE}'" />
      <div class="subscription-card-badges">
        <span class="media-badge ${subType === "live" ? "live" : "dyn"}">${subType === "live" ? "LIVE" : "DYNAMIC"}</span>
      </div>
      <span class="editor-preview-action">${mode === "edit" ? "EDIT" : "ADD"}</span>
      <div class="subscription-media-overlay">
        <h2>${escapeHtml(item.username || "待选择 UP 主")}</h2>
        <p>UID: ${escapeHtml(item.uid || "-")}</p>
      </div>
    </div>
  `;
}

function deleteModal(sub) {
  const subType = sub.sub_type || "dynamic";
  return `
    <div class="manager-modal-backdrop">
      <section class="manager-modal confirm-modal" role="dialog" aria-modal="true" aria-label="删除订阅">
        <div class="subscription-editor-preview confirm-preview">
          <img src="${escapeAttribute(sub.face || NO_FACE)}" alt="" onerror="this.src='${NO_FACE}'" />
          <div class="subscription-card-badges">
            <span class="media-badge ${subType === "live" ? "live" : "dyn"}">${subType === "live" ? "LIVE" : "DYNAMIC"}</span>
          </div>
          <span class="editor-preview-action">DELETE</span>
          <div class="subscription-media-overlay">
            <h2>${escapeHtml(sub.username || "未命名 UP 主")}</h2>
            <p>UID: ${escapeHtml(sub.uid || "-")}</p>
          </div>
        </div>
        <div class="confirm-copy">
          <div>
            <h2>删除订阅</h2>
            <p>确认删除 ${escapeHtml(sub.username || sub.uid || "未命名 UP 主")} 的 ${escapeHtml(subType)} 订阅？</p>
            <p class="modal-muted">会话: ${escapeHtml(sub.target_id || "-")}</p>
          </div>
          <div class="modal-actions">
            <button class="ghost-button" type="button" data-cancel-delete="1">取消</button>
            <button class="danger-button" type="button" data-confirm-delete="1"
              data-uid="${escapeAttribute(sub.uid)}" data-sub-type="${escapeAttribute(subType)}"
              data-target-id="${escapeAttribute(sub.target_id)}">删除</button>
          </div>
        </div>
      </section>
    </div>
  `;
}

function field(label, name, value, type, required) {
  return `
    <label>
      <span>${escapeHtml(label)}</span>
      <input name="${escapeAttribute(name)}" type="${escapeAttribute(type)}"
        value="${escapeAttribute(value)}" ${required ? "required" : ""} />
    </label>
  `;
}

function categoryControls(subType, selected) {
  const selectedSet = new Set((selected || []).map((item) => String(item)));
  return CATEGORY_OPTIONS[subType].map(([value, label]) => `
    <label class="category-chip">
      <input type="checkbox" name="categories" value="${escapeAttribute(value)}"
        ${selectedSet.has(String(value)) ? "checked" : ""} />
      <span>${escapeHtml(label)}</span>
    </label>
  `).join("");
}

function defaultCategories(subType) {
  return CATEGORY_OPTIONS[subType].map(([value]) => value);
}

function summaryBadge(label, value) {
  return `<span><strong>${escapeHtml(value)}</strong>${escapeHtml(label)}</span>`;
}

function listText(value) {
  return Array.isArray(value) ? value.join(",") : (value || "");
}

function editorPayload(form) {
  const formData = new FormData(form);
  return {
    mode: formData.get("mode"),
    original_uid: formData.get("original_uid"),
    original_sub_type: formData.get("original_sub_type"),
    original_target_id: formData.get("original_target_id"),
    uid: formData.get("uid"),
    username: formData.get("username"),
    sub_type: formData.get("sub_type"),
    target_id: formData.get("target_id"),
    categories: formData.getAll("categories"),
    tags: formData.get("tags"),
    enabled: formData.get("enabled") === "true",
  };
}
