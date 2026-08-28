window.PlanaViews = window.PlanaViews || {};

window.PlanaViews.tasks = {
  meta: {
    title: 'tasks.title',
    caption: 'tasks.caption',
    defaultSubview: 'approvals',
    subviews: [
      { id: 'approvals', label: 'tasks.approvals' },
      { id: 'todos', label: 'tasks.todos' },
      { id: 'codex', label: 'tasks.codex' },
    ],
  },

  async render(ctx, root) {
    if (ctx.activeSubview === 'todos') return this.todos(ctx, root);
    if (ctx.activeSubview === 'codex') return this.codex(ctx, root);
    return this.approvals(ctx, root);
  },

  async approvals(ctx, root) {
    const response = await ctx.api('/api/feedback?scope=global&limit=80');
    const items = (response.items || []).filter((item) => item.status === 'pending');
    const rows = items.map((item) => `<article class="info-strip"><div><strong>${ctx.esc(item.title || item.kind || '记忆复核')}</strong><p>${ctx.esc(item.content || item.payload?.content || '等待检查后应用或忽略。')}</p></div>${ctx.tag(item.status, 'warn')}</article>`).join('');
    root.innerHTML = `<div class="view-stack"><section class="section-block">${ctx.sectionHeading('待复核事项', '这里只汇总需要人工判断的记忆建议；具体修改与应用在记忆页完成。', `<span class="status-pill ${items.length ? 'warn' : 'success'}">${items.length} 项</span>`)}${rows ? `<div class="strip-list">${rows}</div>` : ctx.empty('当前没有待复核事项。')}<div class="toolbar"><button class="btn primary" type="button" data-jump-section="memory" data-jump-subview="quality">打开记忆复核</button></div></section></div>`;
  },

  async todos(ctx, root) {
    const [tasks, proactive] = await Promise.all([
      ctx.api('/api/tasks?scope=global&limit=80'),
      ctx.api('/api/proactive?scope=global&limit=40'),
    ]);
    const taskItems = tasks.data || tasks.tasks || [];
    const proactiveItems = proactive.tasks || [];
    const rows = [
      ...taskItems.map((item) => `<tr><td>${ctx.esc(item.title || item.content)}</td><td>${ctx.tag(item.status)}</td><td>${ctx.esc(this.sourceLabel(item.source))}</td><td>${ctx.esc(this.formatTime(item.updated_at || item.created_at))}</td></tr>`),
      ...proactiveItems.map((item) => `<tr><td>${ctx.esc(item.payload || item.kind)}</td><td>${ctx.tag(item.status)}</td><td>主动任务</td><td>${ctx.esc(this.formatTime(item.updated_at || item.created_at))}</td></tr>`),
    ].join('');
    root.innerHTML = `<div class="view-stack"><section class="section-block">${ctx.sectionHeading('待办与主动任务', '展示陪伴侧待办、提醒和后台任务状态。')}${ctx.table(['事项', '状态', '来源', '更新时间'], rows)}</section></div>`;
  },

  async codex(ctx, root) {
    const response = await ctx.api('/api/remote-tasks?limit=50');
    const data = response.data || {};
    const items = data.display_items || [];
    const rows = items.map((item) => {
      const display = item.display || {};
      return `<tr><td>${ctx.esc(display.title || '未命名任务')}</td><td>${ctx.tag(display.status || item.status, display.tone || '')}</td><td>${ctx.esc(display.lane || '交互任务')}</td><td>${ctx.esc(display.duration || '')}</td></tr>`;
    }).join('');
    root.innerHTML = `<div class="view-stack"><section class="section-block">${ctx.sectionHeading('Codex 运行', '展示当前 Runner 的任务状态；取消、结果和技术详情在集成与运行页处理。')}${ctx.table(['任务', '状态', '通道', '持续时间'], rows)}<div class="toolbar"><button class="btn primary" type="button" data-jump-section="resources" data-jump-subview="remote">打开运行详情</button></div></section>${ctx.tech(data)}</div>`;
  },

  sourceLabel(value) {
    return ({ user: '用户', assistant: 'Plana', proactive: '主动任务', imported: '导入' })[value] || value || '系统';
  },

  formatTime(value) {
    if (!value) return '-';
    const numeric = Number(value);
    const date = new Date(numeric < 1000000000000 ? numeric * 1000 : numeric);
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
  },

  bind(ctx, root) {
    root.querySelectorAll('[data-jump-section]').forEach((button) => {
      button.onclick = () => ctx.navigate(button.dataset.jumpSection, button.dataset.jumpSubview || '');
    });
  },
};
