/* 04-settings-llm.js — extracted from templates/index.html. Plain scripts, loaded in
   numbered order; they share one global scope, so load order matters. */
/* ---------- theme + settings ---------- */
function applyTheme(t, save){
  document.body.dataset.theme=t;
  document.querySelectorAll('#themeseg button').forEach(b=>b.classList.toggle('on', b.dataset.t===t));
  SETTINGS.theme=t; if(save) saveSettings();
}
async function loadSettings(){
  try{ SETTINGS=await (await fetch('/api/settings')).json(); }catch(e){ SETTINGS={}; }
  applyTheme(SETTINGS.theme||'light', false);
  if(SETTINGS.compute) setCompute(SETTINGS.compute);
  if(SETTINGS.glossary_name) $('gname').value=SETTINGS.glossary_name;
  $('s_help').checked = SETTINGS.show_help!==false;
  if($('s_ollama_url')) $('s_ollama_url').value = SETTINGS.ollama_url||'';
  if($('s_timeout')) $('s_timeout').value = SETTINGS.llm_timeout!=null ? SETTINGS.llm_timeout : '';
  if($('s_company')) $('s_company').value = SETTINGS.company||'';
  if($('s_workers')) $('s_workers').value = SETTINGS.llm_workers!=null ? SETTINGS.llm_workers : '';
  if($('s_batch')) $('s_batch').value = SETTINGS.llm_batch!=null ? SETTINGS.llm_batch : '';
  // prefill the remembered (non-secret) PDC connection
  if(SETTINGS.pdc_base!=null && $('pdc_base')) $('pdc_base').value=SETTINGS.pdc_base;
  if(SETTINGS.pdc_realm && $('pdc_realm')) $('pdc_realm').value=SETTINGS.pdc_realm;
  if(SETTINGS.pdc_ver && $('pdc_ver')) $('pdc_ver').value=SETTINGS.pdc_ver;
  if(SETTINGS.pdc_verify!=null && $('pdc_verify')) $('pdc_verify').checked=!!SETTINGS.pdc_verify;
  loadModels(SETTINGS.model);
}
function savePdcConn(){
  if(!$('pdc_base')) return;
  const body={pdc_base:$('pdc_base').value.trim(), pdc_realm:($('pdc_realm').value||'pdc').trim(),
              pdc_ver:$('pdc_ver').value, pdc_verify:$('pdc_verify').checked};
  fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}).catch(()=>{});
}
async function saveSettings(){
  const body={theme:document.body.dataset.theme, model:currentModel(), compute:COMPUTE,
              glossary_name:$('gname').value, show_help:$('s_help').checked};
  if($('s_ollama_url')) body.ollama_url=$('s_ollama_url').value.trim();
  if($('s_timeout')) body.llm_timeout=$('s_timeout').value?parseFloat($('s_timeout').value):'';
  if($('s_company')) body.company=$('s_company').value.trim();
  if($('s_workers')) body.llm_workers=$('s_workers').value?parseInt($('s_workers').value,10):'';
  if($('s_batch')) body.llm_batch=$('s_batch').value?parseInt($('s_batch').value,10):'';
  try{ await fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}); }catch(e){}
}
// Save the LLM settings, then re-probe so the status reflects the new URL/timeout,
// and show the result inline next to the Test connection button.
async function saveLlmConfig(){
  const el=$('llmTestMsg'); if(el) el.textContent='Testing connection…';
  await saveSettings();
  llmStatus();
  try{
    const m=currentModel();
    const s=await (await fetch('/api/llm-status'+(m?('?model='+encodeURIComponent(m)):''))).json();
    if(el){
      if(s.online) el.innerHTML='✓ Connected to <code>'+esc(s.url||'')+'</code>'+(s.model_present===false?(' — model <b>'+esc(s.model||'')+'</b> not pulled (use Pull selected model)'):(' · model <b>'+esc(s.model||'')+'</b> ready'));
      else el.innerHTML='✗ Offline at <code>'+esc(s.url||'')+'</code>'+(s.error?(' — '+esc(String(s.error))):'')+'. In Docker, set the URL to <code>http://host.docker.internal:11434</code>.';
    }
  }catch(e){ if(el) el.textContent='✗ Test failed: '+e; }
}

