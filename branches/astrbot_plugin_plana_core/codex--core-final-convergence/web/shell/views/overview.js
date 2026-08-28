window.PlanaViews = window.PlanaViews || {};

window.PlanaViews.overview = {
  meta: { title: 'overview.title', caption: 'overview.caption' },

  async render(ctx, root) {
    const [overview, feedback, domains, remote, diagnostics, tasks, proactive] = await Promise.all([
      ctx.api('/api/overview'),
      ctx.api('/api/feedback?scope=global&limit=40'),
      ctx.api('/api/domains'),
      ctx.api('/api/remote-tasks?limit=30'),
      ctx.api('/api/diagnostics'),
      ctx.api('/api/tasks?scope=global&limit=40'),
      ctx.api('/api/proactive?scope=global&limit=20'),
    ]);
    const data = overview.data || {};
    const build = data.build || {};
    const feedbackItems = feedback.items || [];
    const domainData = domains.data || {};
    const domainHarness = domainData.domain_harness || {};
    const domainSummary = domainHarness.summary || {};
    const remoteData = remote.data || {};
    const remoteItems = remoteData.display_items || [];
    const executor = remoteData.summary?.executor || remoteData.summary || {};
    const diagnosticData = diagnostics.data || {};
    const services = diagnosticData.services || [];
    const warehouse = services.find((item) => item.service_ref === 'plana.memory_warehouse') || {};
    const gallery = data.gallery || {};
    const tables = data.tables || {};
    const memoryCount = (tables.episodic_memories || 0) + (tables.semantic_memories || 0) + (tables.tool_memories || 0);
    const pendingFeedback = feedbackItems.filter((item) => item.status === 'pending');
    const taskItems = tasks.data || tasks.tasks || [];
    const proactiveItems = proactive.tasks || [];
    const openTasks = [...taskItems, ...proactiveItems].filter((item) => !['completed', 'cancelled', 'dismissed'].includes(item.status));
    const staleTasks = remoteItems.filter((item) => item.display?.stale);
    const maintenance = data.memory_production?.memory_maintenance_last_run || {};
    const companionIssue = !gallery.enabled || !gallery.configured || gallery.last_error || !gallery.local_loopback_only;

    const health = [
      { title: '陪伴服务', value: companionIssue ? '需要检查' : '可用', status: gallery.last_error ? '图库连接异常' : gallery.local_loopback_only ? '本机链路正常' : '访问边界异常', text: companionIssue ? '陪伴反应图或本机访问边界需要诊断。' : 'Persona、关系上下文与 Gallery 协同链路可用。', tone: companionIssue ? 'danger' : 'success', section: 'settings', subview: 'diagnostics' },
      { title: 'Memory Warehouse', value: warehouse.status === 'active' ? '健康' : warehouse.status === 'issue' ? '异常' : '待连接', status: `${memoryCount} 条 Core 记忆`, text: warehouse.description || (maintenance.status === 'failed' ? '最近记忆维护未成功。' : '检查独立仓库、索引和同步状态。'), tone: warehouse.status === 'active' ? 'success' : warehouse.status === 'issue' || maintenance.status === 'failed' ? 'danger' : 'warn', section: 'settings', subview: 'diagnostics' },
      { title: '领域集成', value: `${domainSummary.discovered || 0} 个已发现`, status: domainHarness.status === 'empty' ? '安全空态' : domainHarness.status === 'issue' || domainHarness.status === 'unsupported' ? '发现异常' : `${domainSummary.direct_dispatch || 0} 个可直接分派`, text: domainHarness.status === 'empty' ? '没有插件提供 descriptor；Core 不创建内置能力占位。' : '领域业务由当前启用插件提供。', tone: domainHarness.status === 'issue' || domainHarness.status === 'unsupported' ? 'danger' : domainHarness.status === 'empty' ? 'warn' : 'success', section: 'capabilities' },
      { title: '审批与任务', value: `${pendingFeedback.length + openTasks.length} 项待处理`, status: pendingFeedback.length ? `${pendingFeedback.length} 项记忆复核` : '没有记忆复核', text: '集中查看记忆复核、普通待办和主动任务。', tone: pendingFeedback.length + openTasks.length ? 'warn' : 'success', section: 'tasks', subview: pendingFeedback.length ? 'approvals' : 'todos' },
      { title: executor.name || executor.label || 'Codex Runner', value: executor.stale ? `${executor.stale} 项失联` : executor.active ? `${executor.active} 项运行中` : `${executor.completed || 0} 项完成`, status: executor.label || '尚无运行证据', text: executor.stale ? '存在长时间未更新的 Codex 任务。' : '显示最近 Codex 运行和结果交付状态。', tone: executor.stale ? 'danger' : executor.active ? 'warn' : executor.completed ? 'success' : 'neutral', section: 'resources', subview: 'remote' },
    ];

    const attention = [
      ...pendingFeedback.map(() => ({ title: '记忆复核待处理', text: '检查建议内容后再应用到记忆库。', tone: 'warn', section: 'memory', subview: 'quality' })),
      ...staleTasks.map((item) => ({ title: item.display?.title || 'Codex 任务可能失联', text: item.display?.duration || '长时间没有更新。', tone: 'danger', section: 'resources', subview: 'remote' })),
      ...(domainHarness.errors || []).map((error) => ({ title: '领域插件发现异常', text: error, tone: 'danger', section: 'capabilities' })),
    ].slice(0, 6);
    const activity = remoteItems.slice(0, 6).map((item) => ({ title: item.display?.title || 'Codex 任务', text: `${item.display?.status || '待处理'} · ${item.display?.lane || '交互任务'}`, time: Number(item.updated_at || 0), section: 'resources', subview: 'remote' }));

    root.innerHTML = `<div class="view-stack overview-dashboard">
      <section class="section-block">${ctx.sectionHeading('陪伴中枢状态', `优先检查陪伴、记忆仓库、领域集成和 Codex 运行。当前构建：${build.build_id || build.version || 'unknown'}`)}<div class="health-grid">${health.map((item) => `<button type="button" class="health-card ${ctx.esc(item.tone)}" data-jump-section="${item.section}" data-jump-subview="${item.subview || ''}"><span class="health-card-title">${ctx.esc(item.title)}</span><strong>${ctx.esc(item.value)}</strong><span class="health-card-status">${ctx.esc(item.status)}</span><p>${ctx.esc(item.text)}</p></button>`).join('')}</div></section>
      <div class="overview-columns overview-main-grid">
        <section class="section-block">${ctx.sectionHeading('需要处理', '只显示复核、异常和长期未更新的内容。')}<div class="attention-list">${attention.map((item) => `<button type="button" class="attention-row row-button" data-jump-section="${item.section}" data-jump-subview="${item.subview || ''}"><div><h3>${ctx.esc(item.title)}</h3><p>${ctx.esc(item.text)}</p></div>${ctx.tag(item.tone === 'danger' ? '异常' : '待处理', item.tone)}</button>`).join('') || ctx.empty('当前没有需要处理的事项。')}</div></section>
        <section class="section-block">${ctx.sectionHeading('最近 Codex 运行', '只展示当前执行器的任务活动。')}<div class="activity-list">${activity.map((item) => `<button type="button" class="activity-row row-button" data-jump-section="${item.section}" data-jump-subview="${item.subview}"><div><h3>${ctx.esc(item.title)}</h3><p>${ctx.esc(item.text)}</p></div><span>${ctx.esc(this.formatTime(item.time))}</span></button>`).join('') || ctx.empty('暂无 Codex 运行记录。')}</div></section>
      </div>
      ${ctx.tech({ overview: data, domains: domainData, diagnostics: diagnosticData, remote: remoteData })}
    </div>`;
  },

  formatTime(value) {
    const date = new Date(Number(value || 0) * 1000);
    return Number.isNaN(date.getTime()) ? '' : date.toLocaleString();
  },

  bind(ctx, root) {
    root.querySelectorAll('[data-jump-section]').forEach((button) => {
      button.onclick = () => ctx.navigate(button.dataset.jumpSection, button.dataset.jumpSubview || '');
    });
  },
};
