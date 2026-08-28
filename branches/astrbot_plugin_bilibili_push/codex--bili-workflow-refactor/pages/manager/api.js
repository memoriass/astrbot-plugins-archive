import { createLocalBridge } from "./mock_bridge.js?v=manager-live-modal";
import { unwrap } from "./utils.js?v=manager-live-modal";

export function getBridge() {
  return window.AstrBotPluginPage || createLocalBridge();
}

export function createApi(bridge) {
  return {
    async overview() {
      return unwrap(await bridge.apiGet("overview"));
    },
    async createSubscription(payload) {
      return unwrap(await bridge.apiPost("subscriptions/create", payload));
    },
    async updateSubscription(payload) {
      return unwrap(await bridge.apiPost("subscriptions/update", payload));
    },
    async setSubscriptionEnabled(payload) {
      return unwrap(await bridge.apiPost("subscriptions/enabled", payload));
    },
    async deleteSubscription(payload) {
      return unwrap(await bridge.apiPost("subscriptions/delete", payload));
    },
    async clearPending() {
      return unwrap(await bridge.apiPost("pending/clear", {}));
    },
    async upsertAccount(payload) {
      return unwrap(await bridge.apiPost("accounts/upsert", payload));
    },
    async deleteAccount(payload) {
      return unwrap(await bridge.apiPost("accounts/delete", payload));
    },
    async setAccountValid(payload) {
      return unwrap(await bridge.apiPost("accounts/valid", payload));
    },
    async manualLiveCheck(targetId) {
      return unwrap(await bridge.apiPost("checks/live", { target_id: targetId }));
    },
  };
}