/* ---------- LLM ---------- */
const MODELS=[{tag:'llama3.2:3b',size:'~2.0 GB',rec:true},{tag:'qwen2.5:3b',size:'~1.9 GB'},{tag:'phi3:mini',size:'~2.3 GB'},{tag:'gemma2:2b',size:'~1.6 GB'},{tag:'mistral',size:'~4.1 GB'},{tag:'llama3.1',size:'~4.9 GB'}];
// Fill the model dropdown. renderModelOptions() shows the models actually
// installed on the local Ollama (an "Installed" optgroup) plus the curated
// suggestions not yet pulled, and preserves the current/saved selection.
// loadModels() fetches the live list from /api/models; the synchronous call
// below seeds the box so it is never empty before Ollama answers.
function renderModelOptions(installed, want){
  const sizeOf={}; MODELS.forEach(m=>sizeOf[m.tag]=m.size);
  const inst=(installed||[]).filter(Boolean);
  const instSet=new Set(inst);
  let html='';
  if(inst.length){
    html+='<optgroup label="Installed (ready to use)">'+inst.map(t=>`<option value="${esc(t)}">${esc(t)}${sizeOf[t]?(' \u00b7 '+sizeOf[t]):''}</option>`).join('')+'</optgroup>';
  }
  const pull=MODELS.filter(m=>!instSet.has(m.tag));
  if(pull.length){
    html+='<optgroup label="Suggested \u2014 not yet pulled">'+pull.map(m=>`<option value="${esc(m.tag)}">${esc(m.tag)} \u00b7 ${m.size}${m.rec?' \u00b7 recommended':''}</option>`).join('')+'</optgroup>';
  }
  if(want && want!=='__custom__' && !instSet.has(want) && !MODELS.some(m=>m.tag===want)){
    html='<optgroup label="Selected">'+`<option value="${esc(want)}">${esc(want)}</option>`+'</optgroup>'+html;
  }
  html+='<option value="__custom__">Custom\u2026</option>';
  $('modelSel').innerHTML=html;
  const opts=[...$('modelSel').options].map(o=>o.value);
  $('modelSel').value=(want && opts.includes(want))?want:(inst[0]||'llama3.2:3b');
}
renderModelOptions([], 'llama3.2:3b');
async function loadModels(preferred){
  let installed=[];
  try{ installed=(await (await fetch('/api/models')).json()).models||[]; }catch(e){}
  const want=preferred||currentModel()||(typeof SETTINGS!=='undefined'&&SETTINGS.model)||'llama3.2:3b';
  renderModelOptions(installed, want);
  onModelSel();
}
function onModelSel(){ $('modelCustomFld').style.display=$('modelSel').value==='__custom__'?'':'none'; llmStatus(); }
function currentModel(){ const v=$('modelSel').value; return v==='__custom__'?$('modelCustom').value.trim():v; }
function setCompute(c){ COMPUTE=c; document.querySelectorAll('#seg button').forEach(b=>b.classList.toggle('on',b.dataset.c===c)); }
async function llmStatus(){
  const m=currentModel();
  try{
    const s=await (await fetch('/api/llm-status'+(m?('?model='+encodeURIComponent(m)):''))).json();
    $('dot').className='dot '+(s.online?(s.model_present===false?'off':'on'):'off');
    $('llmtxt').textContent=s.online?(s.model_present===false?(s.model+' not pulled'):('Ollama · '+s.model)):'LLM offline';
    const need=s.online&&s.model_present===false;
    $('pullBtn').style.display=need?'':'none';
    $('enrichBtn').disabled=!ROWS.length||!s.online||s.model_present===false; if($('aiSuggestBtn')) $('aiSuggestBtn').disabled=$('enrichBtn').disabled;
    if($('catBtn')) $('catBtn').disabled=$('enrichBtn').disabled;
    if($('qaBtn')) $('qaBtn').disabled=!ROWS.length;
  }catch(e){ $('dot').className='dot off'; $('llmtxt').textContent='LLM offline'; $('pullBtn').style.display='none'; }
}
function fmtBytes(n){ if(!n||n<0)return'0 B'; if(n>=1e9)return(n/1e9).toFixed(2)+' GB'; if(n>=1e6)return(n/1e6).toFixed(1)+' MB'; if(n>=1e3)return(n/1e3).toFixed(0)+' KB'; return n+' B'; }
function fmtETA(s){ if(s==null||!isFinite(s))return''; s=Math.round(s); if(s>=3600)return Math.floor(s/3600)+'h '+Math.round(s%3600/60)+'m'; if(s>=60)return Math.floor(s/60)+'m '+(s%60)+'s'; return s+'s'; }
async function pullModel(){
  const model=currentModel(); $('pullwrap').style.display='flex'; $('bar').style.width='0%'; $('pulltxt').textContent='Pulling '+(model||'model')+'…';
  let lc=0,lt=Date.now(),sp=0;
  try{
    const r=await fetch('/api/pull-model',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model:model||null})});
    const rd=r.body.getReader(), dec=new TextDecoder(); let buf='';
    while(true){ const {done,value}=await rd.read(); if(done)break; buf+=dec.decode(value,{stream:true}); let nl;
      while((nl=buf.indexOf('\n'))>=0){ const line=buf.slice(0,nl).trim(); buf=buf.slice(nl+1); if(!line)continue;
        const ev=JSON.parse(line); if(ev.phase==='error'){$('pulltxt').textContent='Error: '+ev.status;break;}
        const c=ev.completed||0,t=ev.total||0,now=Date.now();
        if(c<lc){sp=0;lc=c;lt=now;} else if(c>lc&&now>lt){const inst=(c-lc)/((now-lt)/1000); sp=sp?sp*0.7+inst*0.3:inst; lc=c;lt=now;}
        if(ev.percent!=null){ $('bar').style.width=ev.percent+'%'; const eta=(sp>0&&t>c)?(t-c)/sp:null;
          let p=[ev.status,ev.percent+'%']; if(t)p.push(fmtBytes(c)+' / '+fmtBytes(t)); if(sp>0)p.push(fmtBytes(sp)+'/s'); if(eta!=null)p.push('~'+fmtETA(eta)+' left'); $('pulltxt').textContent=p.join(' · ');
        } else $('pulltxt').textContent=ev.status;
        if(ev.phase==='success'){$('bar').style.width='100%';$('pulltxt').textContent='Model ready.';}
      } }
  }catch(e){ $('pulltxt').textContent='Pull failed: '+e; }
  setTimeout(()=>{ $('pullwrap').style.display='none'; loadModels(currentModel()); llmStatus(); },1500);
}
async function loadDrivers(){
  try{ const d=(await (await fetch('/api/drivers')).json()).drivers;
    $('drvrows').innerHTML=d.map(x=>`<tr><td>${x.label}</td><td><code>${x.module}</code></td><td><span class="badge ${x.present?'ok':'miss'}">${x.present?('installed'+(x.version?' '+x.version:'')):'not installed'}</span></td><td><code>${x.install}</code></td><td>${x.jdbc_hint}</td></tr>`).join('');
  }catch(e){}
}
