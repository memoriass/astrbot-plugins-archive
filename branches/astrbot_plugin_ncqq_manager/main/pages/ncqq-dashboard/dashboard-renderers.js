(function () {
  const utils = window.NcqqDashboardUtils;
  const { assetUrl, empty, escapeHtml, fmtAge, instanceState, managerState, maskQQ, shortUrl } = utils;
  const mirrorSlotCount = 8;
  const mirrorSceneVersion = "memory-scene-v14-mapcrop6-manual-20260620";
  const mirrorAlertVersion = "memory-alert-edge-v17-manual-20260620";
  const managerSlots = [1, 3, 4, 5, 6, 8];
  const utilitySlots = {
    approvals: 2,
    bindings: 7,
  };
  const mirrorShardFiles = [
    "shard-01-upper-left-scene-v14.png",
    "shard-02-top-center-scene-v14.png",
    "shard-03-upper-right-scene-v14.png",
    "shard-04-left-middle-scene-v14.png",
    "shard-05-right-middle-scene-v14.png",
    "shard-06-lower-left-scene-v14.png",
    "shard-07-lower-center-scene-v14.png",
    "shard-08-lower-right-scene-v14.png",
  ];

  function renderStageHtml(data) {
    const managers = data.managers || [];
    const usedSlots = new Set();
    const panels = [
      ...managers.slice(0, managerSlots.length).map((manager, index) => {
        const slot = managerSlots[index];
        usedSlots.add(slot);
        return renderManagerPanel(manager, index, slot);
      }),
      renderUtilityPanel("approvals", "待审批", (data.approvals || []).length, utilitySlots.approvals, usedSlots),
      renderUtilityPanel("bindings", "绑定关系", (data.bindings || []).length, utilitySlots.bindings, usedSlots),
    ];
    const decorSlots = Array.from({ length: mirrorSlotCount }, (_, index) => index + 1).filter(
      (slot) => !usedSlots.has(slot),
    );
    const content = panels.concat(renderMirrorDecor(decorSlots)).join("") || empty("暂无面板");
    return `
      <section class="memory-stage" aria-label="ncqq 管理面板">
        <div class="memory-board" data-count="${panels.length}">
          <div class="memory-visual" aria-hidden="true">
            ${renderMirrorPieces()}
          </div>
          ${content}
        </div>
      </section>
    `;
  }

  function renderMirrorPieces() {
    return mirrorShardFiles
      .map(
        (file, index) => `
          <img class="memory-piece slot-${index + 1}" src="${escapeHtml(assetUrl(`./assets/memory-shards-scene/${file}?v=${mirrorSceneVersion}`))}" alt="" loading="eager" />
        `,
      )
      .join("");
  }

  function renderAlertOverlay(slot, tone) {
    const baseFile = mirrorShardFiles[slot - 1] || "";
    if (!baseFile) return "";
    const file = baseFile.replace("-scene-v14.png", `-alert-${tone}-v17.png`);
    return `<img class="memory-edge-alert ${tone}" src="${escapeHtml(assetUrl(`./assets/memory-shards-alert/${file}?v=${mirrorAlertVersion}`))}" alt="" aria-hidden="true" loading="eager" />`;
  }

  function renderMirrorDecor(slots) {
    return slots.map((slot) => `<span class="memory-shard memory-decor slot-${slot}" aria-hidden="true"></span>`);
  }

  function renderManagerPanel(manager, index, slot) {
    const instances = manager.instances || {};
    const health = manager.health || {};
    const state = managerState(health);
    const online = Number(instances.online || 0);
    const total = Number(instances.total || 0);
    const tag = manager.is_default ? "LOCAL" : index === 1 ? "CLOUD" : "NODE";
    const hasOfflineAlert = total > online || state === "offline";
    const alert = hasOfflineAlert ? ' data-alert="offline"' : "";
    return `
      <button class="memory-shard memory-link slot-${slot} accent-${index % 6}" type="button" data-open="manager" data-manager-id="${escapeHtml(manager.id)}" data-state="${state}"${alert} aria-label="${escapeHtml(`${manager.name || manager.id} ${online}/${total}`)}">
        ${hasOfflineAlert ? renderAlertOverlay(slot, "red") : ""}
        <span class="memory-label" aria-hidden="true">
          <span>${escapeHtml(tag)}</span>
          <strong>${escapeHtml(manager.name || manager.id)}</strong>
          <em>${escapeHtml(`${online} / ${total}`)}</em>
        </span>
      </button>
    `;
  }

  function renderUtilityPanel(type, title, value, slot, usedSlots) {
    usedSlots.add(slot);
    const meta = {
      approvals: "accent-review",
      bindings: "accent-bind",
    }[type] || "accent-utility";
    const hasApprovalAlert = type === "approvals" && Number(value || 0) > 0;
    return `
      <button class="memory-shard memory-link slot-${slot} ${meta}" type="button" data-open="${escapeHtml(type)}"${hasApprovalAlert ? ' data-alert="approval"' : ""} aria-label="${escapeHtml(`${title} ${value}`)}">
        ${hasApprovalAlert ? renderAlertOverlay(slot, "yellow") : ""}
        <span class="memory-label" aria-hidden="true">
          <span>${type === "approvals" ? "REVIEW" : "BIND"}</span>
          <strong>${escapeHtml(title)}</strong>
          <em>${escapeHtml(String(value))}</em>
        </span>
      </button>
    `;
  }

  function renderManagerDetail(manager) {
    const instances = manager.instances || {};
    const items = instances.items || [];
    return `
      <div class="detail-workspace">
        <section class="detail-main">
          <div class="detail-head">
            <div>
              <h2>${escapeHtml(manager.name || manager.id)}</h2>
              <p>${escapeHtml(manager.id)} · ${escapeHtml(shortUrl(manager.url))}${manager.is_default ? " · default" : ""}</p>
            </div>
            ${renderStatusGroup(items)}
          </div>
          <div class="detail-grid" data-detail-grid>
            ${items.map((item, index) => renderInstanceCard(item, index)).join("") || empty("暂无实例")}
          </div>
          <div class="detail-empty" data-detail-empty hidden>暂无匹配实例</div>
          <div class="detail-pager" data-detail-pager hidden>
            <button type="button" data-detail-page="prev">上一页</button>
            <span data-detail-page-info></span>
            <button type="button" data-detail-page="next">下一页</button>
          </div>
        </section>
      </div>
    `;
  }

  function renderStatusGroup(items) {
    const counts = { all: items.length, abnormal: 0, warn: 0, offline: 0 };
    items.forEach((item) => {
      const key = instanceState(item).key;
      if (key !== "online") counts.abnormal += 1;
      if (counts[key] !== undefined) counts[key] += 1;
    });
    return `
      <div class="status-menu" aria-label="实例状态筛选">
        ${[
          ["all", "全部"],
          ["abnormal", "异常"],
          ["warn", "心跳"],
          ["offline", "离线"],
        ]
          .map(
            ([key, label]) => `
              <button class="detail-filter${key === "all" ? " active" : ""}" type="button" data-instance-filter="${key}">
                <strong>${counts[key]}</strong><span>${label}</span>
              </button>
            `,
          )
          .join("")}
      </div>
    `;
  }

  function renderInstanceCard(item, index) {
    const state = instanceState(item);
    const avatar = String(item.avatar || "").trim();
    const name = item.display_name || item.name || "-";
    const bgStyle = avatar ? ` style="--instance-bg:url('${escapeHtml(avatar)}')"` : "";
    return `
      <article class="instance-card glass-panel ${state.key}" data-detail-card data-instance-index="${index}" data-instance-state="${state.key}"${bgStyle}>
        <div class="instance-card-body">
          <h3>${escapeHtml(name)}</h3>
          <div class="instance-avatar${avatar ? "" : " empty-avatar"}">
            ${avatar ? `<img src="${escapeHtml(avatar)}" alt="" loading="lazy" onerror="this.remove()" />` : "<span>OFF</span>"}
          </div>
          <p>QQ: ${escapeHtml(maskQQ(item.uin))}</p>
        </div>
        <div class="instance-foot">
          <span class="instance-state ${state.key}">${escapeHtml(state.text)}</span>
          <button class="instance-refresh" type="button" data-refresh title="刷新" aria-label="刷新实例数据">&#8635;</button>
        </div>
      </article>
    `;
  }

  function renderBindingsDetail(bindings, managers) {
    const lookup = buildInstanceLookup(managers || []);
    return `<div class="binding-grid">${bindings.map((item) => renderBindingCard(item, lookup)).join("") || empty("暂无绑定")}</div>`;
  }

  function buildInstanceLookup(managers) {
    const lookup = {};
    managers.forEach((manager) => {
      (manager.instances?.items || []).forEach((item) => {
        [item.name, item.display_name].filter(Boolean).forEach((name) => {
          lookup[`${manager.id}/${name}`] = item;
          if (manager.is_default) lookup[name] = item;
        });
      });
    });
    return lookup;
  }

  function renderBindingCard(item, lookup) {
    const refs = item.instances || [];
    const primary = refs.map((ref) => lookup[ref]).find(Boolean) || {};
    const avatar = String(primary.avatar || "").trim();
    const label = primary.display_name || primary.name || refs[0] || "-";
    const initial = String(label).slice(0, 1).toUpperCase();
    return `
      <article class="binding binding-card glass-panel">
        <div class="binding-avatar${avatar ? "" : " no-avatar"}">
          ${avatar ? `<img src="${escapeHtml(avatar)}" alt="" loading="lazy" onerror="this.remove()" />` : `<span>${escapeHtml(initial)}</span>`}
        </div>
        <strong>${escapeHtml(item.qq || "-")}</strong>
        <p>${escapeHtml(label)}</p>
        <div class="binding-refs">${refs.map((ref) => `<span>${escapeHtml(ref)}</span>`).join("") || "<span>-</span>"}</div>
      </article>
    `;
  }

  function renderApprovalsDetail(approvals) {
    return `<div class="approval-grid">${approvals
      .map(
        (item) => `
        <article class="approval glass-panel">
          <div>
            <h3>${escapeHtml(item.description || item.action)}</h3>
            <p>${escapeHtml(item.approval_id)} · ${escapeHtml(item.manager_id || "-")}/${escapeHtml(item.instance_name || "-")} · ${fmtAge(item.age_seconds)}</p>
            <p>QQ ${escapeHtml(item.requester_qq || "-")}${item.group_id ? ` · 群 ${escapeHtml(item.group_id)}` : ""}</p>
          </div>
          <div class="approval-actions">
            <button class="approve" data-action="approve" data-id="${escapeHtml(item.approval_id)}">批准</button>
            <button class="reject" data-action="reject" data-id="${escapeHtml(item.approval_id)}">拒绝</button>
          </div>
        </article>
      `,
      )
      .join("") || empty("暂无审批")}</div>`;
  }

  window.NcqqDashboardRenderers = {
    renderApprovalsDetail,
    renderBindingsDetail,
    renderManagerDetail,
    renderStageHtml,
  };
})();
