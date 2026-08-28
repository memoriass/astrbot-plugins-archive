"""HTML page template for Plana Core web dashboard."""

from __future__ import annotations


def dashboard_html(api_base: str) -> str:
    """Return the full HTML page for the Plana Core dashboard.

    *api_base* is the prefix such as ``/api/plug/plana`` so the
    front-end JS can construct API URLs.
    """
    return _TEMPLATE.replace("{{API_BASE}}", api_base)


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Plana Core Dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#061427;--bg2:#0a1f3a;--card:rgba(11,31,57,.78);
  --card2:rgba(13,42,76,.92);--border:rgba(127,213,255,.18);
  --text:#eaf8ff;--text2:#8fb6d7;--muted:#5c7fa2;--primary:#5fd4ff;
  --primary2:#8aa7ff;--success:#7cf7c5;--warning:#ffd36e;--danger:#ff7d9b;
  --sidebar:rgba(3,13,29,.86);--sidebar-text:#b9daf2;--radius:18px;
  --shadow:0 18px 50px rgba(0,9,30,.34);--glow:0 0 26px rgba(95,212,255,.26);
}
html{background:#061427}
body{font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  background:
    radial-gradient(circle at 18% 16%,rgba(95,212,255,.22),transparent 26%),
    radial-gradient(circle at 80% 10%,rgba(138,167,255,.22),transparent 28%),
    linear-gradient(145deg,var(--bg),var(--bg2) 56%,#091126);
  color:var(--text);font-size:14px;line-height:1.6;min-height:100vh;overflow:hidden}
body::before{content:"";position:fixed;inset:0;pointer-events:none;opacity:.42;
  background-image:radial-gradient(#77dfff 1px,transparent 1px);
  background-size:54px 54px;mask-image:linear-gradient(to bottom,#000,transparent 76%)}
#app{display:flex;height:100vh;overflow:hidden;position:relative}
#sidebar{width:244px;background:var(--sidebar);color:var(--sidebar-text);
  display:flex;flex-direction:column;padding:22px 14px;flex-shrink:0;
  border-right:1px solid var(--border);backdrop-filter:blur(18px)}
.logo{display:flex;gap:12px;align-items:center;color:#fff;padding:0 8px 22px;margin-bottom:10px;
  border-bottom:1px solid rgba(127,213,255,.12);letter-spacing:.08em}
.logo-mark{width:42px;height:42px;border:1px solid rgba(95,212,255,.55);border-radius:14px;
  display:grid;place-items:center;background:linear-gradient(145deg,rgba(95,212,255,.18),rgba(138,167,255,.08));box-shadow:var(--glow)}
.logo-mark::before{content:"◇";font-size:22px;color:var(--primary);text-shadow:0 0 18px var(--primary)}
.logo-title{font-size:16px;font-weight:800;line-height:1.1}.logo-sub{font-size:10px;color:var(--text2);margin-top:4px;letter-spacing:.16em}
.nav-item{display:flex;align-items:center;gap:9px;padding:11px 12px;margin:4px 0;color:var(--sidebar-text);
  text-decoration:none;cursor:pointer;transition:all .18s;font-size:13px;border:1px solid transparent;border-radius:14px}
.nav-item:hover{color:#fff;background:rgba(95,212,255,.08);border-color:rgba(95,212,255,.13)}
.nav-item.active{color:#fff;background:linear-gradient(135deg,rgba(95,212,255,.22),rgba(138,167,255,.13));
  border-color:rgba(95,212,255,.34);box-shadow:0 8px 26px rgba(95,212,255,.12)}
#content{flex:1;overflow-y:auto;padding:28px;position:relative}
.hero{position:relative;overflow:hidden;margin-bottom:18px;padding:28px 30px;border-radius:24px;
  background:linear-gradient(135deg,rgba(11,31,57,.88),rgba(23,48,91,.62));border:1px solid var(--border);box-shadow:var(--shadow)}
.hero::after{content:"";position:absolute;right:46px;top:26px;width:170px;height:170px;border-radius:50%;
  border:1px solid rgba(95,212,255,.22);box-shadow:inset 0 0 38px rgba(95,212,255,.08),0 0 42px rgba(95,212,255,.08)}
.hero-kicker{font-size:11px;color:var(--primary);letter-spacing:.22em;text-transform:uppercase}.hero h1{font-size:34px;letter-spacing:.16em;margin:4px 0 2px}
.hero p{color:var(--text2);max-width:720px}.hero-code{margin-top:12px;color:var(--muted);font-size:11px;letter-spacing:.12em;white-space:pre-wrap}
.tab{display:none}.tab.active{display:block}.card{background:var(--card);border-radius:var(--radius);padding:20px;
  margin-bottom:16px;box-shadow:var(--shadow);border:1px solid var(--border);backdrop-filter:blur(18px)}
.card h3{font-size:14px;margin-bottom:14px;color:var(--text);letter-spacing:.08em;text-transform:uppercase}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px}.stat{text-align:left;padding:16px;border-radius:16px;background:rgba(255,255,255,.035);border:1px solid rgba(127,213,255,.1)}
.stat .val{font-size:26px;font-weight:800;color:var(--primary);text-shadow:0 0 18px rgba(95,212,255,.16);word-break:break-word}.stat .lbl{font-size:12px;color:var(--text2);margin-top:4px}
.badge{display:inline-block;padding:3px 9px;border-radius:999px;font-size:12px;font-weight:700;border:1px solid transparent}.badge-ok{background:rgba(124,247,197,.12);color:var(--success);border-color:rgba(124,247,197,.28)}
.badge-warn{background:rgba(255,211,110,.12);color:var(--warning);border-color:rgba(255,211,110,.25)}.badge-off{background:rgba(143,182,215,.1);color:var(--text2);border-color:rgba(143,182,215,.16)}
table{width:100%;border-collapse:collapse;font-size:13px;overflow:hidden}th,td{text-align:left;padding:10px 12px;border-bottom:1px solid rgba(127,213,255,.1)}
th{font-weight:700;color:var(--text2);font-size:11px;text-transform:uppercase;letter-spacing:.08em}tr:hover td{background:rgba(95,212,255,.045)}
.toolbar{display:flex;gap:10px;margin-bottom:14px;align-items:center;flex-wrap:wrap}.toolbar input,.toolbar select{padding:8px 12px;border:1px solid var(--border);
  border-radius:12px;background:rgba(4,18,39,.68);color:var(--text);font-size:13px;outline:none}.toolbar input{flex:1;max-width:360px}.toolbar input:focus,.toolbar select:focus{border-color:rgba(95,212,255,.55);box-shadow:var(--glow)}
.btn{padding:8px 16px;border:none;border-radius:12px;cursor:pointer;font-size:13px;font-weight:700;transition:all .15s}.btn-primary{background:linear-gradient(135deg,var(--primary),var(--primary2));color:#031326;box-shadow:var(--glow)}.btn-primary:hover{transform:translateY(-1px)}.btn-sm{padding:5px 10px;font-size:12px}
.empty{text-align:center;color:var(--text2);padding:34px;font-size:13px}.tag{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;background:rgba(95,212,255,.1);color:var(--primary);border:1px solid rgba(95,212,255,.18);margin:1px}.concept-w{font-size:11px;color:var(--text2);margin-left:4px}
.hidden{display:none!important}.login-panel{position:fixed;inset:0;background:rgba(2,8,20,.72);display:flex;align-items:center;justify-content:center;z-index:10;backdrop-filter:blur(16px)}
.login-box{width:min(390px,calc(100vw - 32px));background:linear-gradient(145deg,rgba(10,32,60,.96),rgba(12,23,48,.96));border:1px solid rgba(95,212,255,.24);border-radius:24px;box-shadow:var(--shadow);padding:26px}.login-box h3{letter-spacing:.08em}.login-box input{width:100%;padding:10px 12px;border:1px solid var(--border);border-radius:12px;background:rgba(2,12,28,.72);color:var(--text);margin:10px 0 14px}.login-msg{color:var(--danger);font-size:12px;min-height:18px}
@media(max-width:768px){#sidebar{width:76px;padding:16px 9px}.logo{justify-content:center;padding:0 0 16px}.logo-text{display:none}.nav-item{justify-content:center;font-size:0}.nav-item::first-letter{font-size:15px}#content{padding:14px}.hero{padding:22px}.hero h1{font-size:25px}.hero::after{display:none}}
</style>
</head>
<body>
<div id="app">
  <nav id="sidebar">
    <div class="logo">
      <div class="logo-mark"></div>
      <div class="logo-text">
        <div class="logo-title">PLANA CORE</div>
        <div class="logo-sub">BACKUP OS</div>
      </div>
    </div>
    <a class="nav-item active" data-tab="overview">◇ 概览</a>
    <a class="nav-item" data-tab="memories">✧ 记忆</a>
    <a class="nav-item" data-tab="lab">✦ 检索实验室</a>
    <a class="nav-item" data-tab="profile">◈ 画像</a>
    <a class="nav-item" data-tab="bridge">⇄ Bridge</a>
    <a class="nav-item" data-tab="concepts">⬡ 概念图</a>
    <a class="nav-item" data-tab="relations">⌁ 关系</a>
    <a class="nav-item" data-tab="tasks">☑ 任务</a>
    <a class="nav-item" data-tab="maintain">◌ 维护</a>
  </nav>
  <main id="content">
    <div id="tab-overview" class="tab active"></div>
    <div id="tab-memories" class="tab"></div>
    <div id="tab-lab" class="tab"></div>
    <div id="tab-profile" class="tab"></div>
    <div id="tab-bridge" class="tab"></div>
    <div id="tab-concepts" class="tab"></div>
    <div id="tab-relations" class="tab"></div>
    <div id="tab-tasks" class="tab"></div>
    <div id="tab-maintain" class="tab"></div>
  </main>
  <div id="login-panel" class="login-panel hidden">
    <div class="login-box">
      <h3>PLANA CORE ACCESS</h3>
      <p style="color:var(--text2);font-size:13px">输入独立 Web 管理端密码以接入备份 OS 控制台。</p>
      <input id="login-password" type="password" placeholder="管理密码">
      <button class="btn btn-primary" id="login-btn">接入控制台</button>
      <div class="login-msg" id="login-msg"></div>
    </div>
  </div>
</div>
<script>
(async function(){
const API='{{API_BASE}}';
const $=s=>document.querySelector(s);
const $$=s=>document.querySelectorAll(s);
const TOKEN_KEY='plana_dashboard_token';
let authToken=new URLSearchParams(location.search).get('token')||localStorage.getItem(TOKEN_KEY)||'';
const tokenParam=()=>authToken?'token='+encodeURIComponent(authToken):'';
const J=async(path,opts)=>{
  const sep=path.includes('?')?'&':'?';
  const url=API+path+(tokenParam()?sep+tokenParam():'');
  const headers=Object.assign({},(opts&&opts.headers)||{});
  if(authToken)headers.Authorization='Bearer '+authToken;
  const r=await fetch(url,Object.assign({},opts||{},{headers}));
  const data=await r.json().catch(()=>({ok:false,error:'invalid_json'}));
  if(r.status===401){showLogin('认证已失效，请重新登录');throw new Error(data.error||'unauthorized')}
  return data;
};
const ts=v=>{if(!v)return'-';const d=new Date(v*1000);return d.toLocaleString('zh-CN')};
const html=(tag,cls,inner)=>`<${tag} class="${cls||''}">${inner||''}</${tag}>`;
const badge=(ok,yes='已启用',no='已禁用')=>ok?html('span','badge badge-ok',yes):html('span','badge badge-off',no);
function showLogin(msg){
  $('#login-panel').classList.remove('hidden');
  $('#login-msg').textContent=msg||'';
  setTimeout(()=>$('#login-password').focus(),0);
}
function hideLogin(){
  $('#login-panel').classList.add('hidden');
  $('#login-msg').textContent='';
}
async function initAuth(){
  $('#login-btn').onclick=async()=>{
    const password=$('#login-password').value;
    $('#login-btn').disabled=true;$('#login-msg').textContent='登录中…';
    try{
      const r=await fetch(API+'/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password})});
      const d=await r.json();
      if(!r.ok)throw new Error(d.error||'登录失败');
      authToken=d.token||'';localStorage.setItem(TOKEN_KEY,authToken);hideLogin();await loadTab('overview');
    }catch(e){$('#login-msg').textContent=e.message}
    $('#login-btn').disabled=false;
  };
  $('#login-password').onkeydown=e=>{if(e.key==='Enter')$('#login-btn').click()};
  try{
    const r=await fetch(API+'/api/auth-info');
    if(!r.ok)return true;
    const d=await r.json();
    if(d.auth_required&&!authToken){showLogin('');return false}
  }catch(e){return true}
  return true;
}


// Tab navigation
$$('.nav-item').forEach(el=>{
  el.addEventListener('click',()=>{
    $$('.nav-item').forEach(n=>n.classList.remove('active'));
    el.classList.add('active');
    $$('.tab').forEach(t=>t.classList.remove('active'));
    $('#tab-'+el.dataset.tab).classList.add('active');
    loadTab(el.dataset.tab);
  });
});

async function loadTab(name){
  try{
    if(name==='overview') await loadOverview();
    else if(name==='memories') await loadMemories();
    else if(name==='lab') await loadLab();
    else if(name==='profile') await loadProfile();
    else if(name==='bridge') await loadBridge();
    else if(name==='concepts') await loadConcepts();
    else if(name==='relations') await loadRelations();
    else if(name==='tasks') await loadTasks();
    else if(name==='maintain') await loadMaintain();
  }catch(e){console.error(e)}
}

async function loadOverview(){
  const d=(await J('/api/overview')).data;
  const f=d.features;const t=d.tables;
  const focus=d.focus||'-';
  let s=`<section class="hero">
    <div class="hero-kicker">SCHALEN BACKUP OPERATING SYSTEM</div>
    <h1>PLANA CORE</h1>
    <p>记忆、工具、任务与风险复盘核心。当前实例作为备份 OS 运转，负责为 Arona/Nacho 侧提供长期事实索引与执行检查。</p>
    <div class="hero-code">STATUS:${d.mode} / FOCUS:${focus} / RISK:${d.risk_level}</div>
  </section>`;
  s+=html('div','card',html('h3','','系统状态')+
    html('div','grid',
      html('div','stat',html('div','val',d.mode)+html('div','lbl','当前模式'))+
      html('div','stat',html('div','val',d.concept_nodes)+html('div','lbl','概念节点'))+
      html('div','stat',html('div','val',d.concept_edges)+html('div','lbl','概念边'))+
      html('div','stat',html('div','val',focus)+html('div','lbl','焦点'))+
      html('div','stat',html('div','val',d.pressure)+html('div','lbl','压力'))+
      html('div','stat',html('div','val',d.risk_level)+html('div','lbl','风险等级'))
    ));
  s+=html('div','card',html('h3','','功能状态')+
    html('div','grid',
      html('div','stat',badge(f.memory_activation)+html('div','lbl','记忆激活'))+
      html('div','stat',badge(f.memory_consolidation)+html('div','lbl','记忆沉淀'))+
      html('div','stat',badge(f.memory_decay)+html('div','lbl','记忆衰减'))+
      html('div','stat',badge(f.relation_graph)+html('div','lbl','关系图'))+
      html('div','stat',badge(f.concept_extraction)+html('div','lbl','概念提取'))+
      html('div','stat',badge(f.structured_memory_extraction)+html('div','lbl','结构化记忆'))+
      html('div','stat',badge(f.memory_query_planner)+html('div','lbl','检索规划'))+
      html('div','stat',badge(f.task_queue)+html('div','lbl','任务队列'))
    ));
  let rows='';for(const[k,v]of Object.entries(t)){
    rows+=`<tr><td>${k}</td><td style="font-weight:600">${v}</td></tr>`;
  }
  s+=html('div','card',html('h3','','数据表统计')+
    `<table><thead><tr><th>表名</th><th>行数</th></tr></thead><tbody>${rows}</tbody></table>`);
  $('#tab-overview').innerHTML=s;
}

let memQ='';
let memKind='';
let memoryKinds=[];
async function loadMemoryKinds(){
  if(memoryKinds.length)return memoryKinds;
  const d=(await J('/api/overview')).data;
  memoryKinds=((d.features||{}).memory_kinds)||[];
  return memoryKinds;
}
async function loadMemories(){
  const p=$('#tab-memories');
  if(!p.querySelector('.toolbar')){
    const kinds=await loadMemoryKinds();
    const opts=['<option value="">全部类型</option>'].concat(
      kinds.map(k=>`<option value="${k}">${k}</option>`)
    ).join('');
    p.innerHTML=`<div class="card"><h3>记忆查看</h3>
      <div class="toolbar"><input id="mem-q" placeholder="搜索记忆…">
      <select id="mem-kind">${opts}</select>
      <button class="btn btn-primary" id="mem-search">搜索</button></div>
      <div id="mem-list"></div></div>`;
    $('#mem-search').onclick=()=>{memQ=$('#mem-q').value;renderMem()};
    $('#mem-q').onkeydown=e=>{if(e.key==='Enter'){memQ=$('#mem-q').value;renderMem()}};
    $('#mem-kind').onchange=()=>{memKind=$('#mem-kind').value;renderMem()};
  }
  await renderMem();
}
async function renderMem(){
  const q=memQ?'&q='+encodeURIComponent(memQ):'';
  const k=memKind?'&kind='+encodeURIComponent(memKind):'';
  const d=(await J('/api/memories?limit=30'+q+k)).data;
  if(!d||!d.length){$('#mem-list').innerHTML=html('div','empty','暂无记忆数据');return}
  let rows=d.map(m=>`<tr><td>${m.id}</td><td><span class="tag">${m.kind}</span></td>
    <td>${m.content}</td><td>${m.importance}</td><td>${m.source}</td><td>${ts(m.created_at)}</td></tr>`).join('');
  $('#mem-list').innerHTML=`<table><thead><tr><th>ID</th><th>类型</th><th>内容</th>
    <th>重要度</th><th>来源</th><th>时间</th></tr></thead><tbody>${rows}</tbody></table>`;
}

let labQ='';
let labKind='';
async function loadLab(){
  const p=$('#tab-lab');
  if(!p.querySelector('.toolbar')){
    const kinds=await loadMemoryKinds();
    const opts=['<option value="">全部类型</option>'].concat(
      kinds.map(k=>`<option value="${k}">${k}</option>`)
    ).join('');
    p.innerHTML=html('div','card',html('h3','','检索实验室')+
      '<p style="color:var(--text2);margin-bottom:12px">模拟 Plana 记忆检索链路，显示情景记忆、语义画像、概念扩散与 Prompt 上下文预览。</p>'+
      `<div class="toolbar"><input id="lab-q" placeholder="输入关键词，例如：用户偏好 / 任务 / 风险…">
      <select id="lab-kind">${opts}</select><button class="btn btn-primary" id="lab-run">运行检索</button></div>`+
      '<div id="lab-result"></div>');
    $('#lab-run').onclick=()=>{labQ=$('#lab-q').value;labKind=$('#lab-kind').value;renderLab()};
    $('#lab-q').onkeydown=e=>{if(e.key==='Enter')$('#lab-run').click()};
    $('#lab-kind').onchange=()=>{labKind=$('#lab-kind').value;renderLab()};
  }
  await renderLab();
}
async function renderLab(){
  const q=labQ?'&q='+encodeURIComponent(labQ):'';
  const k=labKind?'&kind='+encodeURIComponent(labKind):'';
  const data=(await J('/api/retrieve-test?limit=8'+q+k)).data;
  const preview=(await J('/api/context-preview?limit=8'+q+k)).data;
  const memRows=(data.memories||[]).map(m=>`<tr><td>${m.id}</td><td><span class="tag">${m.kind}</span></td><td>${m.content}</td><td>${m.importance}</td></tr>`).join('');
  const semRows=(data.semantics||[]).map(s=>`<tr><td>${s.subject}</td><td>${s.predicate}</td><td>${s.object_value}</td><td>${s.confidence}</td></tr>`).join('');
  const fusedRows=(data.fused_results||[]).map(r=>`<tr><td>${r.id}</td><td><span class="tag">${r.route}</span></td><td>${r.title}</td><td>${r.kind||'-'}</td><td>${r.content}</td><td>${r.score}</td><td><code>${JSON.stringify(r.score_breakdown||{})}</code></td></tr>`).join('');
  const concepts=(data.concepts||[]).map(c=>`<span class="tag">${c.concept} · ${c.weight}</span>`).join(' ')||'<span class="empty">暂无概念命中</span>';
  const routeSummary=Object.entries(data.routes||{}).map(([name,count])=>`<span class="tag">${name}:${count}</span>`).join(' ')||'<span class="empty">暂无路由命中</span>';
  const lines=(preview.preview_lines||[]).map(x=>`<div>${x}</div>`).join('');
  $('#lab-result').innerHTML=html('div','grid',
    html('div','stat',html('div','val',(data.fused_results||[]).length)+html('div','lbl','RRF 融合命中'))+
    html('div','stat',html('div','val',(data.memories||[]).length)+html('div','lbl','情景记忆命中'))+
    html('div','stat',html('div','val',(data.semantics||[]).length)+html('div','lbl','语义画像命中'))+
    html('div','stat',html('div','val',(data.concepts||[]).length)+html('div','lbl','概念激活')))+
    html('div','card',html('h3','','RRF 融合回忆')+`<p style="color:var(--text2);margin-bottom:10px">${routeSummary}</p>`+(fusedRows?`<table><thead><tr><th>ID</th><th>路由</th><th>标题</th><th>类型</th><th>内容</th><th>分数</th><th>分解</th></tr></thead><tbody>${fusedRows}</tbody></table>`:'<div class="empty">暂无融合命中</div>'))+
    html('div','card',html('h3','','Prompt 上下文预览')+`<div class="hero-code">${lines}</div>`)+
    html('div','card',html('h3','','情景记忆')+(memRows?`<table><thead><tr><th>ID</th><th>类型</th><th>内容</th><th>重要度</th></tr></thead><tbody>${memRows}</tbody></table>`:'<div class="empty">暂无命中</div>'))+
    html('div','card',html('h3','','语义画像')+(semRows?`<table><thead><tr><th>主体</th><th>谓词</th><th>对象</th><th>置信度</th></tr></thead><tbody>${semRows}</tbody></table>`:'<div class="empty">暂无命中</div>'))+
    html('div','card',html('h3','','概念扩散')+`<div>${concepts}</div>`)+
    html('div','card',html('h3','','检索解释')+`<p>fusion: ${data.explain.fusion||'-'} / rrf_k: ${data.explain.rrf_k||'-'} / cross_bonus: ${data.explain.cross_route_bonus||0}</p><p>memory_route: ${data.explain.memory_route}</p><p>semantic_route: ${data.explain.semantic_route}</p><p>concept_route: ${data.explain.concept_route}</p>`);
}

async function loadProfile(){
  const d=(await J('/api/profile?limit=30')).data;
  const s=d.summary||{};
  const semRows=(d.semantics||[]).map(x=>`<tr><td>${x.subject}</td><td>${x.predicate}</td><td>${x.object_value}</td><td>${x.confidence}</td><td>${ts(x.updated_at)}</td></tr>`).join('');
  const relRows=(d.relations||[]).map(x=>`<tr><td>${x.source_id}</td><td>${x.target_id}</td><td><span class="tag">${x.relation_type}</span></td><td>${x.weight}</td><td>${x.confidence}</td></tr>`).join('');
  $('#tab-profile').innerHTML=html('div','card',html('h3','','画像扫描')+
    html('div','grid',
      html('div','stat',html('div','val',s.semantic_items||0)+html('div','lbl','语义条目'))+
      html('div','stat',html('div','val',s.relationship_edges||0)+html('div','lbl','关系边'))+
      html('div','stat',html('div','val',s.preferences||0)+html('div','lbl','偏好'))+
      html('div','stat',html('div','val',s.promises||0)+html('div','lbl','承诺'))))+
    html('div','card',html('h3','','语义画像')+(semRows?`<table><thead><tr><th>主体</th><th>谓词</th><th>对象</th><th>置信度</th><th>时间</th></tr></thead><tbody>${semRows}</tbody></table>`:'<div class="empty">暂无语义画像</div>'))+
    html('div','card',html('h3','','关系摘要')+(relRows?`<table><thead><tr><th>源</th><th>目标</th><th>类型</th><th>权重</th><th>置信度</th></tr></thead><tbody>${relRows}</tbody></table>`:'<div class="empty">暂无关系摘要</div>'));
}

async function loadBridge(){
  const d=(await J('/api/bridge-status')).data;
  const st=d.status||{};
  const kinds=(d.supported_kinds||[]).map(k=>`<span class="tag">${k}</span>`).join(' ');
  $('#tab-bridge').innerHTML=html('div','card',html('h3','','Arona / Nacho Bridge')+
    html('div','grid',
      html('div','stat',badge(st.enabled)+html('div','lbl','桥接开关'))+
      html('div','stat',html('div','val',st.bridge_plugin||d.plugin||'-')+html('div','lbl','桥接插件'))+
      html('div','stat',badge(st.bridge_required,'需要','不需要')+html('div','lbl','调试桥依赖'))+
      html('div','stat',badge(!st.direct_runtime_dependency,'隔离','直连')+html('div','lbl','运行时依赖')))+
    html('div','card',html('h3','','标准请求类型')+`<div>${kinds}</div>`)+
    html('div','card',html('h3','','使用说明')+
      '<p>NachoBridge 可把 Sidecar 的 plana_requests 转发到 PlanaCore，再把 plana_results 回传给 Sidecar。</p>'+
      '<p>推荐将 Web 控制台作为桥接观测面：检查请求类型、记忆查询、任务委托、情绪移交和上下文同步是否按协议进入。</p>'));
}


async function loadConcepts(){
  const d=(await J('/api/concepts?limit=100')).data;
  let s=html('div','card',html('h3','',`概念节点 (${d.total_nodes}) · 边 (${d.total_edges})`)+
    (d.nodes.length?'':'<div class="empty">暂无概念数据</div>'));
  if(d.nodes.length){
    let rows=d.nodes.map(n=>`<tr><td>${n.id}</td><td><strong>${n.concept}</strong></td>
      <td>${n.weight}</td><td title="${n.memory_items}">${(n.memory_items||'').substring(0,80)}</td>
      <td>${ts(n.last_modified)}</td></tr>`).join('');
    s=html('div','card',html('h3','',`概念节点 (${d.total_nodes})`)+
      `<table><thead><tr><th>ID</th><th>概念</th><th>权重</th><th>关联记忆</th><th>修改时间</th></tr></thead>
      <tbody>${rows}</tbody></table>`);
  }
  if(d.edges.length){
    let erows=d.edges.map(e=>`<tr><td>${e.source}</td><td>${e.target}</td>
      <td>${e.strength}</td><td>${ts(e.last_modified)}</td></tr>`).join('');
    s+=html('div','card',html('h3','',`概念边 (${d.total_edges})`)+
      `<table><thead><tr><th>源</th><th>目标</th><th>强度</th><th>修改时间</th></tr></thead>
      <tbody>${erows}</tbody></table>`);
  }
  $('#tab-concepts').innerHTML=s;
}

async function loadRelations(){
  const d=(await J('/api/relations?limit=50')).data;
  if(!d||!d.length){$('#tab-relations').innerHTML=html('div','card',
    html('h3','','关系图')+html('div','empty','暂无关系数据'));return}
  let rows=d.map(e=>`<tr><td>${e.source_id}</td><td>${e.target_id}</td>
    <td><span class="tag">${e.relation_type}</span></td><td>${e.weight}</td>
    <td>${e.confidence}</td><td title="${e.evidence}">${(e.evidence||'').substring(0,60)}</td>
    <td>${ts(e.updated_at)}</td></tr>`).join('');
  $('#tab-relations').innerHTML=html('div','card',html('h3','','关系图')+
    `<table><thead><tr><th>源</th><th>目标</th><th>类型</th><th>权重</th>
    <th>置信度</th><th>证据</th><th>时间</th></tr></thead><tbody>${rows}</tbody></table>`);
}

async function loadTasks(){
  const d=(await J('/api/tasks?limit=30')).data;
  if(!d||!d.length){$('#tab-tasks').innerHTML=html('div','card',
    html('h3','','任务')+html('div','empty','暂无任务'));return}
  let rows=d.map(t=>`<tr><td>${t.id}</td><td>${t.objective}</td>
    <td><span class="badge ${t.status==='done'?'badge-ok':t.status==='cancelled'?'badge-off':'badge-warn'}">${t.status}</span></td>
    <td>${t.risk_level}</td><td>${ts(t.created_at)}</td></tr>`).join('');
  $('#tab-tasks').innerHTML=html('div','card',html('h3','','任务')+
    `<table><thead><tr><th>ID</th><th>目标</th><th>状态</th><th>风险</th><th>创建时间</th></tr></thead>
    <tbody>${rows}</tbody></table>`);
}

async function loadMaintain(flash=''){
  const p=$('#tab-maintain');
  p.innerHTML=html('div','card',html('h3','','维护状态')+html('div','empty','正在读取维护状态…'));
  const status=(await J('/api/maintenance-status')).data;
  const validation=status.validation||{};
  const checks=(validation.checks||[]).map(c=>`<tr><td>${c.name}</td><td><span class="badge ${c.status==='green'?'badge-ok':c.status==='red'?'badge-off':'badge-warn'}">${c.status}</span></td><td>${Array.isArray(c.detail)?c.detail.join(', '):c.detail}</td></tr>`).join('');
  const backups=(status.backups||[]).map(b=>`<tr><td>${b.name}</td><td>${b.size}</td><td>${ts(b.mtime)}</td></tr>`).join('');
  const patterns=status.patterns||{};
  p.innerHTML=html('div','card',html('h3','','维护状态')+
    html('div','grid',
      html('div','stat',html('div','val',validation.status||'-')+html('div','lbl','validator'))+
      html('div','stat',html('div','val',(status.backups||[]).length)+html('div','lbl','backups'))+
      html('div','stat',html('div','val',Object.keys(status.tables||{}).length)+html('div','lbl','tables')))+
    `<p style="color:var(--text2)">db_path=${status.db_path||'-'}</p>`+
    `<table><thead><tr><th>检查项</th><th>状态</th><th>详情</th></tr></thead><tbody>${checks||'<tr><td colspan="3">暂无检查结果</td></tr>'}</tbody></table>`)+
    html('div','card',html('h3','','安全操作')+
      '<p style="color:var(--text2);margin-bottom:12px">执行维护、创建 SQLite 备份、或在备份后重建查询索引。</p>'+
      '<button class="btn btn-primary" id="btn-maintain">执行维护</button> '+
      '<button class="btn" id="btn-backup">创建备份</button> '+
      '<button class="btn" id="btn-rebuild">备份后重建索引</button>'+
      `<div id="maintain-result" style="margin-top:12px">${flash}</div>`)+
    html('div','card',html('h3','','备份列表')+
      `<table><thead><tr><th>文件</th><th>字节</th><th>时间</th></tr></thead><tbody>${backups||'<tr><td colspan="3">暂无备份</td></tr>'}</tbody></table>`)+
    html('div','card',html('h3','','维护设计说明')+
      `<p>validator: ${patterns.validator||'-'}</p><p>backup: ${patterns.backup||'-'}</p><p>scheduler: ${patterns.scheduler||'-'}</p><p>ops_gate: ${patterns.ops_gate||'-'}</p>`);
  $('#btn-maintain').onclick=async()=>{
    $('#btn-maintain').disabled=true;$('#btn-maintain').textContent='执行中…';
    try{
      const d=(await J('/api/maintain',{method:'POST'})).data;
      let r='';
      if(d.consolidate) r+=`<p>沉淀: 处理=${d.consolidate.processed} 跳过=${d.consolidate.skipped} 写入=${d.consolidate.semantic_written}</p>`;
      if(d.decay) r+=`<p>衰减: 处理=${d.decay.processed} 衰减=${d.decay.decayed} 跳过=${d.decay.skipped}</p>`;
      if(d.accumulate){
        if(d.accumulate.skipped&&typeof d.accumulate.skipped==='string'){
          r+=`<p>概念积累: 跳过=${d.accumulate.skipped}</p>`;
        }else{
          r+=`<p>概念积累: 处理=${d.accumulate.processed||0} 写入=${d.accumulate.written||0} 跳过=${d.accumulate.skipped||0}</p>`;
        }
      }
      if(!r) r='<p>所有维护功能均已禁用</p>';
      $('#maintain-result').innerHTML=html('div','card',r);
    }catch(e){$('#maintain-result').innerHTML='<p style="color:var(--danger)">'+e.message+'</p>'}
    $('#btn-maintain').disabled=false;$('#btn-maintain').textContent='执行维护';
  };
  $('#btn-backup').onclick=async()=>{
    const d=(await J('/api/backup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reason:'web-manual'})})).data;
    await loadMaintain(html('div','card',`<p>备份: ${d.ok?'OK':'FAIL'} ${d.path||d.error}</p>`));
  };
  $('#btn-rebuild').onclick=async()=>{
    const d=(await J('/api/rebuild-indexes',{method:'POST'})).data;
    await loadMaintain(html('div','card',`<p>重建索引: ${d.rebuild.count} 个; 备份=${d.backup.path||d.backup.error}</p>`));
  };
}

// Initial load
if(await initAuth())await loadTab('overview');
})();
</script>
</body>
</html>"""
