window.PlanaViews = window.PlanaViews || {};

window.PlanaViews.resources = {
  meta: {
    title: 'resources.title',
    caption: 'resources.caption',
    defaultSubview: 'gateway',
    subviews: [
      { id: 'gateway', label: 'resources.gateway' },
      { id: 'webhook', label: 'Webhook' },
      { id: 'bindings', label: 'resources.bindings' },
      { id: 'remote', label: 'resources.remote' },
    ],
  },
  state: {
    selectedAdapter: '',
    adapterQuery: '',
    selectedResource: '',
    resourceQuery: '',
    selectedTask: '',
    taskFilter: 'active',
    taskQuery: '',
    remoteNotice: '',
    integrations: {},
    webhook: {},
    webhookNotice: '',
    data: {},
    tasks: {},
  },

  async render(ctx, root) {
    if (ctx.activeSubview === 'webhook') {
      const response = await ctx.api('/api/webhook?limit=80');
      this.state.webhook = response.data || {};
      return this.webhook(ctx, root);
    }
    if (ctx.activeSubview === 'remote') {
      const response = await ctx.api('/api/remote-tasks?limit=50');
      this.state.tasks = response.data || {};
      return this.remote(ctx, root);
    }
    if (ctx.activeSubview === 'bindings') {
      const response = await ctx.api('/api/resources?limit=120');
      this.state.data = response.data || {};
      return this.bindings(ctx, root);
    }
    const response = await ctx.api('/api/integrations');
    this.state.integrations = response.data || {};
    return this.gateway(ctx, root);
  },

  gateway(ctx, root) {
    const data = this.state.integrations || {};
    const gateway = data.gateway || {};
    const adapters = data.adapters || [];
    const summary = data.summary || {};
    if (!this.state.selectedAdapter && adapters.length) this.state.selectedAdapter = adapters[0].service_ref;
    const selected = adapters.find((item) => item.service_ref === this.state.selectedAdapter) || adapters[0];
    const tone = gateway.status === 'active' ? 'success' : 'danger';
    const meta = `<span class="status-pill ${tone}">${ctx.esc(gateway.host || '202')} · ${ctx.esc(ctx.label(gateway.status || 'issue'))}</span>`;
    const heading = this.text(ctx, 'gateway.title', 'Adapter Gateway');
    const caption = this.text(ctx, 'gateway.caption', 'Review fixed adapters, credentials, and governed capabilities on 202.');
    const search = this.text(ctx, 'gateway.search', 'Search services or capabilities');
    root.innerHTML = `<div class="view-stack"><section class="section-block">${ctx.sectionHeading(heading, caption, meta)}<div class="summary-grid compact-summary"><div class="summary-item"><strong>${summary.adapters || 0}</strong><span>${ctx.esc(this.text(ctx, 'gateway.summary.adapters', 'Adapters'))}</span></div><div class="summary-item"><strong>${summary.capabilities || 0}</strong><span>${ctx.esc(this.text(ctx, 'gateway.summary.capabilities', 'Capabilities'))}</span></div><div class="summary-item"><strong>${summary.available || 0}</strong><span>${ctx.esc(this.text(ctx, 'gateway.summary.available', 'Available'))}</span></div><div class="summary-item"><strong>${summary.issues || 0}</strong><span>${ctx.esc(this.text(ctx, 'gateway.summary.issues', 'Issues'))}</span></div></div><div class="notice">${ctx.esc(this.text(ctx, 'gateway.governance_notice', 'Gateway owns fixed protocols and credential isolation. Core retains authorization, confirmation, audit, and final execution authority.'))}</div></section>${adapters.length ? `<div class="workspace integration-workspace"><aside class="workspace-list"><div class="workspace-toolbar"><label class="sr-only" for="adapter-search">${ctx.esc(search)}</label><input id="adapter-search" type="search" value="${ctx.esc(this.state.adapterQuery)}" placeholder="${ctx.esc(search)}"></div><div class="list-items" data-preserve-scroll="adapter-list">${adapters.map((item) => `<button type="button" class="list-item ${item.service_ref === this.state.selectedAdapter ? 'active' : ''}" data-adapter="${ctx.esc(item.service_ref)}" data-preserve-focus="adapter:${ctx.esc(item.service_ref)}"><strong>${ctx.esc(item.name || item.service_ref)}</strong><p>${ctx.esc(this.adapterDescription(ctx, item))}</p><span class="item-meta">${ctx.tag(ctx.label(item.status), this.availabilityTone(item.status))}<span>${item.available_count || 0}/${item.capability_count || 0} ${ctx.esc(this.text(ctx, 'gateway.available_short', 'available'))}</span></span></button>`).join('')}<p class="search-empty" data-adapter-empty hidden>${ctx.esc(this.text(ctx, 'gateway.search_empty', 'No matching adapters or capabilities.'))}</p></div></aside><article class="workspace-detail">${this.gatewayDetail(ctx, selected)}</article></div>` : ctx.empty(this.text(ctx, 'gateway.empty', 'No service adapters are registered.'))}${ctx.tech(data.technical || data)}</div>`;
  },

  webhook(ctx, root) {
    const data = this.state.webhook || {};
    const status = data.status || {};
    const companion = status.companion || {};
    const sources = data.sources || [];
    const events = data.events || [];
    const tone = status.ok ? 'success' : 'danger';
    const sourceCards = sources.map((item) => {
      const policy = item.policy || {};
      const enabled = Boolean(Number(policy.enabled ?? 1));
      const action = policy.action || 'deliver';
      return `<article class="integration-card"><div class="integration-card-head"><div><strong>${ctx.esc(item.source || 'unknown')}</strong><p>${ctx.esc((item.routes || []).join(' · ') || '未注册入口')}</p></div>${ctx.tag(enabled ? '已启用' : '已停用', enabled ? 'success' : 'danger')}</div><div class="detail-grid"><span><small>策略</small><strong>${ctx.esc(action)}</strong></span><span><small>模板</small><strong>${ctx.esc(policy.template || item.template || '沿用插件')}</strong></span><span><small>目标</small><strong>${ctx.esc(policy.target || '沿用插件')}</strong></span><span><small>聚合</small><strong>${Number(policy.aggregate_seconds || 0)} 秒</strong></span></div><div class="detail-actions"><button class="btn" type="button" data-webhook-toggle="${ctx.esc(item.source)}" data-enabled="${enabled ? '1' : '0'}">${enabled ? '停用来源' : '启用来源'}</button></div></article>`;
    }).join('');
    const eventRows = events.map((item) => `<article class="info-strip"><div><strong>${ctx.esc(item.summary || item.event_type || item.event_id)}</strong><p>${ctx.esc(item.source || '')} · ${ctx.esc(item.delivery_status || item.status || 'pending')} · ${ctx.esc(item.event_id || '')}</p></div><div>${ctx.tag(item.delivery_status || item.status || 'pending', item.delivery_status === 'failed' ? 'danger' : item.delivery_status === 'delivered' ? 'success' : 'warn')}${item.delivery_status === 'failed' ? `<button class="btn" type="button" data-webhook-replay="${ctx.esc(item.event_id)}">确认重放</button>` : ''}</div></article>`).join('');
    root.innerHTML = `<div class="view-stack"><section class="section-block">${ctx.sectionHeading('Webhook 推送附属插件', '外部 Webhook 接收保持开放；Plana 专用密钥只保护策略、审计与重放治理调用。', `<span class="status-pill ${tone}">${ctx.esc(companion.listen_port ? `201:${companion.listen_port}` : '插件未连接')} · ${status.events || 0} 个事件</span>`)}<div class="summary-grid compact-summary"><div class="summary-item"><strong>${sources.length}</strong><span>来源</span></div><div class="summary-item"><strong>${status.delivered || 0}</strong><span>已投递</span></div><div class="summary-item"><strong>${status.failed || 0}</strong><span>失败</span></div><div class="summary-item"><strong>${companion.queue_messages || 0}</strong><span>待处理</span></div></div>${companion.core_auth_configured === false || companion.error === 'core_service_unauthorized' ? '<div class="notice">Core 专用验证 token 未配置或不一致；治理功能已拒绝访问，Webhook 原始接收与投递仍保持可用。</div>' : ''}${this.state.webhookNotice ? `<div class="notice">${ctx.esc(this.state.webhookNotice)}</div>` : ''}</section><section class="section-block"><h2>来源策略</h2><div class="integration-grid">${sourceCards || ctx.empty('Webhook 插件尚未加载。')}</div></section><section class="section-block"><h2>脱敏事件审计</h2>${eventRows || ctx.empty('暂无 Webhook 事件。')}</section>${ctx.tech(data)}</div>`;
  },

  gatewayDetail(ctx, item) {
    if (!item) return ctx.empty(this.text(ctx, 'gateway.select_adapter', 'Select a service adapter.'));
    const capabilities = item.capabilities || [];
    const credential = this.credentialLabel(ctx, item.credential_status);
    const auth = this.text(ctx, item.authentication_key, item.authentication || '-');
    const trust = this.text(ctx, item.trust_boundary_key, item.trust_boundary || '-');
    const ownership = this.text(ctx, `gateway.management.${item.management || 'controlled'}`, item.management || 'controlled');
    const related = this.relatedResources(ctx, item.child_resources || []);
    return `<div class="detail-header"><div><h2>${ctx.esc(item.name || item.service_ref)}</h2><p>${ctx.esc(this.adapterDescription(ctx, item))}</p></div>${ctx.tag(ctx.label(item.status), this.availabilityTone(item.status))}</div><section class="detail-section"><h3>${ctx.esc(this.text(ctx, 'gateway.connection_boundary', 'Connection boundary'))}</h3><div class="integration-facts"><div><span>${ctx.esc(this.text(ctx, 'gateway.fact.service_ref', 'Service reference'))}</span><strong>${ctx.esc(item.service_ref)}</strong></div><div><span>${ctx.esc(this.text(ctx, 'gateway.fact.target', 'Target system'))}</span><strong>${ctx.esc(item.target)}</strong></div><div><span>${ctx.esc(this.text(ctx, 'gateway.fact.deployment', 'Deployment'))}</span><strong>${ctx.esc(item.deployment || '-')}</strong></div><div><span>${ctx.esc(this.text(ctx, 'gateway.fact.protocol', 'Protocol'))}</span><strong>${ctx.esc(item.protocol || '-')}</strong></div><div><span>${ctx.esc(this.text(ctx, 'gateway.fact.authentication', 'Authentication'))}</span><strong>${ctx.esc(auth)}</strong></div><div><span>${ctx.esc(this.text(ctx, 'gateway.fact.trust', 'Trust boundary'))}</span><strong>${ctx.esc(trust)}</strong></div><div><span>${ctx.esc(this.text(ctx, 'gateway.fact.management', 'Management'))}</span><strong>${ctx.esc(ownership)}</strong></div><div><span>${ctx.esc(this.text(ctx, 'gateway.fact.owner', 'Owner'))}</span><strong>${ctx.esc(item.owner || 'core')}</strong></div></div></section>${related}<section class="detail-section"><h3>${ctx.esc(this.text(ctx, 'gateway.readiness', 'Readiness'))}</h3><div class="gateway-readiness"><div><span>${ctx.esc(this.text(ctx, 'gateway.credential_status', 'Credential status'))}</span><strong>${ctx.esc(credential)}</strong></div><div><span>${ctx.esc(this.text(ctx, 'gateway.health_probe', 'Representative health probe'))}</span><strong>${ctx.esc(item.health_capability || '-')}</strong></div><div><span>${ctx.esc(this.text(ctx, 'gateway.read_only_coverage', 'Read-only coverage'))}</span><strong>${item.read_only_count || 0}/${item.capability_count || 0}</strong></div><div><span>${ctx.esc(this.text(ctx, 'gateway.artifact_count', 'Artifact capabilities'))}</span><strong>${item.artifact_count || 0}</strong></div></div></section><section class="detail-section"><h3>${ctx.esc(this.text(ctx, 'gateway.capabilities', 'Capabilities'))}</h3>${capabilities.length ? `<div class="integration-capability-list">${capabilities.map((capability) => this.capabilityCard(ctx, capability)).join('')}</div>` : `<p>${ctx.esc(this.text(ctx, item.management === 'protected' ? 'gateway.protected_no_capabilities' : 'gateway.no_capabilities', 'No capabilities are registered.'))}</p>`}</section>${ctx.tech(item)}`;
  },

  relatedResources(ctx, resources) {
    if (!resources.length) return '';
    const rows = resources.map((resource) => {
      const management = this.text(ctx, `gateway.management.${resource.management || 'read_only_external'}`, resource.management || 'read_only_external');
      return `<div><span>${ctx.esc(resource.service_ref || '-')}</span><strong>${ctx.esc(resource.owner || '-')} · ${ctx.esc(management)}</strong><small>${ctx.esc(resource.endpoint_role || this.text(ctx, 'gateway.related_resource_default', 'Related service resource'))}</small></div>`;
    }).join('');
    return `<section class="detail-section"><h3>${ctx.esc(this.text(ctx, 'gateway.related_resources', 'Related resources'))}</h3><p>${ctx.esc(this.text(ctx, 'gateway.related_resources_caption', 'These resources are exposed through the parent service route and do not create a second managed adapter.'))}</p><div class="integration-facts">${rows}</div></section>`;
  },

  capabilityCard(ctx, capability) {
    const copyKey = capability.copy_key || 'gateway.capability.generic';
    const title = this.text(ctx, `${copyKey}.title`, capability.capability);
    const description = this.text(ctx, `${copyKey}.description`, capability.capability);
    const category = this.text(ctx, `gateway.category.${capability.category || 'other'}`, capability.category || 'other');
    const result = this.text(ctx, `gateway.result.${capability.result_type || 'normalized_json'}`, capability.result_type || 'normalized JSON');
    const probe = capability.derived
      ? this.text(ctx, 'gateway.probe.derived', 'Availability is derived from the representative adapter probe; this operation is not executed automatically.')
      : this.text(ctx, 'gateway.probe.direct', 'This read-only capability is used as the representative live probe.');
    const argumentsHtml = (capability.arguments || []).length
      ? `<div class="gateway-arguments">${capability.arguments.map((argument) => `<span class="gateway-argument"><strong>${ctx.esc(this.argumentName(ctx, argument.name))}</strong><small>${ctx.esc(this.argumentConstraint(ctx, argument))}</small></span>`).join('')}</div>`
      : `<span class="gateway-no-arguments">${ctx.esc(this.text(ctx, 'gateway.arguments.none', 'No arguments'))}</span>`;
    const limitations = (capability.limitations || []).length
      ? `<ul class="gateway-limitations">${capability.limitations.map((item) => `<li>${ctx.esc(item)}</li>`).join('')}</ul>`
      : '';
    return `<details class="integration-capability" ${capability.availability === 'issue' ? 'open' : ''}><summary><span><strong>${ctx.esc(title)}</strong><code>${ctx.esc(capability.capability)}</code></span><span class="capability-summary-meta">${ctx.tag(category)}${ctx.tag(ctx.label(capability.availability), this.availabilityTone(capability.availability))}</span></summary><div class="integration-capability-body"><p>${ctx.esc(description)}</p><div class="capability-contract"><span><small>${ctx.esc(this.text(ctx, 'gateway.contract.result', 'Result'))}</small><strong>${ctx.esc(result)}</strong></span><span><small>${ctx.esc(this.text(ctx, 'gateway.contract.mode', 'Mode'))}</small><strong>${ctx.esc(this.text(ctx, 'gateway.mode.synchronous', 'Synchronous'))}</strong></span><span><small>${ctx.esc(this.text(ctx, 'gateway.contract.confirmation', 'Confirmation'))}</small><strong>${ctx.esc(this.text(ctx, `gateway.confirmation.${capability.confirmation || 'core_required'}`, capability.confirmation || 'Core required'))}</strong></span><span><small>${ctx.esc(this.text(ctx, 'gateway.contract.output', 'Output'))}</small><strong>${ctx.esc(this.text(ctx, capability.artifact ? 'gateway.output.artifact' : 'gateway.output.json', capability.artifact ? 'Artifact + JSON' : 'Normalized JSON'))}</strong></span></div><div><h4>${ctx.esc(this.text(ctx, 'gateway.arguments', 'Arguments'))}</h4>${argumentsHtml}${(capability.require_one_of || []).length ? `<p class="gateway-argument-note">${ctx.esc(this.text(ctx, 'gateway.arguments.one_of', 'At least one is required'))}: ${ctx.esc(capability.require_one_of.map((name) => this.argumentName(ctx, name)).join(' / '))}</p>` : ''}</div><div class="gateway-probe-note"><strong>${ctx.esc(this.text(ctx, 'gateway.probe.title', 'Health evidence'))}</strong><p>${ctx.esc(probe)} ${ctx.esc(capability.probe_capability || '')}</p></div>${limitations}</div></details>`;
  },

  adapterDescription(ctx, item) {
    return this.text(ctx, `${item.copy_key || 'gateway.adapter.generic'}.description`, item.name || item.service_ref);
  },

  credentialLabel(ctx, value) {
    return this.text(ctx, `gateway.credential.${value || 'unknown'}`, value || 'unknown');
  },

  argumentName(ctx, name) {
    return this.text(ctx, `gateway.argument.${name}`, name || '-');
  },

  argumentConstraint(ctx, argument) {
    const parts = [this.text(ctx, `gateway.type.${argument.type || 'string'}`, argument.type || 'string')];
    parts.push(this.text(ctx, argument.required ? 'gateway.required' : 'gateway.optional', argument.required ? 'required' : 'optional'));
    if (Object.prototype.hasOwnProperty.call(argument, 'default')) parts.push(`${this.text(ctx, 'gateway.default', 'default')} ${argument.default}`);
    if (argument.minimum !== undefined || argument.maximum !== undefined) parts.push(`${argument.minimum ?? '–'}…${argument.maximum ?? '–'}`);
    return parts.join(' · ');
  },

  text(ctx, key, fallback) {
    const value = ctx.t(key);
    return value === key ? fallback : value;
  },

  bindings(ctx, root) {
    const data = this.state.data || {};
    const items = (data.resources || []).filter((item) => item.source !== 'runtime');
    const services = new Map((data.services || []).map((item) => [item.service_ref, item]));
    if (!this.state.selectedResource && items.length) this.state.selectedResource = items[0].resource_id;
    const selected = items.find((item) => item.resource_id === this.state.selectedResource) || items[0];
    const meta = `<span class="status-pill">${items.length} 个持久资源</span>`;
    root.innerHTML = `<div class="view-stack"><section class="section-block">${ctx.sectionHeading('资源绑定', '查看 Core 持久化的资源、主体权限和语义别名；运行节点状态不在这里重复展示。', meta)}</section>${items.length ? `<div class="workspace" id="resource-workspace"><aside class="workspace-list"><div class="workspace-toolbar"><input id="resource-search" type="search" value="${ctx.esc(this.state.resourceQuery)}" placeholder="搜索资源或别名"></div><div class="list-items" data-preserve-scroll="resource-list">${items.map((item) => `<button type="button" class="list-item ${item.resource_id === this.state.selectedResource ? 'active' : ''}" data-resource="${ctx.esc(item.resource_id)}" data-preserve-focus="resource:${ctx.esc(item.resource_id)}"><strong>${ctx.esc(item.display_name || '未命名资源')}</strong><p>${ctx.esc(item.description || this.typeLabel(item.resource_type))}</p><span class="item-meta">${ctx.tag(item.status, item.status === 'active' ? 'success' : item.status === 'issue' ? 'danger' : 'warn')}<span>${ctx.esc(this.typeLabel(services.get(item.service_ref)?.service_type))}</span></span></button>`).join('')}</div></aside><article class="workspace-detail">${this.resourceDetail(ctx, selected, services.get(selected?.service_ref))}</article></div>` : ctx.empty('当前没有持久化资源绑定。运行服务和 Adapter 请前往“Adapter Gateway”。')}</div>`;
  },

  resourceDetail(ctx, item, service) {
    if (!item) return ctx.empty('请选择一个资源。');
    const data = this.state.data || {};
    const bindings = (data.bindings || []).filter((entry) => entry.resource_id === item.resource_id);
    const aliases = (data.aliases || []).filter((entry) => entry.resource_id === item.resource_id);
    const metadata = item.metadata || {};
    const model = metadata.model ? `<span>主模型 ${ctx.esc(metadata.model)}</span>` : '';
    const fallbacks = Array.isArray(metadata.fallback_models) && metadata.fallback_models.length ? `<span>备用 ${ctx.esc(metadata.fallback_models.join('、'))}</span>` : '';
    const contract = metadata.task_skill_contract ? `<span>任务包约束 ${ctx.esc(metadata.task_skill_contract)}</span>` : '';
    const healthError = metadata.health_error || metadata.health?.error || metadata.status?.last_error || '';
    return `<div class="detail-header"><div><h2>${ctx.esc(item.display_name || '未命名资源')}</h2><p>${ctx.esc(item.description || `${this.typeLabel(item.resource_type)} · ${this.typeLabel(service?.service_type)}`)}</p></div>${ctx.tag(item.status, item.status === 'active' ? 'success' : item.status === 'issue' ? 'danger' : 'warn')}</div>${model || fallbacks || contract ? `<section class="detail-section"><h3>运行配置</h3><div class="metric-row">${model}${fallbacks}${contract}</div></section>` : ''}${healthError ? `<section class="detail-section"><h3>连接异常</h3><p>${ctx.esc(healthError)}</p></section>` : ''}<section class="detail-section"><h3>访问边界</h3>${bindings.length ? `<ul>${bindings.map((entry) => `<li>${ctx.esc(entry.subject_name || '已授权用户')} · ${ctx.esc(this.permissionLabel(entry.permissions))}</li>`).join('')}</ul>` : `<p>${item.read_only ? '该卡片仅展示运行状态；执行、写入和外部发送仍由 Core 的 capability、确认与审计策略控制。' : '尚未建立访问关系。'}</p>`}</section><section class="detail-section"><h3>常用名称</h3>${aliases.length ? `<ul>${aliases.map((entry) => `<li>${ctx.esc(entry.alias)}</li>`).join('')}</ul>` : '<p>没有登记别名。</p>'}</section>${ctx.tech({ resource: item, service, bindings, aliases })}`;
  },

  remote(ctx, root) {
    const data = this.state.tasks || {};
    const allItems = data.display_items || [];
    const query = this.state.taskQuery.trim().toLowerCase();
    const items = allItems.filter((item) => {
      const display = item.display || {};
      return (!query || String(display.title || '').toLowerCase().includes(query))
        && (this.state.taskFilter === 'all' || display.category === this.state.taskFilter);
    });
    if (!items.some((item) => item.request_id === this.state.selectedTask)) this.state.selectedTask = items[0]?.request_id || '';
    const selected = allItems.find((item) => item.request_id === this.state.selectedTask) || items[0];
    const summary = data.summary || {};
    const executor = summary.executor || {};
    root.innerHTML = `<div class="view-stack"><section class="section-block">${ctx.sectionHeading('远程任务', `查看 ${executor.label || 'Codex CLI'} 任务的等待、结果和失败原因。`, `<span class="status-pill ${summary.stale ? 'danger' : summary.active ? 'warn' : 'success'}">${summary.active || 0} 项进行中 · ${summary.stale || 0} 项可能失联</span>`)}</section><div id="remote-result" class="page-status" role="status" aria-live="polite">${ctx.esc(this.state.remoteNotice || '')}</div><div class="workspace remote-workspace"><aside class="workspace-list"><div class="workspace-toolbar"><input id="remote-search" type="search" value="${ctx.esc(this.state.taskQuery)}" placeholder="搜索远程任务"><div class="filter-row">${[['active', '进行中'], ['completed', '已完成'], ['failed', '失败'], ['all', '全部']].map(([id, label]) => `<button type="button" class="${this.state.taskFilter === id ? 'active' : ''}" data-remote-filter="${id}">${label}</button>`).join('')}</div></div><div class="list-items remote-task-list" data-preserve-scroll="remote-task-list">${items.map((item) => this.remoteRow(ctx, item)).join('') || ctx.empty('没有符合条件的远程任务。')}</div></aside><article class="workspace-detail" id="remote-detail">${selected ? this.remoteDetail(ctx, selected) : ctx.empty('请选择一条远程任务查看详情。')}</article></div></div>`;
  },

  remoteRow(ctx, item) {
    const display = item.display || {};
    return `<button type="button" class="list-item remote-task-row ${item.request_id === this.state.selectedTask ? 'active' : ''}" data-remote-task="${ctx.esc(item.request_id)}" data-preserve-focus="remote:${ctx.esc(item.request_id)}"><strong>${ctx.esc(display.title || '未命名任务')}</strong><p>${ctx.esc(this.executorLabel(display))} · ${ctx.esc(display.service || '远程执行')} · ${ctx.esc(display.capability || '按请求处理')}</p><span class="item-meta">${ctx.tag(display.status || '待处理', display.tone || '')}<span>${ctx.esc(display.duration || '')}</span></span></button>`;
  },

  remoteDetail(ctx, item) {
    const display = item.display || {};
    const executor = this.executorLabel(display);
    const run = display.run_id ? `<span>运行标识 ${ctx.esc(display.run_id)}</span>` : '';
    const workspace = display.workspace ? `<span>工作区 ${ctx.esc(display.workspace)}</span>` : '';
    return `<div class="detail-header"><div><h2>${ctx.esc(display.title || '未命名任务')}</h2><p>${ctx.esc(executor)} · ${ctx.esc(display.service || '远程执行')} · ${ctx.esc(display.lane || '交互任务')}</p></div>${ctx.tag(display.status || '待处理', display.tone || '')}</div>${display.stale ? `<div class="notice warn">该任务长时间没有更新，可能已与 ${ctx.esc(executor)} 失去同步。</div>` : ''}<section class="detail-section"><h3>执行器</h3><div class="metric-row"><span>${ctx.esc(executor)}</span><span>Profile ${ctx.esc(display.execution_profile || 'codex_default')} · r${ctx.esc(display.profile_revision || 1)}</span><span>${ctx.esc(display.approval || '由 Core 策略控制')}</span>${run}${workspace}</div></section><section class="detail-section"><h3>处理结果</h3><p>${ctx.esc(display.result || '暂无结果。')}</p></section>${display.error ? `<section class="detail-section"><h3>失败原因</h3><p>${ctx.esc(display.error)}</p></section>` : ''}<section class="detail-section"><h3>下一步</h3><p>${ctx.esc(display.next_action || '无需处理。')}</p></section><section class="detail-section"><h3>执行信息</h3><p>${ctx.esc(display.capability || '按请求处理')} · ${ctx.esc(display.duration || '')}</p></section>${display.can_cancel ? `<div class="detail-actions remote-cancel-actions"><button class="btn danger" type="button" data-cancel-remote="${ctx.esc(item.request_id)}">取消任务</button><p class="inline-action-status" data-remote-action-result role="status" aria-live="polite"></p></div>` : ''}${ctx.tech(item.technical || item)}`;
  },

  executorLabel(display) {
    return display.executor || 'Codex CLI';
  },

  typeLabel(value) {
    return ({ device: '设备', service: '服务', server: '服务器', downloader: '下载器', media: '媒体服务', storage: '存储服务', automation: '自动化服务', remote: '远程执行器', control_plane: '控制平面', bridge_gateway: '连接网关', remote_executor: '远程执行器', adapter_gateway: '适配网关', memory_warehouse: '记忆仓库' })[value] || '本地资源';
  },

  permissionLabel(value) {
    const labels = { read: '查看', write: '修改', control: '控制', admin: '管理' };
    const items = Array.isArray(value) ? value : String(value || '').split(/[,\s]+/);
    return [...new Set(items.filter(Boolean).map((item) => labels[item] || '受控访问'))].join('、') || '按需授权';
  },

  availabilityTone(value) {
    return value === 'available' || value === 'active' ? 'success' : value === 'issue' ? 'danger' : 'warn';
  },

  bind(ctx, root) {
    root.querySelector('[data-open-remote]')?.addEventListener('click', () => ctx.setSubview('remote'));
    root.querySelectorAll('[data-webhook-toggle]').forEach((button) => {
      button.onclick = async () => {
        const source = button.dataset.webhookToggle;
        const enabled = button.dataset.enabled !== '1';
        if (!window.confirm(`确认${enabled ? '启用' : '停用'} ${source} Webhook 来源？`)) return;
        button.disabled = true;
        try {
          await ctx.api('/api/webhook/policy', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source, enabled, confirm: true }),
          });
          this.state.webhookNotice = `${source} 来源已${enabled ? '启用' : '停用'}。`;
          await ctx.setSubview('webhook');
        } catch (error) {
          this.state.webhookNotice = `策略更新失败：${error.message}`;
          button.disabled = false;
        }
      };
    });
    root.querySelectorAll('[data-webhook-replay]').forEach((button) => {
      button.onclick = async () => {
        const eventId = button.dataset.webhookReplay;
        if (!window.confirm(`确认重放失败事件 ${eventId}？这会再次发送消息。`)) return;
        button.disabled = true;
        try {
          await ctx.api('/api/webhook/replay', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ event_id: eventId, confirm: true }),
          });
          this.state.webhookNotice = '失败事件已加入重放队列。';
          await ctx.setSubview('webhook');
        } catch (error) {
          this.state.webhookNotice = `重放失败：${error.message}`;
          button.disabled = false;
        }
      };
    });
    root.querySelectorAll('[data-adapter]').forEach((button) => {
      button.onclick = () => ctx.preserveViewState(root, () => {
        this.state.selectedAdapter = button.dataset.adapter;
        return ctx.setSubview('gateway');
      }, button.dataset.preserveFocus);
    });
    root.querySelector('#adapter-search')?.addEventListener('input', (event) => {
      this.state.adapterQuery = event.target.value;
      const query = this.state.adapterQuery.toLowerCase();
      let visible = 0;
      root.querySelectorAll('[data-adapter]').forEach((button) => {
        button.hidden = !button.textContent.toLowerCase().includes(query);
        if (!button.hidden) visible += 1;
      });
      const empty = root.querySelector('[data-adapter-empty]');
      if (empty) empty.hidden = visible > 0;
    });
    if (this.state.adapterQuery) root.querySelector('#adapter-search')?.dispatchEvent(new Event('input'));
    root.querySelectorAll('[data-resource]').forEach((button) => {
      button.onclick = () => ctx.preserveViewState(root, () => {
        this.state.selectedResource = button.dataset.resource;
        return ctx.setSubview('bindings');
      }, button.dataset.preserveFocus);
    });
    root.querySelector('#resource-search')?.addEventListener('input', (event) => {
      this.state.resourceQuery = event.target.value;
      const query = this.state.resourceQuery.toLowerCase();
      root.querySelectorAll('[data-resource]').forEach((button) => { button.hidden = !button.textContent.toLowerCase().includes(query); });
    });
    if (this.state.resourceQuery) root.querySelector('#resource-search')?.dispatchEvent(new Event('input'));
    root.querySelectorAll('[data-remote-filter]').forEach((button) => {
      button.onclick = () => {
        this.state.taskFilter = button.dataset.remoteFilter;
        ctx.setSubview('remote');
      };
    });
    root.querySelector('#remote-search')?.addEventListener('input', (event) => {
      this.state.taskQuery = event.target.value;
      const query = this.state.taskQuery.toLowerCase();
      root.querySelectorAll('[data-remote-task]').forEach((button) => { button.hidden = !button.textContent.toLowerCase().includes(query); });
    });
    root.querySelectorAll('[data-remote-task]').forEach((button) => {
      button.onclick = () => ctx.preserveViewState(root, () => {
        this.state.selectedTask = button.dataset.remoteTask;
        return ctx.setSubview('remote');
      }, button.dataset.preserveFocus);
    });
    root.querySelectorAll('[data-cancel-remote]').forEach((button) => {
      button.onclick = async () => {
        const inlineStatus = root.querySelector('[data-remote-action-result]');
        if (button.dataset.confirmed !== 'true') {
          button.dataset.confirmed = 'true';
          button.textContent = '再次点击确认取消';
          if (inlineStatus) inlineStatus.textContent = '再次点击后将向 Codex Runner 提交取消，并同步最终状态。';
          return;
        }
        button.disabled = true;
        const status = root.querySelector('#remote-result');
        if (inlineStatus) inlineStatus.textContent = '正在提交取消请求…';
        try {
          const response = await ctx.api('/api/remote-tasks/cancel', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ request_id: button.dataset.cancelRemote, confirm: true }) });
          const result = response.data || {};
          const message = result.message || (result.status === 'cancelled' ? '任务已取消。' : result.payload?.reconciled_terminal ? `任务已结束，状态已同步为：${ctx.label(result.status)}` : '取消请求已提交。');
          this.state.remoteNotice = message;
          status.textContent = message;
          if (inlineStatus) inlineStatus.textContent = `${message} 正在刷新列表…`;
          await ctx.preserveViewState(root, () => ctx.setSubview('remote'));
        } catch (error) {
          button.disabled = false;
          button.dataset.confirmed = '';
          button.textContent = '取消任务';
          this.state.remoteNotice = `取消失败：${error?.message || '未知错误'}`;
          status.textContent = this.state.remoteNotice;
          if (inlineStatus) inlineStatus.textContent = `取消失败：${error?.message || '未知错误'}`;
        }
      };
    });
  },
};
