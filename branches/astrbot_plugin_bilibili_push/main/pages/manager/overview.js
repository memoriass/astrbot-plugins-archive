import {
  bindDataset,
  emptyState,
  escapeAttribute,
  escapeHtml,
  formatTargetId,
  formatTime,
} from "./utils.js?v=manager-multitype-ai";
import { pendingTitle } from "./pending_text.js?v=manager-multitype-ai";

const ALL_TARGETS = "__all__";

export function renderOverview(panel, overview, actions, liveConfirm = null) {
  const diagnostics = overview.diagnostics || {};
  const subscriptions = overview.subscriptions || [];
  const accounts = overview.accounts || [];
  const targets = overview.targets || [];
  const pendingTasks = overview.pending_tasks || [];
  const liveTargets = buildLiveTargetOptions(subscriptions, targets);
  const issues = buildIssues(subscriptions, accounts, pendingTasks);

  panel.innerHTML = `
    <section class="overview-layout">
      <div class="overview-main">
        ${workbenchSummary(diagnostics, issues)}
      </div>
      <aside class="overview-side">
        ${issuePanel(issues)}
        ${capabilityPanel(diagnostics, liveTargets)}
      </aside>
    </section>
    ${liveConfirm ? liveCheckModal(liveConfirm) : ""}
  `;

  bindDataset(panel, "[data-jump]", (dataset) => actions.onNavigate(dataset.jump));
  const liveButton = panel.querySelector("[data-live-selected]");
  if (liveButton) {
    liveButton.addEventListener("click", () => {
      const select = panel.querySelector("#overviewManualTargetSelect");
      actions.onManualLive(select.value, select.options[select.selectedIndex]?.textContent || select.value);
    });
  }
  panel.querySelector("[data-cancel-live-check]")?.addEventListener("click", actions.onCancelLive);
  panel.querySelector("[data-confirm-live-check]")?.addEventListener("click", actions.onConfirmLive);
}

function workbenchSummary(diagnostics, issues) {
  const total = diagnostics.subscriptions || 0;
  const enabled = diagnostics.enabled_subscriptions || 0;
  const issueCount = issues.reduce((sum, issue) => sum + issue.count, 0);
  const tone = issueCount ? "attention" : "ok";
  const title = issueCount ? "有待处理项" : "运行状态稳定";
  return `
    <section class="workbench-summary ${tone}">
      <div>
        <p class="section-kicker">总览</p>
        <h2>${title}</h2>
        <p>
          已启用 ${escapeHtml(enabled)}/${escapeHtml(total)} 个订阅，
          覆盖 ${escapeHtml(diagnostics.targets || 0)} 个会话，
          当前有 ${escapeHtml(diagnostics.pending_tasks || 0)} 个待处理事项。
        </p>
      </div>
      <div class="workbench-facts">
        ${factItem("启用率", ratioText(enabled, total))}
        ${factItem("账号", `${diagnostics.valid_accounts || 0}/${diagnostics.accounts || 0}`)}
        ${factItem("待处理", issueCount)}
      </div>
    </section>
  `;
}

function issuePanel(issues) {
  return `
    <section class="overview-section side-section">
      <div class="section-heading">
        <div>
          <p class="section-kicker">队列</p>
          <h2>需要处理</h2>
        </div>
      </div>
      ${issues.length ? `<div class="issue-list">${issues.map(issueRow).join("")}</div>` : emptyState("暂无待处理项")}
    </section>
  `;
}

function capabilityPanel(diagnostics, targets) {
  return `
    <section class="overview-section side-section">
      <div class="section-heading">
        <div>
          <p class="section-kicker">运行</p>
          <h2>运行能力</h2>
        </div>
      </div>
      <div class="capability-list">
        ${capabilityItem("动态检查", `${diagnostics.dynamic_check_interval || diagnostics.check_interval || "-"} 秒`)}
        ${capabilityItem("直播检查", `${diagnostics.live_check_interval || diagnostics.check_interval || "-"} 秒`)}
        ${capabilityItem("链接解析", diagnostics.enable_link_parser ? "启用" : "停用")}
        ${capabilityItem("AI 工具", diagnostics.enable_ai_tools ? "启用" : "停用")}
        ${capabilityItem("账号冷却", `${diagnostics.risk_cooldown_sec || "-"} 秒`)}
      </div>
      <div class="overview-live-check">
        <select id="overviewManualTargetSelect" aria-label="目标会话">
          <option value="${ALL_TARGETS}">全部检查</option>
          ${targets.map((target) => `<option value="${escapeAttribute(target.value)}">${escapeHtml(target.label)}</option>`).join("")}
        </select>
        <button class="ghost-button" type="button" data-live-selected="1" ${targets.length ? "" : "disabled"}>直播检查</button>
      </div>
    </section>
  `;
}

