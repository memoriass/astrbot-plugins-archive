import {
  emptyState,
  escapeHtml,
  formatTargetId,
  formatTime,
} from "./utils.js?v=manager-multitype-ai";
import { renderAccountManager } from "./accounts.js?v=manager-account-qr";
import { pendingCandidateText, pendingSummary, pendingTitle } from "./pending_text.js?v=manager-multitype-ai";
import { renderSubscriptionCards } from "./subscriptions.js?v=manager-target-offset";

export function renderMetrics(container, diagnostics) {
  const items = [
    ["总订阅", diagnostics.subscriptions || 0],
    ["启用", diagnostics.enabled_subscriptions || 0],
    ["动态", diagnostics.dynamic_subscriptions || 0],
    ["直播", diagnostics.live_subscriptions || 0],
    ["账号", `${diagnostics.valid_accounts || 0}/${diagnostics.accounts || 0}`],
    ["待处理", diagnostics.pending_tasks || 0],
  ];
  container.innerHTML = items
    .map(([label, value]) => `
      <article class="metric">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(value)}</strong>
      </article>
    `)
    .join("");
}

export function renderTabs(activeTab) {
  document.querySelectorAll(".tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === activeTab);
  });
  document.querySelectorAll(".panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `${activeTab}Panel`);
  });
  document.getElementById("metrics").hidden = activeTab !== "overview";
  document.getElementById("subscriptionToolbar").hidden = activeTab !== "subscriptions";
}

export function renderSubscriptions(
  panel,
  subscriptions,
  targets,
  filters,
  actions,
  editor,
  deleteConfirm,
  pagination,
) {
  renderSubscriptionCards(
    panel,
    subscriptions,
    targets,
    filters,
    actions,
    editor,
    deleteConfirm,
    pagination,
  );
}

export function renderAccounts(panel, accounts, actions, editor, deleteConfirm, qrLogin) {
  renderAccountManager(panel, accounts, actions, editor, deleteConfirm, qrLogin);
}

export function renderPending(panel, tasks, actions, clearConfirm = false) {
  if (!tasks.length) {
    panel.innerHTML = emptyState("暂无待处理事项");
    return;
  }
  panel.innerHTML = `
    <div class="pending-actions">
      <button class="danger-button" id="clearPendingButton" type="button">清空待处理</button>
    </div>
    <div class="cards">${tasks.map(pendingCard).join("")}</div>
    ${clearConfirm ? clearPendingModal(tasks) : ""}
  `;
  panel.querySelector("#clearPendingButton").addEventListener("click", actions.onClear);
  panel.querySelector("[data-cancel-clear-pending]")?.addEventListener("click", actions.onCancelClear);
  panel.querySelector("[data-confirm-clear-pending]")?.addEventListener("click", actions.onConfirmClear);
}

export function showLoading(metrics) {
  metrics.innerHTML = "";
  for (const id of ["overviewPanel", "subscriptionsPanel", "accountsPanel", "pendingPanel"]) {
    document.getElementById(id).innerHTML = emptyState("加载中");
  }
}

export function renderEmptyError(metrics) {
  metrics.innerHTML = "";
  for (const id of ["overviewPanel", "subscriptionsPanel", "accountsPanel", "pendingPanel"]) {
    document.getElementById(id).innerHTML = emptyState("加载失败");
  }
}

function pendingCard(task) {
  const origin = formatTargetId(task.origin) || "未知来源";
  return `
    <article class="pending-card">
      <div>
        <h2>${escapeHtml(pendingTitle(task))}</h2>
        <p>${escapeHtml(pendingSummary(task))}</p>
      </div>
      <dl>
        <div><dt>来源</dt><dd>${escapeHtml(origin)}</dd></div>
        <div><dt>候选</dt><dd>${escapeHtml(pendingCandidateText(task))}</dd></div>
        <div><dt>过期</dt><dd>${escapeHtml(formatTime(task.expires_at))}</dd></div>
      </dl>
    </article>
  `;
}

function clearPendingModal(tasks) {
  return `
    <div class="manager-modal-backdrop">
      <section class="manager-modal confirm-modal" role="dialog" aria-modal="true" aria-label="清空待处理">
        <div class="action-confirm-preview confirm-preview">
          <span>待处理队列</span>
          <strong>${escapeHtml(tasks.length)}</strong>
          <small>ITEMS</small>
        </div>
        <div class="confirm-copy">
          <div>
            <h2>清空待处理</h2>
            <p>确认清空当前 ${escapeHtml(tasks.length)} 个待处理事项？</p>
            <p class="modal-muted">清空后，聊天侧引用任务将不再继续处理。</p>
          </div>
          <div class="modal-actions">
            <button class="ghost-button" type="button" data-cancel-clear-pending="1">取消</button>
            <button class="danger-button" type="button" data-confirm-clear-pending="1">清空</button>
          </div>
        </div>
      </section>
    </div>
  `;
}
