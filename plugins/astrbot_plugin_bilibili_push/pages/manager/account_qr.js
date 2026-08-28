export function createAccountQrController(api, state, hooks) {
  let timer = null;

  async function start() {
    stopTimer();
    state.accountQr = { loading: true, message: "正在获取二维码" };
    hooks.render();
    try {
      state.accountQr = await api.startAccountQr();
      hooks.render();
      timer = window.setInterval(poll, 3000);
    } catch (error) {
      state.accountQr = { status: "error", message: error.message || String(error) };
      hooks.render();
    }
  }

  async function poll() {
    const key = state.accountQr?.qrcode_key;
    if (!key) {
      stopTimer();
      return;
    }
    try {
      const result = await api.pollAccountQr(key);
      if (result.status === "success") {
        stopTimer();
        state.accountQr = null;
        hooks.showToast(`登录成功：${result.account?.name || result.account?.uid || "Bilibili 账号"}`);
        await hooks.refreshAll();
        return;
      }
      state.accountQr = { ...state.accountQr, ...result };
      if (["expired", "error"].includes(result.status)) {
        stopTimer();
      }
      hooks.render();
    } catch (error) {
      state.accountQr = {
        ...state.accountQr,
        status: "error",
        message: error.message || String(error),
      };
      stopTimer();
      hooks.render();
    }
  }

  function cancel() {
    stopTimer();
    state.accountQr = null;
    hooks.render();
  }

  function stopTimer() {
    if (timer) {
      window.clearInterval(timer);
      timer = null;
    }
  }

  return { start, cancel, refresh: start };
}
