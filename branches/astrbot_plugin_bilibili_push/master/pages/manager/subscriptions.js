import {
  bindDataset,
  emptyState,
  escapeAttribute,
  escapeHtml,
  icon,
  placeholderFace,
} from "./utils.js?v=manager-multitype-ai";
import {
  refreshTargetDetail,
  renderTargetDetail,
  targetBindingFields,
  targetIdFromForm,
  targetShortLabel,
} from "./target_binding.js?v=manager-target-offset";
import {
  bindIdentityLookup,
  createIdentityFields,
} from "./subscription_identity.js?v=manager-target-offset";

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

export function renderSubscriptionCards(panel, subscriptions, targets, filters, actions, editor, deleteConfirm, pagination = {}) {
  const filtered = filterSubscriptions(subscriptions, filters);
  const cardItems = groupSubscriptionCards(filtered);
  const enabledCount = filtered.filter((sub) => sub.enabled).length;
  const totalPages = Math.max(1, Math.ceil(cardItems.length / PAGE_SIZE));
  const page = clamp(Number(pagination.page || 1), 1, totalPages);
  const pageItems = cardItems.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  panel.innerHTML = `
    <section class="subscription-summary">
      <div>
        <h2>订阅卡片</h2>
        <p>当前匹配 ${escapeHtml(cardItems.length)} 张卡片，包含 ${escapeHtml(filtered.length)} 个订阅，启用 ${escapeHtml(enabledCount)} 个。</p>
      </div>
      <div class="subscription-summary-badges">
        ${summaryBadge("动态", filtered.filter((sub) => sub.sub_type === "dynamic").length)}
        ${summaryBadge("直播", filtered.filter((sub) => sub.sub_type === "live").length)}
        <button class="ghost-button" type="button" data-create-subscription="1">新增订阅</button>
      </div>
    </section>
    <section class="subscription-card-grid">
      ${pageItems.length ? pageItems.map((sub) => subscriptionCard(sub, targets)).join("") : emptyState("没有匹配的订阅")}
    </section>
    ${paginationBar(page, totalPages, filtered.length)}
    ${editor ? `<div class="manager-modal-backdrop">${editorForm(editor, targets)}</div>` : ""}
    ${deleteConfirm ? deleteModal(deleteConfirm.item || deleteConfirm, targets) : ""}
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
    form.querySelectorAll("[name='sub_types']").forEach((input) => {
      input.addEventListener("change", () => {
        if (!selectedTypes(form).length) {
          input.checked = true;
        }
        updateCategoryGroups(form);
        updatePreviewBadges(form);
      });
    });
    form.querySelectorAll("[name='target_platform'], [name='target_message_type'], [name='target_session_id']").forEach((input) => {
      input.addEventListener("change", () => refreshTargetDetail(form, targets));
      input.addEventListener("input", () => refreshTargetDetail(form, targets));
    });
    bindIdentityLookup(form, actions.onLookupUser);
  }
}

export function groupSubscriptionEditorItem(subscriptions, item) {
  const base = item || {};
  const peers = subscriptions.filter(
    (sub) => String(sub.uid) === String(base.uid) && String(sub.target_id) === String(base.target_id),
  );
  const subTypes = peers.length ? peers.map((sub) => sub.sub_type) : [base.sub_type || "dynamic"];
  const categories = {};
  for (const sub of peers) {
    categories[sub.sub_type] = sub.categories || defaultCategories(sub.sub_type);
  }
  if (!peers.length && base.sub_type) {
    categories[base.sub_type] = base.categories || defaultCategories(base.sub_type);
  }
  return {
    ...base,
    sub_types: uniqueTypes(subTypes),
    categories_by_type: categories,
  };
}

function filterSubscriptions(subscriptions, filters) {
  return subscriptions.filter((sub) => {
    const labels = [...(sub.categories || []), ...(sub.tags || [])].join(" ");
    const haystack = `${sub.uid} ${sub.username} ${sub.target_id} ${labels}`.toLowerCase();
    const typeMatched = filters.type === "all" || sub.sub_type === filters.type;
    return typeMatched && (!filters.query || haystack.includes(filters.query));
  });
}

function groupSubscriptionCards(subscriptions) {
  const groups = new Map();
  for (const sub of subscriptions) {
    const key = `${sub.uid || ""}\u0000${sub.target_id || ""}`;
    const current = groups.get(key);
    if (!current) {
      groups.set(key, {
        ...sub,
        sub_types: uniqueTypes([sub.sub_type]),
        subscriptions: [sub],
      });
      continue;
    }
    current.subscriptions.push(sub);
    current.sub_types = uniqueTypes([...current.sub_types, sub.sub_type]);
    current.enabled = current.subscriptions.some((item) => item.enabled);
    current.is_live = current.subscriptions.some((item) => item.is_live);
    if (!current.face && sub.face) {
      current.face = sub.face;
    }
    if (!current.username && sub.username) {
      current.username = sub.username;
    }
  }
  return Array.from(groups.values());
}

function subscriptionCard(sub, targets) {
  const subTypes = uniqueTypes(sub.sub_types || [sub.sub_type || "dynamic"]);
  const primaryType = primarySubType(subTypes);
  return `
    <article class="subscription-card ${sub.enabled ? "" : "is-disabled"}">
      <div class="subscription-media">
        <img src="${escapeAttribute(sub.face || NO_FACE)}" alt="" onerror="this.src='${NO_FACE}'" />
        <div class="subscription-card-badges">
          ${mediaBadges(subTypes)}
        </div>
        <div class="card-icon-actions">
          <button class="icon-button" type="button" data-edit="1"
            data-uid="${escapeAttribute(sub.uid)}" data-sub-type="${escapeAttribute(primaryType)}"
            data-sub-types="${escapeAttribute(subTypes.join(","))}"
            data-target-id="${escapeAttribute(sub.target_id)}" aria-label="编辑订阅">${icon("settings")}</button>
          <button class="icon-button danger" type="button" data-delete="1"
            data-uid="${escapeAttribute(sub.uid)}" data-sub-type="${escapeAttribute(primaryType)}"
            data-sub-types="${escapeAttribute(subTypes.join(","))}"
            data-target-id="${escapeAttribute(sub.target_id)}" aria-label="删除订阅">${icon("trash")}</button>
        </div>
        <div class="subscription-media-overlay">
          <h2>${escapeHtml(sub.username || "未命名 UP 主")}</h2>
          <p>${escapeHtml(targetShortLabel(sub.target_id, targets))}</p>
          <p>UID: ${escapeHtml(sub.uid || "-")}</p>
        </div>
      </div>
    </article>
  `;
}

function editorForm(editor, targets = []) {
  const item = editor.item || {};
  const isCreate = editor.mode === "create";
  const subTypes = uniqueTypes(item.sub_types || [item.sub_type || "dynamic"]);
  const categories = item.categories_by_type || { [item.sub_type || "dynamic"]: item.categories };
  return `
    <form class="subscription-editor" id="subscriptionEditorForm" role="dialog" aria-modal="true">
      <input type="hidden" name="mode" value="${escapeAttribute(editor.mode || "create")}" />
      <input type="hidden" name="original_uid" value="${escapeAttribute(item.original_uid || item.uid || "")}" />
      <input type="hidden" name="original_sub_type" value="${escapeAttribute(item.original_sub_type || item.sub_type || "")}" />
      <input type="hidden" name="original_target_id" value="${escapeAttribute(item.original_target_id || item.target_id || "")}" />
      ${isCreate ? "" : `<input type="hidden" name="target_id" value="${escapeAttribute(item.target_id || "")}" />`}
      ${isCreate ? "" : `<input type="hidden" name="uid" value="${escapeAttribute(item.uid || "")}" />`}
      ${isCreate ? "" : `<input type="hidden" name="username" value="${escapeAttribute(item.username || "")}" />`}
      <div class="editor-heading">
        <div>
          <h2>${editor.mode === "edit" ? "编辑订阅" : "新增订阅"}</h2>
          <p>${isCreate ? "填写 UID 后选择订阅类型和通知类别。" : "卡片已包含 UID 与 UP 主信息，这里只调整类型、通知类别、标签和启用状态。"}</p>
        </div>
        <button class="ghost-button" type="button" data-cancel-subscription="1">取消</button>
      </div>
      <div class="subscription-editor-layout">
        ${editorPreview(item, editor.mode, subTypes, targets)}
        <div class="subscription-editor-fields">
          ${isCreate ? createIdentityFields(item) : ""}
          <section class="type-panel">
            <div>
              <h3>订阅类型</h3>
              <p>动态与直播可以同时选中，保存时会按类型分别写入。</p>
            </div>
            ${typeControls(subTypes)}
          </section>
          <section class="category-panel">
            <div>
              <h3>通知类别</h3>
              <p>同时选择两种类型时，下方会分别显示动态与直播的通知类别。</p>
            </div>
            <div class="category-options">
              ${categoryGroups(subTypes, categories)}
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

function typeControls(values) {
  const selected = new Set(values || ["dynamic"]);
  return `
    <div class="type-switch">
      ${typeChip("dynamic", "动态", selected)}
      ${typeChip("live", "直播", selected)}
    </div>
  `;
}

function typeChip(value, label, selected) {
  return `
    <label class="type-chip ${value}">
      <input type="checkbox" name="sub_types" value="${escapeAttribute(value)}" ${selected.has(value) ? "checked" : ""} />
      <span>${escapeHtml(label)}</span>
    </label>
  `;
}

function editorPreview(item, mode, subTypes, targets) {
  const isCreate = mode === "create";
  return `
    <aside class="subscription-editor-side">
      <div class="subscription-editor-preview">
        <img data-preview-face="1" src="${escapeAttribute(item.face || NO_FACE)}" alt="" onerror="this.src='${NO_FACE}'" />
        <div class="subscription-card-badges">
          ${mediaBadges(subTypes)}
        </div>
        <span class="editor-preview-action">${mode === "edit" ? "EDIT" : "ADD"}</span>
        <div class="subscription-media-overlay">
          <h2 data-preview-username="1">${escapeHtml(item.username || "待选择 UP 主")}</h2>
          <p data-preview-uid="1">UID: ${escapeHtml(item.uid || "-")}</p>
        </div>
      </div>
      ${isCreate ? targetBindingFields(item, targets) : renderTargetDetail(item.target_id || "", targets)}
    </aside>
  `;
}

function deleteModal(sub, targets) {
  const subTypes = uniqueTypes(sub.sub_types || [sub.sub_type || "dynamic"]);
  const primaryType = primarySubType(subTypes);
  const targetText = targetShortLabel(sub.target_id, targets);
  return `
    <div class="manager-modal-backdrop">
      <section class="manager-modal confirm-modal" role="dialog" aria-modal="true" aria-label="删除订阅">
        <div class="subscription-editor-preview confirm-preview">
          <img src="${escapeAttribute(sub.face || NO_FACE)}" alt="" onerror="this.src='${NO_FACE}'" />
          <div class="subscription-card-badges">
            ${mediaBadges(subTypes)}
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
            <p>确认删除 ${escapeHtml(sub.username || sub.uid || "未命名 UP 主")} 的 ${escapeHtml(typeListLabel(subTypes))} 订阅？</p>
            <p class="modal-muted">会话: ${escapeHtml(targetText || sub.target_id || "-")}</p>
          </div>
          <div class="modal-actions">
            <button class="ghost-button" type="button" data-cancel-delete="1">取消</button>
            <button class="danger-button" type="button" data-confirm-delete="1"
              data-uid="${escapeAttribute(sub.uid)}" data-sub-type="${escapeAttribute(primaryType)}"
              data-sub-types="${escapeAttribute(subTypes.join(","))}"
              data-target-id="${escapeAttribute(sub.target_id)}">删除</button>
          </div>
        </div>
      </section>
    </div>
  `;
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

function categoryGroups(types, categoriesByType) {
  return uniqueTypes(types).map((type) => `
    <div class="category-group" data-category-group="${escapeAttribute(type)}">
      <div class="category-group-heading">
        ${mediaBadge(type)}
      </div>
      <div class="category-chip-row">
        ${categoryControls(type, categoriesByType?.[type] || defaultCategories(type))}
      </div>
    </div>
  `).join("");
}

function categoryControls(subType, selected) {
  const selectedSet = new Set((selected || []).map((item) => String(item)));
  return CATEGORY_OPTIONS[subType].map(([value, label]) => `
    <label class="category-chip">
      <input type="checkbox" name="categories_${escapeAttribute(subType)}" value="${escapeAttribute(value)}"
        ${selectedSet.has(String(value)) ? "checked" : ""} />
      <span>${escapeHtml(label)}</span>
    </label>
  `).join("");
}

function defaultCategories(subType) {
  return CATEGORY_OPTIONS[subType].map(([value]) => value);
}

function editorPayload(form) {
  const formData = new FormData(form);
  const subTypes = selectedTypes(form);
  const mode = formData.get("mode");
  const targetId = mode === "create"
    ? targetIdFromForm(formData)
    : String(formData.get("target_id") || "");
  return {
    mode,
    original_uid: formData.get("original_uid"),
    original_sub_type: formData.get("original_sub_type"),
    original_target_id: formData.get("original_target_id"),
    uid: formData.get("uid"),
    username: formData.get("username"),
    sub_type: subTypes[0] || "dynamic",
    sub_types: subTypes,
    target_id: targetId,
    categories: formData.getAll(`categories_${subTypes[0] || "dynamic"}`),
    categories_by_type: categoriesByType(form),
    tags: formData.get("tags"),
    enabled: formData.get("enabled") === "true",
  };
}

function updateCategoryGroups(form) {
  const container = form.querySelector(".category-options");
  if (!container) {
    return;
  }
  container.innerHTML = categoryGroups(selectedTypes(form), categoriesByType(form));
}

function updatePreviewBadges(form) {
  const badges = form.querySelector(".subscription-editor-preview .subscription-card-badges");
  if (badges) {
    badges.innerHTML = mediaBadges(selectedTypes(form));
  }
}

function categoriesByType(form) {
  const data = new FormData(form);
  return {
    dynamic: data.getAll("categories_dynamic"),
    live: data.getAll("categories_live"),
  };
}

function selectedTypes(form) {
  return Array.from(form.querySelectorAll("[name='sub_types']:checked")).map((input) => input.value);
}

function summaryBadge(label, value) {
  return `<span><strong>${escapeHtml(value)}</strong>${escapeHtml(label)}</span>`;
}

function listText(value) {
  return Array.isArray(value) ? value.join(",") : (value || "");
}

function mediaBadge(type) {
  return `<span class="media-badge ${type === "live" ? "live" : "dyn"}">${type === "live" ? "LIVE" : "DYNAMIC"}</span>`;
}

function mediaBadges(types) {
  return sortBadgeTypes(types).map(mediaBadge).join("");
}

function typeListLabel(types) {
  const labels = sortBadgeTypes(types).map((type) => type === "live" ? "直播" : "动态");
  return labels.join("和");
}

function uniqueTypes(types) {
  const values = (types || []).filter((type) => ["dynamic", "live"].includes(type));
  return [...new Set(values.length ? values : ["dynamic"])];
}

function sortBadgeTypes(types) {
  const selected = new Set(uniqueTypes(types));
  return ["live", "dynamic"].filter((type) => selected.has(type));
}

function primarySubType(types) {
  return uniqueTypes(types).includes("dynamic") ? "dynamic" : "live";
}

function clamp(value, min, max) {
  if (!Number.isFinite(value)) {
    return min;
  }
  return Math.min(max, Math.max(min, value));
}
