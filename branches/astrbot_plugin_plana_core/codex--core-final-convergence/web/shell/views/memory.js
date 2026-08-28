window.PlanaViews = window.PlanaViews || {};

window.PlanaViews.memory = {
  meta: {
    title: 'memory.title',
    caption: 'memory.caption',
    defaultSubview: 'library',
    subviews: [
      { id: 'library', label: 'memory.library' },
      { id: 'quality', label: 'memory.quality' },
      { id: 'profile', label: 'memory.profile' },
      { id: 'map', label: 'memory.map' },
    ],
  },

  async render(ctx, root) {
    if (ctx.activeSubview === 'quality') return this.quality(ctx, root);
    if (ctx.activeSubview === 'profile') return this.profile(ctx, root);
    if (ctx.activeSubview === 'map') return this.map(ctx, root);
    return this.library(ctx, root);
  },

  async scopeData(ctx) {
    const response = await ctx.api('/api/memory-scopes?limit=160');
    return response.data || { summary: {}, items: [] };
  },

  chooseScope(ctx, items, mode) {
    const storageKey = `plana_memory_scope_${mode}`;
    const stored = ctx.storageGet(storageKey);
    if (stored && items.some((item) => item.id === stored && (mode !== 'library' || Number(item.counts?.memories || 0) > 0))) return stored;
    const relevant = items.filter((item) => {
      const counts = item.counts || {};
      if (mode === 'library') return counts.memories > 0;
      if (mode === 'profile') return counts.semantics > 0;
      return counts.pending_feedback > 0 || counts.open_gaps > 0;
    });
    if (mode === 'library') relevant.sort((left, right) => Number(right.counts?.memories || 0) - Number(left.counts?.memories || 0));
    const friend = mode === 'library' ? null : relevant.find((item) => item.kind === 'friend');
    return (friend || relevant[0] || items[0] || { id: 'global' }).id;
  },

  scopeToolbar(ctx, scopeData, selectedScope, mode) {
    const options = (scopeData.items || []).map((item) => {
      const counts = item.counts || {};
      let suffix = `\u8bb0\u5fc6 ${counts.memories || 0}`;
      if (mode === 'profile') suffix = `\u7406\u89e3 ${counts.semantics || 0}`;
      if (mode === 'quality') suffix = `\u5f85\u5904\u7406 ${counts.pending_feedback || 0} \u00b7 \u7f3a\u53e3 ${counts.open_gaps || 0}`;
      return `<option value="${ctx.esc(item.id)}" ${item.id === selectedScope ? 'selected' : ''}>${ctx.esc(item.label)} \u00b7 ${suffix}</option>`;
    }).join('');
    const summary = scopeData.summary || {};
    return `<div class="scope-toolbar"><label><span>\u5f53\u524d\u8bb0\u5fc6\u8303\u56f4</span><select data-memory-scope data-scope-mode="${mode}">${options}</select></label><p>\u672c\u5730\u9884\u89c8\u5df2\u8bfb\u53d6 ${summary.scopes || 0} \u4e2a\u8303\u56f4\uff0c\u5171 ${summary.memories || 0} \u6761\u8bb0\u5fc6\u3002</p></div>`;
  },

  async library(ctx, root) {
    this.stopGraph?.();
    const scopes = await this.scopeData(ctx);
    const selectedScope = this.chooseScope(ctx, scopes.items || [], 'library');
    const response = await ctx.api(`/api/memories?scope=${encodeURIComponent(selectedScope)}&limit=100`);
    const items = response.data || [];
    const kinds = [...new Set(items.map((item) => item.kind).filter(Boolean))];
    const sources = [...new Set(items.map((item) => item.source).filter(Boolean))];
    root.innerHTML = `<div class="view-stack"><section class="section-block">${ctx.sectionHeading('\u8bb0\u5fc6\u5e93', '\u4ee5\u6761\u5f62\u8bb0\u5f55\u6d4f\u89c8\u8bb0\u5fc6\uff0c\u5c55\u5f00\u540e\u67e5\u770b\u5b8c\u6574\u5185\u5bb9\u3002', `<span class="status-pill">${items.length} \u6761\u8bb0\u5fc6</span>`)}<div class="memory-toolbar"><label><span>\u8bb0\u5fc6\u8303\u56f4</span><select data-memory-scope data-scope-mode="library">${this.libraryScopeOptions(ctx, scopes.items || [], selectedScope)}</select></label><label><span>\u641c\u7d22</span><input id="memory-filter" type="search" placeholder="\u641c\u7d22\u8bb0\u5fc6\u5185\u5bb9"></label><label><span>\u7c7b\u578b</span><select id="memory-kind-filter"><option value="">\u5168\u90e8\u7c7b\u578b</option>${kinds.map((kind) => `<option value="${ctx.esc(kind)}">${ctx.esc(this.predicateLabel(kind))}</option>`).join('')}</select></label><label><span>\u6765\u6e90</span><select id="memory-source-filter"><option value="">\u5168\u90e8\u6765\u6e90</option>${sources.map((source) => `<option value="${ctx.esc(source)}">${ctx.esc(this.sourceLabel(source))}</option>`).join('')}</select></label></div><div class="memory-strip-list" id="memory-items">${items.map((item) => this.memoryStrip(ctx, item)).join('') || ctx.empty('\u8be5\u8303\u56f4\u8fd8\u6ca1\u6709\u4fdd\u5b58\u7684\u8bb0\u5fc6\u3002')}</div></section></div>`;
    root._memoryItems = items;
  },

  libraryScopeOptions(ctx, items, selectedScope) {
    const groups = [
      ['friend', '\u597d\u53cb'],
      ['group', '\u7fa4\u804a'],
      ['web', '\u7f51\u9875\u4f1a\u8bdd'],
      ['other', '\u5176\u4ed6'],
    ];
    const available = items.filter((item) => Number(item.counts?.memories || 0) > 0);
    const groupFor = (item) => item.kind === 'friend' ? 'friend' : item.kind === 'group' ? 'group' : String(item.kind || '').includes('web') || String(item.label || '').includes('\u7f51\u9875') ? 'web' : 'other';
    return groups.map(([id, label]) => {
      const options = available.filter((item) => groupFor(item) === id).sort((left, right) => Number(right.counts?.memories || 0) - Number(left.counts?.memories || 0));
      return options.length ? `<optgroup label="${label}">${options.map((item) => `<option value="${ctx.esc(item.id)}" ${item.id === selectedScope ? 'selected' : ''}>${ctx.esc(item.label)} \u00b7 ${Number(item.counts?.memories || 0)} \u6761</option>`).join('')}</optgroup>` : '';
    }).join('');
  },

  memoryStrip(ctx, item) {
    const content = this.memoryContentLabel(item.content);
    return `<article class="memory-strip" data-memory-row data-search="${ctx.esc(content.toLowerCase())}" data-kind="${ctx.esc(item.kind || '')}" data-source="${ctx.esc(item.source || '')}"><button type="button" class="memory-strip-summary" data-memory-toggle="${item.id}" aria-expanded="false"><span class="memory-strip-type">${ctx.esc(this.predicateLabel(item.kind || '\u8bb0\u5fc6'))}</span><span class="memory-strip-content">${ctx.esc(content)}</span><span class="memory-strip-meta"><span>${ctx.esc(this.sourceLabel(item.source))}</span><span>\u91cd\u8981\u5ea6 ${ctx.esc(this.importanceLabel(item.importance))}</span><span>${ctx.esc(this.formatTime(item.created_at))}</span></span><span class="memory-strip-action">\u5c55\u5f00</span></button><div class="memory-strip-detail" data-memory-detail="${item.id}" hidden><div><h3>\u5b8c\u6574\u8bb0\u5fc6</h3><p>${ctx.esc(content)}</p></div><dl class="status-list"><div><dt>\u8bb0\u5fc6\u7c7b\u578b</dt><dd>${ctx.esc(this.predicateLabel(item.kind))}</dd></div><div><dt>\u8bb0\u5f55\u6765\u6e90</dt><dd>${ctx.esc(this.sourceLabel(item.source))}</dd></div><div><dt>\u91cd\u8981\u5ea6</dt><dd>${ctx.esc(this.importanceLabel(item.importance))}</dd></div><div><dt>\u8bb0\u5f55\u65f6\u95f4</dt><dd>${ctx.esc(this.formatTime(item.created_at))}</dd></div></dl>${ctx.tech(item)}</div></article>`;
  },

  feedbackType(kind) {
    return ({ useful: '\u6709\u5e2e\u52a9', not_useful: '\u53ec\u56de\u4e0d\u51c6\u786e', new_memory: '\u65b0\u8bb0\u5fc6\u5efa\u8bae', merge: '\u5408\u5e76\u8bb0\u5fc6\u5efa\u8bae' })[kind] || kind || '\u8bb0\u5fc6\u53cd\u9988';
  },

  feedbackDescription(item) {
    const payload = item.payload || {};
    const candidate = payload.content || payload.reason || payload.merged_content;
    if (candidate) return this.isTechnicalError(candidate) ? '\u68c0\u6d4b\u5230\u5de5\u5177\u6267\u884c\u9519\u8bef\uff0c\u5efa\u8bae\u68c0\u67e5\u540e\u4fee\u6b63\u6216\u5ffd\u7565\u3002' : candidate;
    if (Array.isArray(payload.memory_ids)) return `\u6d89\u53ca\u8bb0\u5fc6 ${payload.memory_ids.join(', ')}`;
    return '\u7b49\u5f85\u4eba\u5de5\u590d\u6838\u3002';
  },

  isTechnicalError(value) {
    return typeof value === 'string' && /(bridge tool .* failed|command \[|timed out after|traceback|\/home\/)/i.test(value);
  },

  formatTime(value) {
    if (value === null || value === undefined || value === '') return '-';
    const numeric = Number(value);
    const date = Number.isFinite(numeric)
      ? new Date(numeric < 1000000000000 ? numeric * 1000 : numeric)
      : new Date(value);
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
  },

  actorLabel(value) {
    if (value === 'system') return '\u7cfb\u7edf\u8bc6\u522b';
    if (value === 'codex_runner') return 'Codex CLI';
    return value || '\u672a\u6807\u8bb0\u7528\u6237';
  },

  qualityStatus(ctx, status) {
    const label = this.qualityStatusLabel(status);
    return `<span class="tag ${status === 'open' ? 'warn' : ''}">${label}</span>`;
  },

  qualityStatusLabel(status) {
    return ({
      pending: '\u5f85\u590d\u6838',
      open: '\u5f85\u8865\u5145',
      applied: '\u5df2\u5e94\u7528',
      dismissed: '\u5df2\u5ffd\u7565',
      resolved: '\u5df2\u5904\u7406',
    })[status] || '\u5f85\u5904\u7406';
  },

  async quality(ctx, root) {
    this.stopGraph?.();
    const scopes = await this.scopeData(ctx);
    const selectedScope = this.chooseScope(ctx, scopes.items || [], 'quality');
    const encodedScope = encodeURIComponent(selectedScope);
    const [feedback, gaps] = await Promise.all([
      ctx.api(`/api/feedback?scope=${encodedScope}&limit=50`),
      ctx.api(`/api/recall-gaps?scope=${encodedScope}`),
    ]);
    const feedbackItems = feedback.items || [];
    const gapItems = gaps.items || [];
    const candidates = [
      ...feedbackItems.map((item) => ({ type: 'feedback', id: String(item.id), item })),
      ...gapItems.map((item) => ({ type: 'gap', id: String(item.id), item })),
    ];
    const selectedKey = candidates.some((entry) => `${entry.type}:${entry.id}` === this.qualitySelection)
      ? this.qualitySelection
      : candidates[0] ? `${candidates[0].type}:${candidates[0].id}` : '';
    this.qualitySelection = selectedKey;
    const selected = candidates.find((entry) => `${entry.type}:${entry.id}` === selectedKey);
    const list = candidates.map((entry) => {
      const item = entry.item;
      const title = entry.type === 'feedback' ? this.feedbackType(item.kind) : '\u56de\u5fc6\u7f3a\u53e3';
      const description = entry.type === 'feedback' ? this.feedbackDescription(item) : item.query || '\u672a\u8bb0\u5f55\u67e5\u8be2';
      return `<button class="list-item ${`${entry.type}:${entry.id}` === selectedKey ? 'active' : ''}" type="button" data-quality-item="${entry.type}:${ctx.esc(entry.id)}" data-preserve-focus="quality:${entry.type}:${ctx.esc(entry.id)}"><strong>${ctx.esc(title)}</strong><p>${ctx.esc(description)}</p><span class="item-meta">${ctx.esc(this.actorLabel(item.user_id))} \u00b7 ${ctx.esc(this.qualityStatusLabel(item.status))}</span></button>`;
    }).join('');
    const detail = selected
      ? selected.type === 'feedback'
        ? this.feedbackEditor(ctx, selected.item, selectedScope)
        : this.gapEditor(ctx, selected.item, selectedScope)
      : ctx.empty('\u5f53\u524d\u8303\u56f4\u6ca1\u6709\u5f85\u590d\u6838\u5185\u5bb9\u3002');
    const action = feedbackItems.length > 1 ? `<button class="btn" type="button" data-process-scope="${ctx.esc(selectedScope)}" data-count="${feedbackItems.length}">\u6279\u91cf\u5e94\u7528 ${feedbackItems.length} \u9879</button>` : '';
    const notice = this.qualityNotice ? `<div class="notice">${ctx.esc(this.qualityNotice)}</div>` : '';
    this.qualityNotice = '';
    root.innerHTML = `<div class="view-stack"><section class="section-block">${ctx.sectionHeading('\u8bb0\u5fc6\u4fee\u6b63', '\u9010\u9879\u590d\u6838\u3001\u7f16\u8f91\u5e76\u5e94\u7528\u8bb0\u5fc6\u5efa\u8bae\uff1b\u6240\u6709\u5199\u5165\u64cd\u4f5c\u90fd\u9700\u8981\u4e8c\u6b21\u786e\u8ba4\u3002', action)}${this.scopeToolbar(ctx, scopes, selectedScope, 'quality')}${notice}<div id="correction-status" class="page-status" role="status" aria-live="polite"></div><div class="workspace correction-workspace ${this.qualityMobileDetail ? 'mobile-detail' : ''}"><aside class="workspace-list"><div class="workspace-toolbar"><strong>\u5f85\u590d\u6838\u9879</strong><span class="item-meta">${feedbackItems.length} \u9879\u5efa\u8bae \u00b7 ${gapItems.length} \u4e2a\u7f3a\u53e3</span></div><div class="list-items" data-preserve-scroll="quality-list">${list || ctx.empty('\u5f53\u524d\u8303\u56f4\u5df2\u5904\u7406\u5b8c\u6bd5\u3002')}</div></aside><article class="workspace-detail" id="correction-detail">${detail}</article></div></section></div>`;
    root._qualityScope = selectedScope;
  },

  feedbackEditor(ctx, item, scope) {
    const payload = item.payload || {};
    const editable = ['new_memory', 'merge', 'not_useful'].includes(item.kind);
    const content = item.kind === 'new_memory' ? payload.content : item.kind === 'merge' ? payload.merged_content : payload.reason;
    const kindOptions = ['semantic_note', 'user_fact', 'user_preference', 'relationship_note', 'promise', 'task_fact'].map((kind) => `<option value="${kind}" ${kind === (payload.kind || 'semantic_note') ? 'selected' : ''}>${ctx.esc(this.predicateLabel(kind))}</option>`).join('');
    const editor = editable ? `<section class="detail-section correction-form"><label class="form-field" for="correction-content"><span>${item.kind === 'not_useful' ? '\u4fee\u6b63\u8bf4\u660e' : '\u8bb0\u5fc6\u5185\u5bb9'}</span><textarea id="correction-content" rows="9" maxlength="1000">${ctx.esc(content || '')}</textarea></label>${item.kind === 'new_memory' ? `<label class="form-field" for="correction-kind"><span>\u8bb0\u5fc6\u7c7b\u578b</span><select id="correction-kind">${kindOptions}</select></label>` : ''}<p class="field-hint">\u4fee\u6539\u540e\u5148\u4fdd\u5b58\uff0c\u518d\u5e94\u7528\u5230\u8bb0\u5fc6\u5e93\u3002</p></section>` : `<section class="detail-section"><h3>\u5904\u7406\u8bf4\u660e</h3><p>\u6b64\u7c7b\u53cd\u9988\u4e0d\u5305\u542b\u53ef\u7f16\u8f91\u6587\u672c\uff0c\u53ef\u76f4\u63a5\u5e94\u7528\u6216\u5ffd\u7565\u3002</p></section>`;
    const relatedIds = Array.isArray(payload.memory_ids) && payload.memory_ids.length ? `<p class="field-hint">\u5173\u8054\u8bb0\u5fc6\uff1a${ctx.esc(payload.memory_ids.join(', '))}</p>` : '';
    return `<button class="btn mobile-back" type="button" data-quality-back>\u8fd4\u56de\u5f85\u590d\u6838\u5217\u8868</button><div class="detail-header"><div><h2>${ctx.esc(this.feedbackType(item.kind))}</h2><p>${ctx.esc(this.actorLabel(item.user_id))} \u63d0\u4ea4\u7684\u5f85\u590d\u6838\u5185\u5bb9</p></div>${this.qualityStatus(ctx, item.status)}</div>${editor}${relatedIds}<div class="detail-actions">${editable ? `<button class="btn" type="button" data-quality-action="save" data-feedback-id="${item.id}">\u4fdd\u5b58\u4fee\u6539</button>` : ''}<button class="btn primary" type="button" data-quality-action="apply" data-feedback-id="${item.id}">\u5e94\u7528\u6b64\u9879</button><button class="btn danger" type="button" data-quality-action="dismiss" data-feedback-id="${item.id}">\u5ffd\u7565\u6b64\u9879</button></div>${ctx.tech({ id: item.id, scope, kind: item.kind, payload, created_at: item.created_at })}`;
  },

  gapEditor(ctx, item, scope) {
    const kindOptions = ['semantic_note', 'user_fact', 'user_preference', 'relationship_note'].map((kind) => `<option value="${kind}">${ctx.esc(this.predicateLabel(kind))}</option>`).join('');
    return `<button class="btn mobile-back" type="button" data-quality-back>\u8fd4\u56de\u5f85\u590d\u6838\u5217\u8868</button><div class="detail-header"><div><h2>\u8865\u5168\u56de\u5fc6\u7f3a\u53e3</h2><p>${ctx.esc(item.query || '\u672a\u8bb0\u5f55\u67e5\u8be2')}</p></div>${this.qualityStatus(ctx, item.status)}</div><section class="detail-section correction-form"><label class="form-field" for="gap-content"><span>\u6b63\u786e\u7b54\u6848\u6216\u5e94\u8bb0\u4f4f\u7684\u5185\u5bb9</span><textarea id="gap-content" rows="9" maxlength="1000" placeholder="\u8f93\u5165\u7ecf\u8fc7\u590d\u6838\u7684\u8bb0\u5fc6\u5185\u5bb9"></textarea></label><label class="form-field" for="gap-kind"><span>\u8bb0\u5fc6\u7c7b\u578b</span><select id="gap-kind">${kindOptions}</select></label><p class="field-hint">\u63d0\u4ea4\u540e\u4f1a\u751f\u6210\u5f85\u590d\u6838\u5efa\u8bae\uff0c\u4e0d\u4f1a\u7ed5\u8fc7\u5e94\u7528\u786e\u8ba4\u3002</p></section><div class="detail-actions"><button class="btn primary" type="button" data-quality-action="propose" data-gap-id="${item.id}">\u751f\u6210\u5f85\u590d\u6838\u8bb0\u5fc6</button></div>${ctx.tech({ id: item.id, scope, query: item.query, user_id: item.user_id, created_at: item.created_at })}`;
  },

  predicateLabel(predicate) {
    return ({ likes: '\u559c\u6b22', preferred_anime_source: '\u52a8\u6f2b\u8ba2\u9605\u6765\u6e90', uses_service: '\u4f7f\u7528\u670d\u52a1', uses_software: '\u4f7f\u7528\u8f6f\u4ef6', preference: '\u504f\u597d', promise: '\u7ea6\u5b9a', semantic_note: '\u8bed\u4e49\u5907\u6ce8', user_fact: '\u7528\u6237\u4e8b\u5b9e', user_preference: '\u7528\u6237\u504f\u597d', relationship_note: '\u5173\u7cfb\u5907\u6ce8', task_fact: '\u4efb\u52a1\u4e8b\u5b9e', observed_need: '\u89c2\u5bdf\u5230\u7684\u9700\u6c42', feedback_note: '\u4eba\u5de5\u4fee\u6b63\u8bb0\u5f55', important_event: '\u91cd\u8981\u7ecf\u5386' })[predicate] || '\u5176\u4ed6\u7406\u89e3';
  },

  sourceLabel(source) {
    return ({ memory_feedback: '\u4eba\u5de5\u4fee\u6b63', history_import: '\u5386\u53f2\u5bfc\u5165', conversation: '\u5bf9\u8bdd\u8bb0\u5f55', llm: 'Plana \u6574\u7406', system: '\u7cfb\u7edf\u6574\u7406' })[source] || '\u7cfb\u7edf\u6574\u7406';
  },

  subjectLabel(subject) {
    const value = String(subject || '');
    if (/^(task|session):/.test(value)) return '\u5bf9\u8bdd\u4e2d\u89c2\u5bdf\u5230';
    if (/^\d+$/.test(value)) return `\u7528\u6237 ${value}`;
    return value.replace(/^(?:user:)?(aiocqhttp|webchat):/, '\u7528\u6237 ') || '\u5f53\u524d\u7528\u6237';
  },

  objectLabel(value) {
    const text = this.memoryContentLabel(value);
    if (text === 'anime') return '\u52a8\u6f2b';
    const animeSearch = text.match(/^(.+?) uses (.+?) to search for anime\.?$/i);
    if (animeSearch) return `${animeSearch[1]} \u4f7f\u7528 ${animeSearch[2]} \u641c\u7d22\u52a8\u6f2b\u3002`;
    return text.replace(/^Plana response:\s*/i, 'Plana \u66fe\u56de\u590d\uff1a');
  },

  memoryContentLabel(value) {
    return String(value || '')
      .replace(/\brecent\b/g, '\u8fd1\u671f')
      .replace(/\bhistorical\b/g, '\u5386\u53f2')
      .replace(/\blimited_observed_interaction\b/g, '\u4e92\u52a8\u8bb0\u5f55\u8f83\u5c11')
      .replace(/\bmoderate_observed_interaction\b/g, '\u5df2\u6709\u4e00\u5b9a\u4e92\u52a8')
      .replace(/\bstrong_observed_interaction\b/g, '\u4e92\u52a8\u8bb0\u5f55\u8f83\u4e30\u5bcc');
  },

  importanceLabel(value) {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? `${Math.round(numeric * 100)}%` : '-';
  },

  confidenceLabel(value) {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? `${Math.round(numeric * 100)}%` : '-';
  },

  async profile(ctx, root) {
    this.stopGraph?.();
    const scopes = await this.scopeData(ctx);
    const selectedScope = this.chooseScope(ctx, scopes.items || [], 'profile');
    const response = await ctx.api(`/api/profile?scope=${encodeURIComponent(selectedScope)}&limit=50`);
    const data = response.data || {};
    const person = data.person || {};
    const semantics = data.semantics || [];
    const selected = (scopes.items || []).find((item) => item.id === selectedScope) || {};
    const displayName = person.display_name || this.subjectLabel(data.user_id) || this.subjectLabel(semantics.find((item) => !String(item.subject || '').startsWith('task:'))?.subject) || selected.label || '\u5f53\u524d\u7528\u6237';
    const summaryText = data.person_summary || (data.snapshots || []).find((item) => item.summary)?.summary || `\u5df2\u6574\u7406 ${semantics.length} \u6761\u957f\u671f\u504f\u597d\u4e0e\u4e8b\u5b9e\uff0c\u53ef\u5728\u6280\u672f\u8be6\u60c5\u4e2d\u67e5\u770b\u6765\u6e90\u8bc1\u636e\u3002`;
    const cards = `<div class="summary-grid profile-summary-grid"><div class="summary-item"><strong>${semantics.length}</strong><span>\u957f\u671f\u7406\u89e3</span></div><div class="summary-item"><strong>${(data.evidence || []).length}</strong><span>\u6765\u6e90\u8bc1\u636e</span></div><div class="summary-item"><strong>${(data.snapshots || []).length}</strong><span>\u753b\u50cf\u5feb\u7167</span></div><div class="summary-item"><strong>${data.refresh?.pending || 0}</strong><span>\u5f85\u5237\u65b0</span></div></div>`;
    const rows = semantics.map((item) => `<tr><td><strong>${ctx.esc(this.predicateLabel(item.predicate))}</strong><span class="row-subtext">${ctx.esc(this.subjectLabel(item.subject))}</span></td><td>${ctx.esc(this.objectLabel(item.object_value))}</td><td>${ctx.esc(this.confidenceLabel(item.confidence))}</td></tr>`).join('');
    root.innerHTML = `<div class="view-stack"><section class="section-block">${ctx.sectionHeading('\u7528\u6237\u7406\u89e3', 'Plana \u6839\u636e\u957f\u671f\u4fe1\u606f\u6574\u7406\u51fa\u7684\u7528\u6237\u504f\u597d\u548c\u5173\u7cfb\u3002')}${this.scopeToolbar(ctx, scopes, selectedScope, 'profile')}<div class="profile-intro"><span class="profile-kicker">${ctx.esc(selected.label || '\u5f53\u524d\u8303\u56f4')}</span><h3>${ctx.esc(displayName)}</h3><p>${ctx.esc(summaryText)}</p></div>${cards}${ctx.table(['\u7406\u89e3', '\u5185\u5bb9', '\u7f6e\u4fe1\u5ea6'], rows)}${ctx.tech(data)}</section></div>`;
  },

  async map(ctx, root) {
    this.stopGraph?.();
    const response = await ctx.api('/api/concepts?limit=300');
    const data = response.data || {};
    const legend = [['topic', '\u4e3b\u9898'], ['person', '\u7528\u6237\u4e0e\u753b\u50cf'], ['fact', '\u4e8b\u5b9e\u4e0e\u504f\u597d'], ['summary', '\u8bb0\u5fc6\u4e0e\u6d41\u7a0b'], ['other', '\u5176\u4ed6']].map(([kind, label]) => `<span><i class="map-dot node-${kind}"></i>${label}</span>`).join('');
    const options = (data.nodes || []).slice(0, 120).map((node) => `<option value="${ctx.esc(node.concept)}"></option>`).join('');
    root.innerHTML = `<div class="view-stack"><section class="section-block">${ctx.sectionHeading('\u8bb0\u5fc6\u56fe\u8c31', '\u6eda\u8f6e\u7f29\u653e\u3001\u62d6\u52a8\u5e73\u79fb\uff1b\u60ac\u505c\u805a\u7126\u90bb\u63a5\u5173\u7cfb\uff0c\u70b9\u51fb\u56fa\u5b9a\u8282\u70b9\u3002')}<div class="map-header"><div class="map-legend">${legend}</div><span id="concept-map-status" class="map-status"></span></div><div class="map-toolbar"><label class="map-search" for="concept-search"><span>\u641c\u7d22\u8282\u70b9</span><input id="concept-search" type="search" list="concept-options" placeholder="\u8f93\u5165\u4e3b\u9898\u540d\u79f0"></label><datalist id="concept-options">${options}</datalist><button class="map-tool" type="button" data-map-action="search">\u5b9a\u4f4d</button><span class="map-tool-divider" aria-hidden="true"></span><button class="map-tool map-tool-icon" type="button" data-map-action="zoom-in" aria-label="\u653e\u5927\u56fe\u8c31">\uff0b</button><button class="map-tool map-tool-icon" type="button" data-map-action="zoom-out" aria-label="\u7f29\u5c0f\u56fe\u8c31">\u2212</button><button class="map-tool" type="button" data-map-action="reset">\u91cd\u7f6e\u89c6\u56fe</button><button class="map-tool active" type="button" data-map-action="labels" aria-pressed="true">\u6807\u7b7e</button></div><div class="memory-map"><canvas id="concept-canvas" tabindex="0" role="img" aria-label="\u8bb0\u5fc6\u56fe\u8c31\uff0c\u53ef\u4f7f\u7528\u6eda\u8f6e\u7f29\u653e\u3001\u62d6\u52a8\u5e73\u79fb\uff0c\u65b9\u5411\u952e\u79fb\u52a8\u89c6\u56fe\uff0cEscape \u91cd\u7f6e"></canvas><div class="map-hint" aria-hidden="true">\u62d6\u52a8\u5e73\u79fb \u00b7 \u6eda\u8f6e\u7f29\u653e</div></div><div class="map-detail" id="concept-map-detail">\u5c06\u6307\u9488\u79fb\u52a8\u5230\u8282\u70b9\u4e0a\u67e5\u770b\u8be6\u60c5\u3002</div><div class="notice">\u5f53\u524d\u4f18\u5148\u663e\u793a\u9ad8\u6743\u91cd\u4e3b\u9898\uff0c\u5b8c\u6574\u6570\u636e\u5305\u542b ${(data.nodes || []).length} \u4e2a\u4e3b\u9898\u548c ${(data.edges || []).length} \u6761\u5173\u8054\u3002</div>${ctx.tech(data)}</section></div>`;
    this.stopGraph = window.PlanaMemoryGraph.mount({ canvas: root.querySelector('#concept-canvas'), detail: root.querySelector('#concept-map-detail'), root, data, ctx });
  },

  bind(ctx, root) {
    root.querySelectorAll('[data-memory-scope]').forEach((select) => {
      select.onchange = () => {
        ctx.storageSet(`plana_memory_scope_${select.dataset.scopeMode}`, select.value);
        ctx.setSubview(ctx.activeSubview);
      };
    });

    root.querySelectorAll('[data-memory-toggle]').forEach((button) => {
      button.onclick = () => {
        const detail = root.querySelector(`[data-memory-detail="${button.dataset.memoryToggle}"]`);
        const willOpen = detail?.hidden;
        root.querySelectorAll('[data-memory-detail]').forEach((candidate) => { candidate.hidden = true; });
        root.querySelectorAll('[data-memory-toggle]').forEach((candidate) => { candidate.setAttribute('aria-expanded', 'false'); candidate.querySelector('.memory-strip-action').textContent = '\u5c55\u5f00'; });
        if (detail && willOpen) {
          detail.hidden = false;
          button.setAttribute('aria-expanded', 'true');
          button.querySelector('.memory-strip-action').textContent = '\u6536\u8d77';
        }
      };
    });

    const applyMemoryFilters = () => {
      const query = String(root.querySelector('#memory-filter')?.value || '').toLowerCase();
      const kind = root.querySelector('#memory-kind-filter')?.value || '';
      const source = root.querySelector('#memory-source-filter')?.value || '';
      root.querySelectorAll('[data-memory-row]').forEach((row) => {
        row.hidden = Boolean((query && !row.dataset.search.includes(query)) || (kind && row.dataset.kind !== kind) || (source && row.dataset.source !== source));
      });
    };
    root.querySelector('#memory-filter')?.addEventListener('input', applyMemoryFilters);
    root.querySelector('#memory-kind-filter')?.addEventListener('change', applyMemoryFilters);
    root.querySelector('#memory-source-filter')?.addEventListener('change', applyMemoryFilters);

    root.querySelectorAll('[data-quality-item]').forEach((button) => {
      button.onclick = () => ctx.preserveViewState(root, () => {
        this.qualitySelection = button.dataset.qualityItem;
        this.qualityMobileDetail = true;
        return ctx.setSubview('quality');
      }, button.dataset.preserveFocus);
    });
    const qualityBack = root.querySelector('[data-quality-back]');
    if (qualityBack) qualityBack.onclick = () => {
      this.qualityMobileDetail = false;
      ctx.setSubview('quality');
    };

    const correctionStatus = root.querySelector('#correction-status');
    const showCorrectionError = (error) => {
      const labels = {
        empty_content: '\u8bf7\u5148\u586b\u5199\u4fee\u6b63\u540e\u7684\u8bb0\u5fc6\u5185\u5bb9\u3002',
        feedback_not_applied: '\u6b64\u9879\u672a\u80fd\u5e94\u7528\uff0c\u53ef\u7f16\u8f91\u540e\u91cd\u8bd5\u6216\u5ffd\u7565\u3002',
        not_found: '\u8be5\u5f85\u529e\u5df2\u88ab\u5904\u7406\uff0c\u8bf7\u5237\u65b0\u540e\u67e5\u770b\u3002',
      };
      if (correctionStatus) correctionStatus.textContent = labels[error?.message] || `\u64cd\u4f5c\u5931\u8d25\uff1a${error?.message || '\u672a\u77e5\u9519\u8bef'}`;
    };
    const confirmAction = (button, confirmedLabel, action) => {
      button.onclick = async () => {
        if (button.dataset.confirmed !== 'true') {
          button.dataset.confirmed = 'true';
          button.dataset.originalLabel = button.textContent;
          button.textContent = confirmedLabel;
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
          showCorrectionError(error);
        }
      };
    };
    root.querySelectorAll('[data-quality-action]').forEach((button) => {
      const action = button.dataset.qualityAction;
      const feedbackId = Number(button.dataset.feedbackId || 0);
      const scope = root._qualityScope || 'global';
      if (action === 'save') confirmAction(button, '\u518d\u6b21\u70b9\u51fb\u786e\u8ba4\u4fdd\u5b58', async () => {
        await ctx.api('/api/feedback/update', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ scope, feedback_id: feedbackId, content: root.querySelector('#correction-content')?.value || '', memory_kind: root.querySelector('#correction-kind')?.value || '', confirm: true }) });
        this.qualityNotice = '\u4fee\u6539\u5df2\u4fdd\u5b58\uff0c\u8bf7\u786e\u8ba4\u5185\u5bb9\u540e\u518d\u5e94\u7528\u3002';
        await ctx.preserveViewState(root, () => ctx.setSubview('quality'));
      });
      if (action === 'apply') confirmAction(button, '\u518d\u6b21\u70b9\u51fb\u786e\u8ba4\u5e94\u7528', async () => {
        await ctx.api('/api/feedback/process-item', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ scope, feedback_id: feedbackId, confirm: true }) });
        this.qualityNotice = '\u8be5\u9879\u5df2\u5e94\u7528\u5230\u8bb0\u5fc6\u5e93\u3002';
        this.qualitySelection = '';
        await ctx.preserveViewState(root, () => ctx.setSubview('quality'));
      });
      if (action === 'dismiss') confirmAction(button, '\u518d\u6b21\u70b9\u51fb\u786e\u8ba4\u5ffd\u7565', async () => {
        await ctx.api('/api/feedback/dismiss', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ scope, feedback_id: feedbackId, confirm: true }) });
        this.qualityNotice = '\u8be5\u9879\u5df2\u5ffd\u7565\uff0c\u672a\u5199\u5165\u8bb0\u5fc6\u5e93\u3002';
        this.qualitySelection = '';
        await ctx.preserveViewState(root, () => ctx.setSubview('quality'));
      });
      if (action === 'propose') confirmAction(button, '\u518d\u6b21\u70b9\u51fb\u786e\u8ba4\u751f\u6210', async () => {
        await ctx.api('/api/recall-gaps/propose', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ scope, gap_id: Number(button.dataset.gapId || 0), content: root.querySelector('#gap-content')?.value || '', kind: root.querySelector('#gap-kind')?.value || 'semantic_note', confirm: true }) });
        this.qualityNotice = '\u5df2\u751f\u6210\u5f85\u590d\u6838\u8bb0\u5fc6\uff0c\u8bf7\u7ee7\u7eed\u68c0\u67e5\u5e76\u5e94\u7528\u3002';
        this.qualitySelection = '';
        await ctx.preserveViewState(root, () => ctx.setSubview('quality'));
      });
    });
    root.onkeydown = (event) => {
      if (event.key !== 'Escape') return;
      root.querySelectorAll('[data-confirmed="true"]').forEach((button) => {
        button.dataset.confirmed = '';
        button.classList.remove('primary');
        button.textContent = button.dataset.originalLabel || button.textContent;
      });
    };

    const processButton = root.querySelector('[data-process-scope]');
    if (processButton) processButton.onclick = async () => {
      if (processButton.dataset.confirmed !== 'true') {
        processButton.dataset.confirmed = 'true';
        processButton.classList.add('primary');
        processButton.textContent = `\u518d\u6b21\u70b9\u51fb\u786e\u8ba4\u5904\u7406 ${processButton.dataset.count} \u9879`;
        return;
      }
      processButton.disabled = true;
      try {
        const result = await ctx.api('/api/feedback/process', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ scope: processButton.dataset.processScope, limit: Number(processButton.dataset.count || 20), confirm: true }) });
        const stats = result.stats || {};
        this.qualityNotice = `\u6279\u91cf\u5904\u7406\u5b8c\u6210\uff1a\u5df2\u5e94\u7528 ${stats.processed || 0} \u9879\uff0c\u8df3\u8fc7 ${stats.skipped || 0} \u9879\u3002`;
        await ctx.preserveViewState(root, () => ctx.setSubview('quality'));
      } catch (error) {
        processButton.disabled = false;
        processButton.dataset.confirmed = '';
        processButton.classList.remove('primary');
        processButton.textContent = `\u6279\u91cf\u5e94\u7528 ${processButton.dataset.count} \u9879`;
        showCorrectionError(error);
      }
    };
  },
};
