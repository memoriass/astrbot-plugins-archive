import {
  bindDataset,
  emptyState,
  escapeAttribute,
  escapeHtml,
  icon,
  placeholderFace,
} from "./utils.js?v=manager-live-modal";

const NO_FACE = placeholderFace("BILI");

export function renderAccountManager(panel, accounts, actions, editor, deleteConfirm) {
  panel.innerHTML = `
    <section class="account-summary">
      <div>
        <h2>账号管理</h2>
        <p>当前 ${escapeHtml(accounts.length)} 个账号，Cookie 只允许写入或替换，不会在页面回显。</p>
      </div>
      <button class="ghost-button" type="button" data-create-account="1">新增账号</button>
    </section>
    ${accounts.length ? `<div class="account-grid">${accounts.map(accountCard).join("")}</div>` : emptyState("暂无登录账号")}
    ${editor ? `<div class="manager-modal-backdrop">${editorForm(editor)}</div>` : ""}
    ${deleteConfirm ? deleteModal(deleteConfirm.item || deleteConfirm) : ""}
  `;

  panel.querySelector("[data-create-account]").addEventListener("click", actions.onCreate);
  bindDataset(panel, "[data-edit-account]", actions.onEdit);
  bindDataset(panel, "[data-delete-account]", actions.onDelete);
  bindDataset(panel, "[data-confirm-delete-account]", actions.onConfirmDelete);
  bindDataset(panel, "[data-cancel-delete-account]", actions.onCancelDelete);
  const form = panel.querySelector("#accountEditorForm");
  if (form) {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      actions.onSubmit(Object.fromEntries(new FormData(form)));
    });
    panel.querySelector("[data-cancel-account]").addEventListener("click", actions.onCancel);
  }
}

function accountCard(account) {
  return `
    <article class="account-card">
      <div class="account-media">
        <img src="${escapeAttribute(account.face || NO_FACE)}" alt="" onerror="this.src='${NO_FACE}'" />
        <div class="card-icon-actions">
          <button class="icon-button" type="button" data-edit-account="1"
            data-uid="${escapeAttribute(account.uid)}" aria-label="编辑账号">${icon("settings")}</button>
          <button class="icon-button danger" type="button" data-delete-account="1"
            data-uid="${escapeAttribute(account.uid)}" aria-label="删除账号">${icon("trash")}</button>
        </div>
        <div class="account-media-overlay">
          <h2>${escapeHtml(account.name || "Bilibili 账号")}</h2>
          <p>UID: ${escapeHtml(account.uid || "-")}</p>
          ${account.status_label ? `<p>${escapeHtml(account.status_label)}</p>` : ""}
        </div>
      </div>
    </article>
  `;
}

function editorForm(editor) {
  const item = editor.item || {};
  return `
    <form class="account-editor" id="accountEditorForm" role="dialog" aria-modal="true">
      <div class="editor-heading">
        <div>
          <h2>${editor.mode === "edit" ? "编辑账号" : "新增账号"}</h2>
          <p>Cookie 支持 JSON 或浏览器 Cookie 字符串；编辑时留空表示不替换。</p>
        </div>
        <button class="ghost-button" type="button" data-cancel-account="1">取消</button>
      </div>
      <div class="account-editor-layout">
        <div class="account-editor-preview">
          <img src="${escapeAttribute(item.face || NO_FACE)}" alt="" onerror="this.src='${NO_FACE}'" />
          <div class="account-media-overlay">
            <h2>${escapeHtml(item.name || "Bilibili 账号")}</h2>
            <p>UID: ${escapeHtml(item.uid || "-")}</p>
          </div>
        </div>
        <div class="account-editor-fields">
          <div class="editor-grid">
            ${field("UID", "uid", item.uid || "", "text", editor.mode !== "create")}
            ${field("名称", "name", item.name || "", "text", false)}
            ${field("头像 URL", "face", item.face || "", "url", false)}
          </div>
          <label class="cookie-field">
            <span>Cookie</span>
            <textarea name="cookies_text" rows="4" placeholder="SESSDATA=...; bili_jct=...; DedeUserID=..."></textarea>
          </label>
        </div>
      </div>
      <label class="editor-check">
        <input type="checkbox" name="valid" value="true" ${item.valid === false ? "" : "checked"} />
        标记为有效
      </label>
      <div class="editor-actions">
        <button class="ghost-button" type="submit">${editor.mode === "edit" ? "保存账号" : "创建账号"}</button>
      </div>
    </form>
  `;
}

function deleteModal(account) {
  return `
    <div class="manager-modal-backdrop">
      <section class="manager-modal confirm-modal" role="dialog" aria-modal="true" aria-label="删除账号">
        <div class="account-editor-preview confirm-preview">
          <img src="${escapeAttribute(account.face || NO_FACE)}" alt="" onerror="this.src='${NO_FACE}'" />
          <span class="editor-preview-action">DELETE</span>
          <div class="account-media-overlay">
            <h2>${escapeHtml(account.name || "Bilibili 账号")}</h2>
            <p>UID: ${escapeHtml(account.uid || "-")}</p>
          </div>
        </div>
        <div class="confirm-copy">
          <div>
            <h2>删除账号</h2>
            <p>确认删除 ${escapeHtml(account.name || "Bilibili 账号")}？</p>
            <p class="modal-muted">UID: ${escapeHtml(account.uid || "-")}</p>
          </div>
          <div class="modal-actions">
            <button class="ghost-button" type="button" data-cancel-delete-account="1">取消</button>
            <button class="danger-button" type="button" data-confirm-delete-account="1"
              data-uid="${escapeAttribute(account.uid)}">删除</button>
          </div>
        </div>
      </section>
    </div>
  `;
}

function field(label, name, value, type, readonly) {
  return `
    <label>
      <span>${escapeHtml(label)}</span>
      <input name="${escapeAttribute(name)}" type="${escapeAttribute(type)}"
        value="${escapeAttribute(value)}" ${readonly ? "readonly" : ""} />
    </label>
  `;
}
