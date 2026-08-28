import { createApi, getBridge } from "./api.js?v=manager-target-offset";
import { createAccountQrController } from "./account_qr.js?v=manager-target-offset";
import { renderOverview } from "./overview.js?v=manager-multitype-ai";
import {
  renderAccounts,
  renderEmptyError,
  renderMetrics,
  renderPending,
  renderSubscriptions,
  renderTabs,
  showLoading,
} from "./renderers.js?v=manager-target-offset";
import { groupSubscriptionEditorItem } from "./subscriptions.js?v=manager-target-offset";

const bridge = getBridge();
const api = createApi(bridge);

const state = {
  tab: "overview",
  overview: null,
  subscriptionEditor: null,
  subscriptionDelete: null,
  subscriptionPage: 1,
  accountEditor: null,
  accountDelete: null,
  accountQr: null,
  pendingClearConfirm: false,
  liveCheckConfirm: null,
  query: "",
  type: "all",
};

const VALID_TABS = new Set(["overview", "subscriptions", "accounts", "pending"]);

const metrics = document.getElementById("metrics");
const toast = document.getElementById("toast");
const searchInput = document.getElementById("searchInput");
const typeFilter = document.getElementById("typeFilter");
const accountQrController = createAccountQrController(api, state, {
  render,
  refreshAll,
  showToast,
});

document.getElementById("refreshButton").addEventListener("click", refreshAll);
searchInput.addEventListener("input", () => {
  state.query = searchInput.value.trim().toLowerCase();
  state.subscriptionPage = 1;
  render();
});
typeFilter.addEventListener("change", () => {
  state.type = typeFilter.value;
  state.subscriptionPage = 1;
  render();
});
document.querySelectorAll(".tab").forEach((button) => {
  button.addEventListener("click", () => {
    switchTab(button.dataset.tab);
  });
});

await bridge.ready();
await refreshAll();

async function refreshAll() {
  try {
    showLoading(metrics);
    state.overview = await api.overview();
    render();
  } catch (error) {
    showToast(error.message || String(error));
    renderEmptyError(metrics);
  }
}

function render() {
  const overview = state.overview || {};
  renderMetrics(metrics, overview.diagnostics || {});
  renderTabs(state.tab);
  renderOverview(
    document.getElementById("overviewPanel"),
    overview,
    {
      onNavigate: switchTab,
      onManualLive: startManualLiveCheck,
      onConfirmLive: manualLiveCheck,
      onCancelLive: cancelManualLiveCheck,
    },
    state.liveCheckConfirm,
  );
  renderSubscriptions(
    document.getElementById("subscriptionsPanel"),
    overview.subscriptions || [],
    overview.targets || [],
    { query: state.query, type: state.type },
    {
      onCreate: startCreateSubscription,
      onEdit: startEditSubscription,
      onSubmit: submitSubscription,
      onCancel: cancelSubscriptionEdit,
      onDelete: startDeleteSubscription,
      onConfirmDelete: deleteSubscription,
      onCancelDelete: cancelSubscriptionDelete,
      onPage: setSubscriptionPage,
      onLookupUser: lookupBiliUser,
    },
    state.subscriptionEditor,
    state.subscriptionDelete,
    { page: state.subscriptionPage },
  );
  renderAccounts(
    document.getElementById("accountsPanel"),
    overview.accounts || [],
    {
      onCreate: startCreateAccount,
      onEdit: startEditAccount,
      onSubmit: submitAccount,
      onCancel: cancelAccountEdit,
      onDelete: startDeleteAccount,
      onConfirmDelete: deleteAccount,
      onCancelDelete: cancelAccountDelete,
      onQrLogin: accountQrController.start,
      onCancelQr: accountQrController.cancel,
      onRefreshQr: accountQrController.refresh,
    },
    state.accountEditor,
    state.accountDelete,
    state.accountQr,
  );
  renderPending(
    document.getElementById("pendingPanel"),
    overview.pending_tasks || [],
    {
      onClear: startClearPending,
      onConfirmClear: clearPending,
      onCancelClear: cancelClearPending,
    },
    state.pendingClearConfirm,
  );
}

