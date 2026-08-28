import {
  escapeAttribute,
  escapeHtml,
} from "./utils.js?v=manager-sub-identity";

export function createIdentityFields(item) {
  return `
    <div class="editor-grid identity-grid">
      ${field("UID", "uid", item.uid || "", "text", true)}
      <label class="identity-name-field">
        <span>UP 主</span>
        <div class="identity-name-row">
          <input name="username" type="text" value="${escapeAttribute(item.username || "")}" />
          <button class="ghost-button identity-lookup-button" type="button" data-lookup-up="1">搜索</button>
        </div>
      </label>
    </div>
  `;
}

export function bindIdentityLookup(form, lookup) {
  const button = form.querySelector("[data-lookup-up]");
  if (!button || !lookup) {
    return;
  }
  button.addEventListener("click", async () => {
    const uid = String(form.elements.uid?.value || "").trim();
    if (!uid) {
      return;
    }
    button.disabled = true;
    try {
      const user = await lookup(uid);
      if (user) {
        applyIdentityLookup(form, user);
      }
    } finally {
      button.disabled = false;
    }
  });
}

function applyIdentityLookup(form, user) {
  const uid = String(user.uid || form.elements.uid?.value || "").trim();
  const username = String(user.username || "").trim();
  const face = String(user.face || "").trim();
  if (uid && form.elements.uid) {
    form.elements.uid.value = uid;
  }
  if (username && form.elements.username) {
    form.elements.username.value = username;
  }
  const previewName = form.querySelector("[data-preview-username]");
  const previewUid = form.querySelector("[data-preview-uid]");
  const previewFace = form.querySelector("[data-preview-face]");
  if (previewName && username) {
    previewName.textContent = username;
  }
  if (previewUid) {
    previewUid.textContent = `UID: ${uid || "-"}`;
  }
  if (previewFace && face) {
    previewFace.src = face;
  }
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
