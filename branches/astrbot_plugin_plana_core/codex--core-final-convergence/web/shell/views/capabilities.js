window.PlanaViews = window.PlanaViews || {};

window.PlanaViews.capabilities = {
  meta: { title: 'capabilities.title', caption: 'capabilities.caption' },
  state: { items: [], selected: '', query: '', data: {}, mobileDetail: false, notice: '' },

  async render(ctx, root) {
    const response = await ctx.api('/api/domains');
    this.applyData(ctx, response.data || {});
    return this.catalog(ctx, root);
  },

  applyData(ctx, data) {
    this.state.data = data;
    this.state.items = data.domain_harness?.items || [];
    const stored = ctx.storageGet('plana_selected_domain');
    if (stored && this.state.items.some((item) => String(item.id) === stored)) this.state.selected = stored;
    else if (!this.state.items.some((item) => String(item.id) === this.state.selected)) this.state.selected = String(this.state.items[0]?.id || '');
  },

  catalog(ctx, root) {
    const data = this.state.data || {};
    const harness = data.domain_harness || {};
    const summary = harness.summary || {};
    const query = this.state.query.trim().toLowerCase();
    const items = this.state.items.filter((item) => {
      const haystack = [item.name, item.plugin_name, item.owner, item.profile, ...(item.aliases || [])].join(' ').toLowerCase();
      return !query || haystack.includes(query);
    });
    if (!items.some((item) => String(item.id) === this.state.selected)) this.state.selected = String(items[0]?.id || '');
    const selected = this.state.items.find((item) => String(item.id) === this.state.selected);
    const tone = harness.status === 'issue' || harness.status === 'unsupported' ? 'danger' : harness.status === 'empty' ? 'warn' : 'success';
    const warnings = this.duplicateWarnings(this.state.items, harness.errors || []);
    const empty = harness.status === 'issue' || harness.status === 'unsupported'
      ? ctx.empty('领域插件发现暂不可用。Core 不会回退到内置领域清单，请检查诊断信息。')
      : ctx.empty('尚未发现动态领域 descriptor。Core 保持安全空态，不创建能力占位。');
    root.innerHTML = `<div class="view-stack">
      <section class="section-block">${ctx.sectionHeading('领域集成', '业务语义只来自当前启用的领域插件；Core 负责路由、确认、授权和审计。', `<span class="status-pill ${tone}">${summary.discovered || 0} 个领域</span>`)}
        <div class="summary-grid compact-summary"><div class="summary-item"><strong>${summary.active_plugins || 0}</strong><span>已启用插件</span></div><div class="summary-item"><strong>${summary.discovered || 0}</strong><span>领域 descriptor</span></div><div class="summary-item"><strong>${summary.direct_dispatch || 0}</strong><span>直接分派</span></div><div class="summary-item"><strong>${summary.confirmation_governed || 0}</strong><span>写确认声明</span></div></div>
        ${this.state.notice ? `<div class="notice">${ctx.esc(this.state.notice)}</div>` : ''}<button class="btn" type="button" id="domain-refresh">刷新目录</button>
      </section>
      <section class="section-block">${ctx.sectionHeading('动态领域目录', '仅展示 AstrBot 当前启用插件提供的 descriptor，不提供运行时安装或能力审批入口。')}
        ${warnings.length ? `<div class="notice danger" role="alert">${warnings.map((warning) => `<p>${ctx.esc(warning)}</p>`).join('')}</div>` : ''}
        <div class="workspace ${this.state.mobileDetail ? 'mobile-detail' : ''}" id="capability-workspace"><aside class="workspace-list"><div class="workspace-toolbar"><label class="sr-only" for="capability-search">搜索领域插件</label><input id="capability-search" type="search" value="${ctx.esc(this.state.query)}" placeholder="搜索领域、插件或 profile"></div><div class="list-items" data-preserve-scroll="capability-list">${items.map((item) => this.row(ctx, item)).join('') || empty}</div></aside><article class="workspace-detail">${selected ? this.detail(ctx, selected) : empty}</article></div>
      </section>
      ${ctx.tech(data)}
    </div>`;
  },

  row(ctx, item) {
    const active = String(item.id) === this.state.selected;
    return `<button type="button" class="list-item ${active ? 'active' : ''}" data-capability="${ctx.esc(item.id)}" data-preserve-focus="domain:${ctx.esc(item.id)}"><strong>${ctx.esc(item.name || item.id)}</strong><p>${ctx.esc(item.description || item.plugin_name || '')}</p><span class="item-meta">${ctx.tag(item.status || 'active')}<span>${ctx.esc(item.owner || item.plugin_name || '')}</span></span></button>`;
  },

  detail(ctx, item) {
    const reads = item.read_operations || [];
    const writes = item.write_operations || [];
    const aliases = item.aliases || [];
    return `<button class="mobile-back" id="capability-back" type="button">← 返回领域列表</button><div class="detail-header"><div><h2>${ctx.esc(item.name || item.id)}</h2><p>${ctx.esc(item.description || '当前插件提供的领域入口。')}</p></div>${ctx.tag(item.status || 'active')}</div><section class="detail-section"><h3>所有权与路由</h3><div class="metric-row"><span>${ctx.esc(item.owner || item.plugin_name || '未声明 owner')}</span><span>${ctx.esc(item.profile || '未声明 profile')}</span><span>${ctx.esc(item.dispatch_mode || '受控分派')}</span></div></section><section class="detail-section"><h3>只读操作</h3>${reads.length ? `<ul>${reads.map((entry) => `<li>${ctx.esc(typeof entry === 'string' ? entry : entry.name || entry.capability || JSON.stringify(entry))}</li>`).join('')}</ul>` : '<p>未声明只读操作。</p>'}</section><section class="detail-section"><h3>写操作边界</h3>${writes.length ? `<ul>${writes.map((entry) => `<li>${ctx.esc(typeof entry === 'string' ? entry : entry.name || entry.capability || JSON.stringify(entry))}</li>`).join('')}</ul>` : '<p>未声明写操作。</p>'}<p>所有写操作仍需 Core proposal、策略评审和用户确认。</p></section><section class="detail-section"><h3>常用名称</h3><p>${aliases.length ? aliases.map((entry) => ctx.esc(entry)).join('、') : '未声明别名。'}</p></section>${ctx.tech(item)}`;
  },

  duplicateWarnings(items, errors) {
    const warnings = [...errors];
    [['profile', 'profile'], ['technical.tool_name', 'tool']].forEach(([path, label]) => {
      const seen = new Map();
      items.forEach((item) => {
        const value = path === 'profile' ? item.profile : item.technical?.tool_name;
        const key = String(value || '').trim().toLowerCase();
        if (!key) return;
        const owners = seen.get(key) || [];
        owners.push(item.owner || item.plugin_name || item.id || 'unknown');
        seen.set(key, owners);
      });
      seen.forEach((owners, value) => { if (owners.length > 1) warnings.push(`${label} ${value} 被多个插件声明：${owners.join('、')}`); });
    });
    return [...new Set(warnings)];
  },

  bind(ctx, root) {
    root.querySelectorAll('[data-capability]').forEach((button) => {
      button.onclick = () => ctx.preserveViewState(root, () => {
        this.state.selected = button.dataset.capability;
        this.state.mobileDetail = true;
        ctx.storageSet('plana_selected_domain', this.state.selected);
        this.catalog(ctx, root);
        this.bind(ctx, root);
      }, button.dataset.preserveFocus);
    });
    root.querySelector('#capability-search')?.addEventListener('input', (event) => {
      this.state.query = event.target.value;
      this.catalog(ctx, root);
      this.bind(ctx, root);
      root.querySelector('#capability-search')?.focus();
    });
    root.querySelector('#capability-back')?.addEventListener('click', () => {
      this.state.mobileDetail = false;
      root.querySelector('#capability-workspace')?.classList.remove('mobile-detail');
    });
    root.querySelector('#domain-refresh')?.addEventListener('click', async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      button.textContent = '正在发现…';
      try {
        const response = await ctx.api('/api/domains');
        this.applyData(ctx, response.data || {});
        this.state.notice = '领域插件发现状态已刷新。';
      } catch (error) {
        this.state.notice = `发现未完成：${error?.message || '无法读取 AstrBot 插件注册表'}`;
      }
      this.catalog(ctx, root);
      this.bind(ctx, root);
    });
  },
};