function switchTab(tab) {
  state.tab = VALID_TABS.has(tab) ? tab : "overview";
  render();
}

function setSubscriptionPage(dataset) {
  state.subscriptionPage = Math.max(1, Number(dataset.page || 1));
  render();
}

function startCreateSubscription() {
  const targetId = state.overview?.targets?.[0]?.target_id
    || state.overview?.subscriptions?.[0]?.target_id
    || "llonebot:GroupMessage:";
  state.subscriptionEditor = {
    mode: "create",
    item: { sub_types: ["dynamic"], target_id: targetId, enabled: true },
  };
  state.subscriptionDelete = null;
  render();
}

function startEditSubscription(dataset) {
  const item = findSubscription(dataset);
  if (!item) {
    showToast("未找到订阅");
    return;
  }
  state.subscriptionEditor = {
    mode: "edit",
    item: groupSubscriptionEditorItem(state.overview?.subscriptions || [], {
      ...item,
      original_uid: item.uid,
      original_sub_type: item.sub_type,
      original_target_id: item.target_id,
    }),
  };
  state.subscriptionDelete = null;
  render();
}

function cancelSubscriptionEdit() {
  state.subscriptionEditor = null;
  render();
}

function startDeleteSubscription(dataset) {
  const item = findSubscription(dataset);
  if (!item) {
    showToast("未找到订阅");
    return;
  }
  state.subscriptionDelete = {
    item: {
      ...item,
      sub_types: uniqueTypes(String(dataset.subTypes || item.sub_type || "dynamic").split(",")),
    },
  };
  state.subscriptionEditor = null;
  render();
}

function cancelSubscriptionDelete() {
  state.subscriptionDelete = null;
  render();
}

async function submitSubscription(data) {
  try {
    const operations = subscriptionOperations(data);
    for (const operation of operations) {
      if (operation.kind === "update") {
        await api.updateSubscription(operation.payload);
      } else {
        await api.createSubscription(operation.payload);
      }
    }
    showToast(data.mode === "edit" ? "订阅已更新" : "订阅已创建");
    state.subscriptionEditor = null;
    state.subscriptionDelete = null;
    await refreshAll();
  } catch (error) {
    showToast(error.message || String(error));
  }
}

async function lookupBiliUser(uid) {
  try {
    const user = await api.lookupBiliUser(uid);
    showToast(`已加载：${user.username || user.uid}`);
    return user;
  } catch (error) {
    showToast(error.message || String(error));
    return null;
  }
}

function subscriptionOperations(data) {
  const selectedTypes = uniqueTypes(data.sub_types || [data.sub_type || "dynamic"]);
  const basePayloads = selectedTypes.map((subType) => ({
    uid: data.uid,
    username: data.username,
    sub_type: subType,
    target_id: data.target_id,
    categories: data.categories_by_type?.[subType] || data.categories || [],
    tags: data.tags,
    enabled: data.enabled === true || data.enabled === "true",
  }));
  if (data.mode !== "edit") {
    return basePayloads.map((payload) => ({ kind: "create", payload }));
  }
  const existing = (state.overview?.subscriptions || []).filter(
    (sub) =>
      String(sub.uid) === String(data.uid) &&
      String(sub.target_id) === String(data.target_id),
  );
  const ops = [];
  for (const payload of basePayloads) {
    const current = existing.find((sub) => sub.sub_type === payload.sub_type);
    if (current) {
      ops.push({
        kind: "update",
        payload: {
          ...payload,
          original_uid: current.uid,
          original_sub_type: current.sub_type,
          original_target_id: current.target_id,
        },
      });
    } else {
      ops.push({ kind: "create", payload });
    }
  }
  return ops;
}

function findSubscription(dataset) {
  return (state.overview?.subscriptions || []).find(
    (sub) =>
      String(sub.uid) === String(dataset.uid) &&
      sub.sub_type === dataset.subType &&
      sub.target_id === dataset.targetId,
  );
}

