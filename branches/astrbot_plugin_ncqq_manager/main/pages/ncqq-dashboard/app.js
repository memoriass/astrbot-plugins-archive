(function () {
  const els = {
    approvalCancel: document.getElementById("approval-cancel"),
    approvalConfirm: document.getElementById("approval-confirm"),
    approvalMessage: document.getElementById("approval-message"),
    approvalModal: document.getElementById("approval-modal"),
    approvalReason: document.getElementById("approval-reason"),
    approvalTitle: document.getElementById("approval-title"),
    detailBody: document.getElementById("detail-body"),
    detailClose: document.getElementById("detail-close"),
    detailModal: document.getElementById("detail-modal"),
    detailTitle: document.getElementById("detail-title"),
    managers: document.getElementById("managers"),
    refresh: document.getElementById("refresh"),
    toast: document.getElementById("toast"),
  };

  const renderers = window.NcqqDashboardRenderers;
  const mockData = window.NcqqDashboardMockData || { managers: [], approvals: [], bindings: [] };
  const detailPageSize = 9;
  let bridge = null;
  let currentData = null;
  let detailPage = 1;
  let pendingApproval = null;

  async function initBridge() {
    if (window.AstrBotPluginPage) {
      bridge = window.AstrBotPluginPage;
      await bridge.ready();
    }
  }

  async function loadData() {
    setLoading(true);
    try {
      currentData = bridge ? await bridge.apiGet("dashboard/summary") : mockData;
      renderStage(currentData);
    } catch (error) {
      showToast(error.message || String(error), true);
    } finally {
      setLoading(false);
    }
  }

  function setLoading(loading) {
    els.refresh.disabled = loading;
    els.refresh.classList.toggle("spin", loading);
  }

  function renderStage(data) {
    els.managers.innerHTML = renderers.renderStageHtml(data);
    document.body.dataset.stageView = "memory";
  }

  function openPanel(type, managerId) {
    if (!currentData) return;
    if (type === "manager") {
      const manager = (currentData.managers || []).find((item) => item.id === managerId);
      if (!manager) return;
      openDetail(manager.name || manager.id, renderers.renderManagerDetail(manager));
    } else if (type === "bindings") {
      openDetail(
        "绑定",
        renderers.renderBindingsDetail(currentData.bindings || [], currentData.managers || []),
      );
    } else if (type === "approvals") {
      openDetail("审批", renderers.renderApprovalsDetail(currentData.approvals || []));
    }
  }

  function openDetail(title, html) {
    detailPage = 1;
    els.detailTitle.textContent = title || "-";
    els.detailBody.innerHTML = html || "";
    els.detailModal.hidden = false;
    updateDetailPagination();
  }

  function activeDetailFilter() {
    return els.detailBody.querySelector("[data-instance-filter].active")?.dataset.instanceFilter || "all";
  }

  function matchesDetailFilter(card, filter) {
    const state = card.dataset.instanceState;
    return filter === "all" || (filter === "abnormal" ? state !== "online" : state === filter);
  }

  function updateDetailPagination() {
    const grid = els.detailBody.querySelector("[data-detail-grid]");
    if (!grid) return;
    const cards = Array.from(grid.querySelectorAll("[data-detail-card]"));
    const matches = cards.filter((card) => matchesDetailFilter(card, activeDetailFilter()));
    const maxPage = Math.max(1, Math.ceil(matches.length / detailPageSize));
    const start = (Math.min(detailPage, maxPage) - 1) * detailPageSize;
    detailPage = Math.min(detailPage, maxPage);
    cards.forEach((card) => {
      const index = matches.indexOf(card);
      card.hidden = index < start || index >= start + detailPageSize;
    });
    const emptyBox = els.detailBody.querySelector("[data-detail-empty]");
    if (emptyBox) emptyBox.hidden = matches.length > 0;
    updatePager(matches.length, maxPage);
  }

  function updatePager(total, maxPage) {
    const pager = els.detailBody.querySelector("[data-detail-pager]");
    if (!pager) return;
    pager.hidden = total <= detailPageSize;
    pager.querySelector("[data-detail-page-info]").textContent = `${detailPage}/${maxPage} · ${total}`;
    pager.querySelector('[data-detail-page="prev"]').disabled = detailPage <= 1;
    pager.querySelector('[data-detail-page="next"]').disabled = detailPage >= maxPage;
  }

  function filterDetailInstances(filter) {
    const active = filter || "all";
    detailPage = 1;
    els.detailBody
      .querySelectorAll("[data-instance-filter]")
      .forEach((button) => button.classList.toggle("active", button.dataset.instanceFilter === active));
    updateDetailPagination();
  }

  function stepDetailPage(direction) {
    detailPage = Math.max(1, detailPage + direction);
    updateDetailPagination();
  }

  function closeDetail() {
    els.detailModal.hidden = true;
  }

  function handleApproval(action, approvalId) {
    if (!approvalId) return;
    const reject = action === "reject";
    pendingApproval = { action, approvalId };
    els.approvalTitle.textContent = reject ? "拒绝审批" : "批准审批";
    els.approvalMessage.textContent = `${reject ? "拒绝" : "批准"} ${approvalId}`;
    els.approvalReason.hidden = !reject;
    els.approvalReason.value = "";
    els.approvalConfirm.textContent = reject ? "拒绝" : "批准";
    els.approvalConfirm.className = reject ? "reject" : "approve";
    els.approvalModal.hidden = false;
    (reject ? els.approvalReason : els.approvalConfirm).focus();
  }

  function closeApprovalDialog() {
    pendingApproval = null;
    els.approvalModal.hidden = true;
  }

  async function submitApprovalDialog() {
    if (!pendingApproval) return;
    const { action, approvalId } = pendingApproval;
    const body = action === "reject" ? { reason: els.approvalReason.value.trim() } : {};
    try {
      if (bridge) {
        await bridge.apiPost(`approvals/${approvalId}/${action}`, body);
      } else {
        currentData.approvals = (currentData.approvals || []).filter((item) => item.approval_id !== approvalId);
      }
      showToast(action === "approve" ? "已批准" : "已拒绝", false);
      closeApprovalDialog();
      closeDetail();
      await loadData();
    } catch (error) {
      showToast(error.message || String(error), true);
    }
  }

  function showToast(message, error) {
    els.toast.textContent = message;
    els.toast.classList.toggle("error", Boolean(error));
    els.toast.classList.add("show");
    window.setTimeout(() => els.toast.classList.remove("show"), 2400);
  }

  els.refresh.addEventListener("click", loadData);
  els.managers.addEventListener("click", (event) => {
    const button = event.target.closest("[data-open]");
    if (!button) return;
    openPanel(button.dataset.open, button.dataset.managerId || "");
  });
  els.detailBody.addEventListener("click", (event) => {
    const refresh = event.target.closest("button[data-refresh]");
    if (refresh) loadData();
    const filter = event.target.closest("button[data-instance-filter]");
    if (filter) filterDetailInstances(filter.dataset.instanceFilter);
    const page = event.target.closest("button[data-detail-page]");
    if (page) stepDetailPage(page.dataset.detailPage === "next" ? 1 : -1);
    const action = event.target.closest("button[data-action]");
    if (action) handleApproval(action.dataset.action, action.dataset.id);
  });
  els.detailClose.addEventListener("click", closeDetail);
  els.detailModal.addEventListener("click", (event) => {
    if (event.target === els.detailModal) closeDetail();
  });
  els.approvalCancel.addEventListener("click", closeApprovalDialog);
  els.approvalConfirm.addEventListener("click", submitApprovalDialog);
  els.approvalModal.addEventListener("click", (event) => {
    if (event.target === els.approvalModal) closeApprovalDialog();
  });

  initBridge().then(loadData).catch((error) => showToast(error.message || String(error), true));
})();