function buildIssues(subscriptions, accounts, pendingTasks) {
  const disabled = subscriptions.filter((sub) => !sub.enabled);
  const invalidAccounts = accounts.filter((account) => !account.valid);
  const issues = [];
  if (pendingTasks.length) {
    issues.push({
      title: "待处理事项",
      count: pendingTasks.length,
      detail: pendingTasks.slice(0, 2).map((task) => `${pendingTitle(task)} · ${formatTime(task.expires_at)}`),
      tab: "pending",
    });
  }
  if (invalidAccounts.length) {
    issues.push({
      title: "账号失效",
      count: invalidAccounts.length,
      detail: invalidAccounts.map((account) => account.name || account.uid || "-"),
      tab: "accounts",
    });
  }
  if (disabled.length) {
    issues.push({
      title: "停用订阅",
      count: disabled.length,
      detail: disabled.slice(0, 3).map((sub) => sub.username || sub.uid),
      tab: "subscriptions",
    });
  }
  return issues;
}

function issueRow(issue) {
  return `
    <article class="issue-row">
      <div>
        <strong>${escapeHtml(issue.title)}</strong>
        <p>${escapeHtml(issue.detail.join(" / "))}</p>
      </div>
      <button class="ghost-button" type="button" data-jump="${escapeAttribute(issue.tab)}">${escapeHtml(issue.count)}</button>
    </article>
  `;
}

function factItem(label, value) {
  return `<article><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></article>`;
}

function capabilityItem(label, value) {
  return `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function buildLiveTargetOptions(subscriptions, targetRows) {
  const targets = new Map();
  const enabledTargets = new Map(
    targetRows.map((target) => [target.target_id, target.enabled !== false]),
  );
  for (const sub of subscriptions) {
    if (!sub.enabled || sub.sub_type !== "live" || !sub.target_id) {
      continue;
    }
    if (enabledTargets.has(sub.target_id) && !enabledTargets.get(sub.target_id)) {
      continue;
    }
    targets.set(sub.target_id, formatTargetId(sub.target_id));
  }
  return Array.from(targets, ([value, label]) => ({ value, label })).sort((a, b) =>
    a.label.localeCompare(b.label, "zh-CN"),
  );
}

function liveCheckModal(target) {
  const label = target.displayName || target.targetId || "-";
  const isAll = target.targetId === ALL_TARGETS;
  return `
    <div class="manager-modal-backdrop">
      <section class="manager-modal confirm-modal" role="dialog" aria-modal="true" aria-label="直播检查">
        <div class="action-confirm-preview confirm-preview">
          <span>直播检查</span>
          <strong>${isAll ? "ALL" : "LIVE"}</strong>
          <small>${escapeHtml(isAll ? "GROUPS" : "TARGET")}</small>
        </div>
        <div class="confirm-copy">
          <div>
            <h2>执行直播检查</h2>
            <p>确认对 ${escapeHtml(label)} 执行手动直播检查？</p>
            <p class="modal-muted">检查会按当前订阅与会话配置执行，可能触发对应推送。</p>
          </div>
          <div class="modal-actions">
            <button class="ghost-button" type="button" data-cancel-live-check="1">取消</button>
            <button class="ghost-button" type="button" data-confirm-live-check="1">开始检查</button>
          </div>
        </div>
      </section>
    </div>
  `;
}

function ratioText(value, total) {
  if (!total) {
    return "0%";
  }
  return `${Math.round((value / total) * 100)}%`;
}