function findAccount(dataset) {
  return (state.overview?.accounts || []).find(
    (account) => String(account.uid) === String(dataset.uid),
  );
}

function startCreateAccount() {
  state.accountEditor = { mode: "create", item: { valid: true } };
  state.accountDelete = null;
  render();
}

function startEditAccount(dataset) {
  const item = (state.overview?.accounts || []).find(
    (account) => String(account.uid) === String(dataset.uid),
  );
  if (!item) {
    showToast("未找到账号");
    return;
  }
  state.accountEditor = { mode: "edit", item };
  state.accountDelete = null;
  render();
}

function cancelAccountEdit() {
  state.accountEditor = null;
  render();
}

function startDeleteAccount(dataset) {
  const item = findAccount(dataset);
  if (!item) {
    showToast("未找到账号");
    return;
  }
  state.accountDelete = { item };
  state.accountEditor = null;
  render();
}

function cancelAccountDelete() {
  state.accountDelete = null;
  render();
}

async function submitAccount(data) {
  try {
    await api.upsertAccount({
      uid: data.uid,
      name: data.name,
      face: data.face,
      cookies_text: data.cookies_text,
      valid: data.valid === "true",
    });
    showToast("账号已保存");
    state.accountEditor = null;
    state.accountDelete = null;
    await refreshAll();
  } catch (error) {
    showToast(error.message || String(error));
  }
}

async function deleteSubscription(dataset) {
  try {
    const subTypes = uniqueTypes(String(dataset.subTypes || dataset.subType || "dynamic").split(","));
    for (const subType of subTypes) {
      await api.deleteSubscription(subscriptionPayload({ ...dataset, subType }));
    }
    showToast("订阅已删除");
    state.subscriptionDelete = null;
    await refreshAll();
  } catch (error) {
    showToast(error.message || String(error));
  }
}

async function deleteAccount(dataset) {
  try {
    await api.deleteAccount({ uid: dataset.uid });
    showToast("账号已删除");
    state.accountDelete = null;
    await refreshAll();
  } catch (error) {
    showToast(error.message || String(error));
  }
}

function startClearPending() {
  state.pendingClearConfirm = true;
  render();
}

function cancelClearPending() {
  state.pendingClearConfirm = false;
  render();
}

async function clearPending() {
  try {
    const result = await api.clearPending();
    showToast(`已清空 ${result.cleared || 0} 个待处理事项`);
    state.pendingClearConfirm = false;
    await refreshAll();
  } catch (error) {
    showToast(error.message || String(error));
  }
}

function startManualLiveCheck(targetId, displayName) {
  if (!targetId) {
    return;
  }
  state.liveCheckConfirm = {
    targetId,
    displayName: displayName || targetId,
  };
  render();
}

function cancelManualLiveCheck() {
  state.liveCheckConfirm = null;
  render();
}

async function manualLiveCheck() {
  const target = state.liveCheckConfirm;
  if (!target?.targetId) {
    return;
  }
  const targetId = target.targetId;
  const isAll = targetId === "__all__";
  try {
    const result = await api.manualLiveCheck(targetId);
    const targetText = isAll ? `检查 ${result.targets || 0} 个群，` : "";
    showToast(`手动检查完成，${targetText}推送 ${result.pushed || 0} 条`);
    state.liveCheckConfirm = null;
    await refreshAll();
  } catch (error) {
    showToast(error.message || String(error));
  }
}

function subscriptionPayload(dataset, extra = {}) {
  return {
    uid: dataset.uid,
    sub_type: dataset.subType,
    target_id: dataset.targetId,
    ...extra,
  };
}

function uniqueTypes(types) {
  const values = (types || []).filter((type) => ["dynamic", "live"].includes(type));
  return [...new Set(values.length ? values : ["dynamic"])];
}

function showToast(message) {
  toast.textContent = message;
  toast.hidden = false;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    toast.hidden = true;
  }, 2600);
}
