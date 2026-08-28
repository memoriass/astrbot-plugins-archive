window.PlanaViews = window.PlanaViews || {};

window.PlanaViews.settings = {
  meta: {
    title: 'settings.title',
    caption: 'settings.caption',
    defaultSubview: 'connection',
    subviews: [
      { id: 'connection', label: 'settings.connection' },
      { id: 'maintenance', label: 'settings.maintenance' },
      { id: 'diagnostics', label: 'settings.diagnostics' },
    ],
  },

  async render(ctx, root) {
    if (ctx.activeSubview === 'maintenance') return this.maintenance(ctx, root);
    if (ctx.activeSubview === 'diagnostics') return this.diagnostics(ctx, root);
    return this.connection(ctx, root);
  },

  async connection(ctx, root) {
    const response = await ctx.api('/api/diagnostics');
    const data = response.data || {};
    const services = data.services || [];
    const overall = data.overall || {};
    const nodes = ['plana.core', 'plana.bridge', 'codex.runner', 'adapter.gateway'].map((serviceRef) => services.find((item) => item.service_ref === serviceRef)).filter(Boolean);
    const support = services.filter((item) => !nodes.some((node) => node.service_ref === item.service_ref));
    const nodeCards = nodes.map((item, index) => `${index ? '<span class="topology-arrow" aria-hidden="true">→</span>' : ''}<button type="button" class="topology-node" data-jump-section="${item.service_ref === 'adapter.gateway' ? 'resources' : item.service_ref === 'codex.runner' ? 'resources' : 'settings'}" data-jump-subview="${item.service_ref === 'adapter.gateway' ? 'gateway' : item.service_ref === 'codex.runner' ? 'remote' : 'diagnostics'}"><span>${ctx.esc(item.name)}</span><strong>${ctx.esc(item.service_ref)}</strong>${ctx.tag(this.serviceStatus(item.status), item.tone || this.serviceTone(item.status))}</button>`).join('');
    const supportRows = support.map((item) => `<article class="support-service"><div><strong>${ctx.esc(item.name)}</strong><span>${ctx.esc(item.description || item.service_ref)}</span></div>${ctx.tag(this.serviceStatus(item.status), item.tone || this.serviceTone(item.status))}</article>`).join('');
    root.innerHTML = `<div class="view-stack"><section class="section-block">${ctx.sectionHeading('服务链路', '这里只展示控制面、执行器和集成网关的总体拓扑；Adapter 和 capability 详情统一进入集成页面。', `<span class="status-pill ${overall.status === 'issue' ? 'danger' : overall.status === 'attention' ? 'warn' : 'success'}">${this.overallStatus(overall.status)}</span>`)}<div class="summary-grid compact-summary"><div class="summary-item"><strong>${overall.service_count || services.length}</strong><span>链路节点</span></div><div class="summary-item"><strong>${overall.issue_count || 0}</strong><span>连接异常</span></div><div class="summary-item"><strong>${overall.warning_count || 0}</strong><span>需要关注</span></div><div class="summary-item"><strong>${ctx.esc(data.runtime?.build?.build_id || 'unknown')}</strong><span>当前构建</span></div></div><div class="service-topology">${nodeCards || ctx.empty('尚未发现核心链路节点。')}</div>${supportRows ? `<div class="support-service-list">${supportRows}</div>` : ''}<div class="toolbar"><button type="button" class="btn primary" data-jump-section="resources" data-jump-subview="gateway">查看 Adapter Gateway</button><button type="button" class="btn" data-jump-section="settings" data-jump-subview="diagnostics">打开技术诊断</button></div></section></div>`;
  },

  serviceStatus(status) {
    return ({ active: '正常', disabled: '未启用', issue: '异常' })[status] || status || '未知';
  },

  serviceTone(status) {
    return status === 'active' ? 'success' : status === 'issue' ? 'danger' : 'warn';
  },

  detailText(detail) {
    if (detail === null || detail === undefined || detail === '') return '-';
    if (Array.isArray(detail)) return detail.map((item) => this.detailText(item)).join(', ');
    if (typeof detail === 'object') {
      const labels = { indexed: '\u5df2\u7d22\u5f15', missing: '\u7f3a\u5931', orphans: '\u5b64\u7acb\u8bb0\u5f55' };
      return Object.entries(detail).map(([key, value]) => `${labels[key] || key}: ${this.detailText(value)}`).join(' \u00b7 ');
    }
    return detail === 'ok' ? '\u6b63\u5e38' : String(detail);
  },

  maintenanceStatus(status) {
    return ({ green: '\u6b63\u5e38', yellow: '\u9700\u5173\u6ce8', red: '\u5f02\u5e38', error: '\u5f02\u5e38' })[status] || status || '-';
  },

  maintenanceCheck(name) {
    return ({
      sqlite_quick_check: '\u6570\u636e\u5e93\u53ef\u8bfb\u6027',
      schema_tables: '\u6570\u636e\u7ed3\u6784',
      memory_link_orphans: '\u8bb0\u5fc6\u5173\u8054\u5b8c\u6574\u6027',
      decay_event_orphans: '\u8870\u51cf\u8bb0\u5f55\u5173\u8054',
      memory_atom_orphans: '\u8bb0\u5fc6\u539f\u5b50\u5173\u8054',
      concept_edge_orphans: '\u56fe\u8c31\u5173\u8054\u5b8c\u6574\u6027',
      episodic_fts_consistency: '\u4e8b\u4ef6\u8bb0\u5fc6\u7d22\u5f15',
      memory_atom_fts_consistency: '\u8bb0\u5fc6\u539f\u5b50\u7d22\u5f15',
    })[name] || name || '-';
  },

  maintenanceDetail(item) {
    const detail = item?.detail;
    const orphanChecks = new Set([
      'memory_link_orphans',
      'decay_event_orphans',
      'memory_atom_orphans',
      'concept_edge_orphans',
    ]);
    if (orphanChecks.has(item?.name) && Number.isFinite(Number(detail))) {
      const count = Number(detail);
      if (count === 0) return '\u672a\u53d1\u73b0\u5f02\u5e38\u5173\u8054';
      return `\u53d1\u73b0 ${count} \u6761\u5f85\u6574\u7406\u5173\u8054`;
    }
    const emptyStructureDetail = detail === null
      || detail === undefined
      || detail === ''
      || (Array.isArray(detail) && detail.length === 0)
      || (typeof detail === 'object' && !Array.isArray(detail) && Object.keys(detail).length === 0);
    if (item?.name === 'schema_tables' && emptyStructureDetail) {
      return '\u6570\u636e\u7ed3\u6784\u5b8c\u6574';
    }
    return this.detailText(detail);
  },

  async maintenance(ctx, root) {
    const response = await ctx.api('/api/maintenance-status');
    const data = response.data || {};
    const validation = data.validation || {};
    const rows = (validation.checks || []).map((item) => `<tr><td>${ctx.esc(this.maintenanceCheck(item.name))}</td><td>${ctx.tag(this.maintenanceStatus(item.status), item.status === 'green' ? 'success' : item.status === 'yellow' ? 'warn' : 'danger')}</td><td>${ctx.esc(this.maintenanceDetail(item))}</td></tr>`).join('');
    root.innerHTML = `<div class="view-stack"><section class="section-block">${ctx.sectionHeading('\u6570\u636e\u7ef4\u62a4', '\u5907\u4efd\u548c\u7d22\u5f15\u7ef4\u62a4\u5747\u5728\u672c\u673a\u6267\u884c\uff0c\u64cd\u4f5c\u524d\u9700\u8981\u4e8c\u6b21\u786e\u8ba4\u3002')}<div class="summary-grid"><div class="summary-item"><strong>${this.maintenanceStatus(validation.status)}</strong><span>\u5065\u5eb7\u68c0\u67e5</span></div><div class="summary-item"><strong>${(data.backups || []).length}</strong><span>\u53ef\u7528\u5907\u4efd</span></div><div class="summary-item"><strong>${Object.keys(data.tables || {}).length}</strong><span>\u6570\u636e\u8868</span></div><div class="summary-item"><strong>${data.jobs?.running || 0}</strong><span>\u8fd0\u884c\u4e2d\u4efb\u52a1</span></div></div><div class="toolbar"><button class="btn primary" id="maintain-run" type="button">\u68c0\u67e5\u5e76\u4fee\u590d</button><button class="btn" id="maintain-backup" type="button">\u7acb\u5373\u5907\u4efd</button><button class="btn" id="maintain-rebuild" type="button">\u91cd\u5efa\u7d22\u5f15</button></div><div id="maintenance-result" class="page-status" role="status" aria-live="polite"></div>${ctx.table(['\u68c0\u67e5\u9879', '\u72b6\u6001', '\u8bf4\u660e'], rows)}${ctx.tech(data)}</section></div>`;
  },

  async diagnostics(ctx, root) {
    const response = await ctx.api('/api/diagnostics');
    const data = response.data || {};
    const overall = data.overall || {};
    const runtime = data.runtime || {};
    const governance = data.governance || {};
    const remote = governance.remote_tasks || {};
    const dataHealth = data.data_health || {};
    const validation = dataHealth.validation || {};
    const services = (data.services || []).map((item) => `<article class="connection-card"><div><span class="connection-kicker">${ctx.esc(item.service_ref || item.resource_id)}</span><h3>${ctx.esc(item.name)}</h3></div>${ctx.tag(this.serviceStatus(item.status), item.tone || this.serviceTone(item.status))}<p>${ctx.esc(item.description || '运行时服务')}</p><small>${ctx.esc(item.error || `状态证据更新时间：${this.formatTime(item.updated_at)}`)}</small></article>`).join('');
    const findings = (data.findings || []).map((item) => `<button type="button" class="diagnostic-finding row-button" data-jump-section="${ctx.esc(item.section || 'settings')}" data-jump-subview="${ctx.esc(item.subview || '')}"><span class="finding-mark ${ctx.esc(item.tone || 'neutral')}"></span><div><h3>${ctx.esc(item.title)}</h3><p>${ctx.esc(item.text)}</p></div>${ctx.tag(item.tone === 'danger' ? '异常' : '需关注', item.tone || 'neutral')}</button>`).join('');
    const audits = (data.recent_audit || []).slice(0, 8).map((item) => `<div class="audit-line"><div><strong>${ctx.esc(this.auditAction(item.action))}</strong><span>${ctx.esc(item.target_type || 'system')} · ${ctx.esc(item.actor || 'system')}</span></div><time>${ctx.esc(this.formatTime(item.created_at))}</time></div>`).join('');
    root.innerHTML = `<div class="view-stack diagnostics-view"><section class="section-block">${ctx.sectionHeading('技术诊断', '用真实运行证据定位陪伴服务、Memory Warehouse、Codex Runner 和数据健康问题。', `<span class="status-pill ${overall.status === 'issue' ? 'danger' : overall.status === 'attention' ? 'warn' : 'success'}">${this.overallStatus(overall.status)}</span>`)}<div class="diagnostic-hero"><div><span>诊断快照</span><strong>${overall.issue_count || 0}</strong><small>异常</small></div><div><span>需要关注</span><strong>${overall.warning_count || 0}</strong><small>警告或待处理</small></div><div><span>服务链路</span><strong>${overall.service_count || 0}</strong><small>已纳管节点</small></div><div><span>当前构建</span><strong class="build-value">${ctx.esc(runtime.build?.build_id || runtime.build?.version || 'unknown')}</strong><small>${ctx.esc(this.formatTime(data.generated_at))}</small></div></div></section><section class="section-block">${ctx.sectionHeading('服务链路', '区分未启用、真实失联和历史任务残留。')}<div class="diagnostic-service-grid">${services || ctx.empty('没有可展示的服务证据。')}</div></section><div class="diagnostic-columns"><section class="section-block diagnostic-panel">${ctx.sectionHeading('Codex Runner', '只展示当前执行器的注册边界、运行状态和失联证据。')}<dl class="status-list"><div><dt>已注册能力</dt><dd>${governance.registered_capabilities || 0}</dd></div><div><dt>当前允许能力</dt><dd>${governance.allowed_capabilities || 0}</dd></div><div><dt>Codex 运行中</dt><dd>${remote.active || 0}</dd></div><div><dt>Codex 已完成</dt><dd>${remote.completed || 0}</dd></div><div><dt>Codex 长时未更新</dt><dd>${ctx.tag(`${remote.stale || 0} 项`, remote.stale ? 'danger' : 'success')}</dd></div></dl><button type="button" class="btn" data-jump-section="resources" data-jump-subview="remote">查看运行详情</button></section><section class="section-block diagnostic-panel">${ctx.sectionHeading('数据健康', 'SQLite、索引、关联完整性和备份状态。')}<dl class="status-list"><div><dt>检查状态</dt><dd>${ctx.tag(this.maintenanceStatus(validation.status), validation.status === 'green' ? 'success' : 'warn')}</dd></div><div><dt>检查项目</dt><dd>${(validation.checks || []).length}</dd></div><div><dt>数据表</dt><dd>${Object.keys(dataHealth.tables || {}).length}</dd></div><div><dt>可用备份</dt><dd>${dataHealth.backups || 0}</dd></div><div><dt>运行任务</dt><dd>${runtime.jobs?.running || 0}</dd></div></dl><button type="button" class="btn" data-jump-section="settings" data-jump-subview="maintenance">打开数据维护</button></section></div><div class="diagnostic-columns"><section class="section-block diagnostic-panel">${ctx.sectionHeading('诊断结论', '只列出当前证据支持的异常和待处理项。')}<div class="diagnostic-findings">${findings || ctx.empty('当前未发现需要处理的诊断项。')}</div></section><section class="section-block diagnostic-panel">${ctx.sectionHeading('近期维护审计', '展示删除、清理、重建等受控操作记录。')}<div class="audit-lines">${audits || ctx.empty('暂无维护审计记录。')}</div></section></div><section class="section-block"><div class="notice warn">技术附录可能包含内部路径、策略和局域网服务信息，仅在排障时展开；页面不会展示密钥。</div>${ctx.tech(data.technical || {})}</section></div>`;
  },

  overallStatus(status) {
    return ({ healthy: '运行正常', attention: '需要关注', issue: '存在异常' })[status] || '状态未知';
  },

  auditAction(action) {
    return ({ backup: '创建备份', rebuild_indexes: '重建索引', clean_orphans: '清理孤立记录', delete_memory: '删除记忆', delete_semantic: '删除语义记录' })[action] || action || '维护操作';
  },

  formatTime(value) {
    const date = new Date(Number(value || 0) * 1000);
    return Number.isNaN(date.getTime()) || !Number(value) ? '无时间证据' : date.toLocaleString();
  },

  bind(ctx, root) {
    root.querySelectorAll('[data-jump-section]').forEach((button) => {
      button.onclick = () => ctx.navigate(button.dataset.jumpSection, button.dataset.jumpSubview || '');
    });
    const resultNode = root.querySelector('#maintenance-result');
    const run = async (path, body) => {
      const result = await ctx.api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      resultNode.innerHTML = `<div class="notice">\u64cd\u4f5c\u5df2\u5b8c\u6210\u3002</div>${ctx.tech(result)}`;
    };
    const confirmAction = (button, label, action) => {
      button.onclick = async () => {
        if (button.dataset.confirmed !== 'true') {
          button.dataset.confirmed = 'true';
          button.dataset.originalLabel = button.textContent;
          button.textContent = label;
          button.classList.add('primary');
          return;
        }
        button.disabled = true;
        try {
          await action();
        } catch (error) {
          button.disabled = false;
          button.dataset.confirmed = '';
          button.textContent = button.dataset.originalLabel || button.textContent;
          resultNode.textContent = `\u64cd\u4f5c\u5931\u8d25\uff1a${error?.message || '\u672a\u77e5\u9519\u8bef'}`;
        }
      };
    };
    const maintain = root.querySelector('#maintain-run');
    if (maintain) confirmAction(maintain, '\u518d\u6b21\u70b9\u51fb\u786e\u8ba4\u4fee\u590d', () => run('/api/maintain', { confirm: true }));
    const backup = root.querySelector('#maintain-backup');
    if (backup) confirmAction(backup, '\u518d\u6b21\u70b9\u51fb\u786e\u8ba4\u5907\u4efd', () => run('/api/backup', { confirm: true, reason: 'web-manual' }));
    const rebuild = root.querySelector('#maintain-rebuild');
    if (rebuild) confirmAction(rebuild, '\u518d\u6b21\u70b9\u51fb\u786e\u8ba4\u91cd\u5efa', () => run('/api/rebuild-indexes', { confirm: true }));
    root.onkeydown = (event) => {
      if (event.key !== 'Escape') return;
      root.querySelectorAll('[data-confirmed="true"]').forEach((button) => {
        button.dataset.confirmed = '';
        button.classList.remove('primary');
        button.textContent = button.dataset.originalLabel || button.textContent;
      });
    };
  },
};
