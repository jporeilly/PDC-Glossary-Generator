/* 06-review-aids.js — extracted from templates/index.html. Plain scripts, loaded in
   numbered order; they share one global scope, so load order matters. */
/* ---------- stats + summary ---------- */
function rowSource(r){ const s=r.Source_Column||''; if(s.startsWith('glossary:'))return'Glossary'; if(s.includes('/'))return'Document store'; return'Database'; }
function sourceBreakdown(rows){ const m={}; rows.forEach(r=>{const k=rowSource(r);m[k]=(m[k]||0)+1;}); return m; }
function computeStats(rows){ const conf={High:0,Medium:0,Low:0},sev={HIGH:0,MEDIUM:0,LOW:0},cats=new Set(); let pii=0,enr=0;
  rows.forEach(r=>{ cats.add(r.Category); if(conf[r.Confidence]!=null)conf[r.Confidence]++; if(sev[r.Sensitivity]!=null)sev[r.Sensitivity]++; if(r.PII_Category)pii++; if(r.LLM_Enriched==='Yes')enr++; });
  return {terms:rows.length,categories:cats.size,pii,confidence:conf,sensitivity:sev,enriched:enr}; }
function renderSummary(s, scanned){
  const c=s.confidence||{}, sv=s.sensitivity||{}, src=sourceBreakdown(ROWS), sk=Object.keys(src);
  const srcChip=sk.length>1?`<span class="chip">Sources: ${sk.map(k=>`${k} <b>${src[k]}</b>`).join(' · ')}</span>`:'';
  $('summary').innerHTML=[
    scanned?`<span class="chip">Scanned <b>${scanned.tables}</b> tables · <b>${scanned.columns}</b> cols</span>`:'',
    srcChip,
    `<span class="chip">Terms <b>${s.terms}</b></span>`,
    `<span class="chip">Categories <b>${s.categories}</b></span>`,
    `<span class="chip click ${$('fpii').checked?'active':''}" onclick="$('fpii').checked=!$('fpii').checked;applyFilter()">PII <b class="sens-hi">${s.pii}</b></span>`,
    `<span class="chip">Confidence H<b class="sens-hi">${c.High||0}</b> M<b class="sens-md">${c.Medium||0}</b> L<b class="sens-lo">${c.Low||0}</b></span>`,
    `<span class="chip">Sensitivity HIGH<b class="sens-hi">${sv.HIGH||0}</b> MED<b class="sens-md">${sv.MEDIUM||0}</b> LOW<b class="sens-lo">${sv.LOW||0}</b></span>`,
    s.enriched?`<span class="chip">LLM-enriched <b>${s.enriched}</b></span>`:''
  ].join('');
}
function renderOwnership(o){
  const box=$('ownreport'); if(!o){box.style.display='none';box.innerHTML='';return;}
  const found=o.by_folder&&Object.keys(o.by_folder).length;
  box.style.display=''; box.innerHTML=`<span class="keepcount">Ownership ${found?'✓':'·'}</span>`+(o.signals||[]).map(s=>`<span class="chip">${esc(s)}</span>`).join('')+(found?'<span class="kspacer"></span><span class="msg">owner hints can set the Records &amp; Documents steward</span>':'');
}

/* ---------- discovery charts (Connections page) ---------- */
function barRows(data){
  const max=Math.max(1,...data.map(d=>d.value));
  return data.map(d=>`<div class="crow"><span class="cl" title="${esc(d.label)}">${esc(d.label)}</span><span class="cbar"><i style="width:${Math.round(d.value/max*100)}%;background:${d.color||'var(--teal)'}"></i></span><span class="cv">${d.value}</span></div>`).join('');
}
function renderDiscovery(scanned){
  if(!ROWS.length){ $('discovery').style.display='none'; return; }
  const byCat={}, sev={HIGH:0,MEDIUM:0,LOW:0}, conf={High:0,Medium:0,Low:0}; let pii=0,cde=0;
  ROWS.forEach(r=>{ byCat[r.Category]=(byCat[r.Category]||0)+1; if(sev[r.Sensitivity]!=null)sev[r.Sensitivity]++; if(conf[r.Confidence]!=null)conf[r.Confidence]++; if(r.PII_Category)pii++; if(r.Critical_Data_Element==='Yes')cde++; });
  const catData=Object.entries(byCat).sort((a,b)=>b[1]-a[1]).map(([k,v])=>({label:k,value:v}));
  const sevData=[{label:'HIGH',value:sev.HIGH,color:'#B23A48'},{label:'MEDIUM',value:sev.MEDIUM,color:'#C25E00'},{label:'LOW',value:sev.LOW,color:'#1C7293'}];
  const confData=[{label:'High',value:conf.High,color:'#3C7A57'},{label:'Medium',value:conf.Medium,color:'#B8862A'},{label:'Low',value:conf.Low,color:'#8a9aa3'}];
  const flagData=[{label:'PII',value:pii,color:'#B23A48'},{label:'CDE',value:cde,color:'#065A82'},{label:'Other',value:Math.max(0,ROWS.length-pii),color:'#1C7293'}];
  $('charts').innerHTML=[
    `<div class="chartbox"><h4>Terms by category</h4>${barRows(catData)}</div>`,
    `<div class="chartbox"><h4>Sensitivity</h4>${barRows(sevData)}</div>`,
    `<div class="chartbox"><h4>Confidence</h4>${barRows(confData)}</div>`,
    `<div class="chartbox"><h4>PII &amp; CDE</h4>${barRows(flagData)}</div>`
  ].join('');
  const src=sourceBreakdown(ROWS), sk=Object.keys(src);
  $('discMeta').textContent='— '+ROWS.length+' terms'+(scanned?`, ${scanned.tables} tables · ${scanned.columns} cols`:'')+(sk.length>1?` · ${sk.map(k=>k+' '+src[k]).join(', ')}`:'');
  $('discovery').style.display='';
}

/* ---------- filtering ---------- */
function buildCategoryFilter(){
  const cats=[...new Set(ROWS.map(r=>r.Category))].sort();
  $('fcat').innerHTML='<option value="">All categories</option>'+cats.map(c=>`<option>${esc(c)}</option>`).join('');
  const tags=[...new Set(ROWS.flatMap(r=>(r.Suggested_Tags||'').split(';').map(t=>t.trim()).filter(Boolean)))].sort((a,b)=>a.toLowerCase().localeCompare(b.toLowerCase()));
  const cur=$('ftag').value;
  $('ftag').innerHTML='<option value="">All tags</option>'+tags.map(t=>`<option ${t===cur?'selected':''}>${esc(t)}</option>`).join('');
}
function clearFilters(){ ['q','fcat','fsev','fconf','ftag'].forEach(id=>$(id).value=''); $('fpii').checked=false; $('fkept').checked=false; applyFilter(); }
function applyFilter(){
  const q=$('q').value.trim().toLowerCase(),cat=$('fcat').value,sev=$('fsev').value,conf=$('fconf').value,tag=$('ftag').value,pii=$('fpii').checked,kept=$('fkept').checked;
  SHOWN=[]; ROWS.forEach((r,i)=>{
    if(cat&&r.Category!==cat)return; if(sev&&r.Sensitivity!==sev)return; if(conf&&r.Confidence!==conf)return;
    if(tag){ const ts=(r.Suggested_Tags||'').split(';').map(t=>t.trim()); if(!ts.includes(tag))return; }
    if(pii&&!r.PII_Category)return; if(kept&&!truthy(r.Keep))return;
    if(q){ const h=((r.Term||'')+' '+(r.Definition||'')+' '+(r.Source_Column||'')+' '+(r.Category||'')+' '+(r.Suggested_Tags||'')).toLowerCase(); if(!h.includes(q))return; }
    SHOWN.push(i);
  }); lastShownPos=null; drawRows(); updateKeepUI(); if(typeof renderGroupResolve==='function') renderGroupResolve();
  scheduleRecos();
}
// One data row of the review grid.
function _rowHtml(r, i, pos){ const tt=isTableTerm(r); return `
    <tr class="${truthy(r.Keep)?'':'drop'}${tt?' tterm':''}" id="r${i}">
      <td>${tt
        ? `<input type="checkbox" checked disabled aria-label="Table term — always kept" title="Table-level term — always kept; can't be dropped even at low confidence.">`
        : `<input type="checkbox" ${truthy(r.Keep)?'checked':''} aria-label="Keep ${esc(r.Term)}" onclick="keepClick(event,${i},${pos},this)">`}</td>
      <td><input type="text" value="${esc(r.Category)}" title="${esc(r.Category)}" onchange="upd(${i},'Category',this.value)"></td>
      <td><input type="text" value="${esc(r.Term)}" title="${esc(r.Term)}" onchange="upd(${i},'Term',this.value)">${tt?`<span class="ttbadge" title="Table-level record term — links to the whole table; always kept.">TABLE</span>`:''}${(r.Suggested_Name && r.Suggested_Name!==r.Term)?`<span class="ren" title="LLM-suggested name from a cryptic column — click to use" onclick="useName(${i})">&#8594; ${esc(r.Suggested_Name)}</span>`:''}${(r.PDC_Current&&r.PDC_Current.governed)?`<span class="pdcbadge" title="Already governed in PDC${r.PDC_Current.sensitivity?' · sensitivity '+esc(r.PDC_Current.sensitivity):''}${(r.PDC_Current.trust!=null&&r.PDC_Current.trust!=='')?' · trust '+esc(String(r.PDC_Current.trust)):''}${(r.PDC_Current.terms&&r.PDC_Current.terms.length)?' · terms: '+esc(r.PDC_Current.terms.join(', ')):''}">in PDC</span>`:''}</td>
      <td><textarea title="${esc(r.Definition)}" onchange="upd(${i},'Definition',this.value)">${esc(r.Definition)}</textarea>${(r.LLM_Definition==='Yes'||(r.LLM_Definition===undefined&&r.LLM_Enriched==='Yes'))?'<span class="enr">LLM</span>':''}</td>
      <td><textarea placeholder="purpose…" onchange="upd(${i},'Purpose',this.value)">${esc(r.Purpose||'')}</textarea>${(r.LLM_Purpose==='Yes'||(r.LLM_Purpose===undefined&&r.LLM_Enriched==='Yes'))?'<span class="enr">LLM</span>':''}</td>
      <td><select class="sevsel ${r.Sensitivity}" onchange="upd(${i},'Sensitivity',this.value);this.className='sevsel '+this.value">${['HIGH','MEDIUM','LOW'].map(s=>`<option ${r.Sensitivity===s?'selected':''}>${s}</option>`).join('')}</select>${r.PII_Category?`<div class="sev ${r.Sensitivity}">${esc(r.PII_Category)}</div>`:''}</td>
      <td><select class="cdesel${r.Critical_Data_Element==='Yes'?' cde-true':''}" aria-label="CDE" onchange="upd(${i},'Critical_Data_Element',this.value);this.className='cdesel'+(this.value==='Yes'?' cde-true':'')"><option value="No" ${r.Critical_Data_Element==='Yes'?'':'selected'}>False</option><option value="Yes" ${r.Critical_Data_Element==='Yes'?'selected':''}>True</option></select></td>
      <td><input type="text" value="${esc(r.Suggested_Tags)}" title="${esc(r.Suggested_Tags)}" onchange="upd(${i},'Suggested_Tags',this.value)"></td>
      <td><span class="conf ${r.Confidence}">${r.Confidence}</span></td>
      <td><span class="src" onclick="zoomSource(${i})" title="Click to view all sources">${esc(r.Source_Column)}${(String(r.Source_Column||'').split(';').filter(s=>s.trim()).length>1)?`<span class="more">⤢ ${String(r.Source_Column).split(';').filter(s=>s.trim()).length} sources — click to expand</span>`:''}</span></td>
    </tr>`; }

// Cluster the currently shown rows by their group key. Table terms get a solo key
// (never cluster). Returns ordered keys + members, anchored at first occurrence.
function _gridClusters(){
  _regroupByName();   // detection follows CURRENT names (active resolutions stay frozen)
  const by={}, order=[];
  SHOWN.forEach(i=>{ const r=ROWS[i]; if(!r) return;
    const solo=isTableTerm(r);
    const key=solo ? ('\u0000solo:'+i) : (r._grp!=null ? r._grp : (r.Term||'').trim());
    if(!by[key]){ by[key]=[]; order.push(key); }
    by[key].push(i);
  });
  return {by, order};
}

// Draw the review grid with duplicate candidates clustered under an inline header
// row (the Merge / Disambiguate / Keep separate control lives on that header).

/* ---- duplicate-group decision aid: evidence -> live probe -> AI agent ---- */
let RECO={}, _recoFP='', _recoTimer=null, _lastDbConn=null;
function _dupFingerprint(){
  const by={}; (ROWS||[]).forEach(r=>{ if(!r||!truthy(r.Keep))return; const t=(r.Term||'').trim(); if(t) by[t]=(by[t]||0)+1; });
  return Object.keys(by).filter(t=>by[t]>1).sort().map(t=>t+':'+by[t]).join('|');
}
// background pass: cached scan evidence only (cheap, no DB, no LLM), debounced on data change
function scheduleRecos(){
  const fp=_dupFingerprint();
  if(fp===_recoFP) return;
  _recoFP=fp; clearTimeout(_recoTimer);
  if(!fp){ RECO={}; return; }
  _recoTimer=setTimeout(()=>fetchRecos(false), 500);
}
// full pass (the "AI advise" button): + live data-value probe + AI adjudication
async function fetchRecos(full){
  const btn=$('aiAdviseBtn');
  try{
    if(full&&btn){ btn.disabled=true; btn.textContent='Advising\u2026'; }
    const conn=full?(_lastDbConn||((CONNS||[]).find(c=>c.type==='db')||{}).config||null):null;
    const d=await (await fetch('/api/recommend-resolutions',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({rows:ROWS, conn:conn, ai:!!full})})).json();
    RECO={}; (d.groups||[]).forEach(g=>{ RECO[g.name]=g; });
    drawRows();
    if(full&&$('msg')) $('msg').textContent = d.used_llm
      ? `AI adjudicated the ambiguous duplicate groups${d.probed?` (live-probed ${d.probed} group${d.probed!==1?'s':''})`:''}.`
      : (d.probed?`Live-probed ${d.probed} group(s); Ollama offline so evidence decides.`:'Evidence-only recommendations (Ollama offline, no ambiguous groups probed).');
  }catch(e){ if(full&&$('msg')) $('msg').textContent='Advise failed: '+(e.message||e); }
  finally{ if(btn){ btn.disabled=false; btn.textContent='AI advise'; } }
}
function drawRows(){
  if(!ROWS.length){ $('rows').innerHTML='<tr><td colspan="10" class="empty">Scan a connection to suggest glossary terms.</td></tr>'; return; }
  if(!SHOWN.length){ $('rows').innerHTML='<tr><td colspan="10" class="empty">No terms match the filter.</td></tr>'; return; }
  const {by, order}=_gridClusters();
  // clustered visual order — members contiguous; keep SHOWN aligned so pos / shift-select match what's rendered
  const vis=[]; order.forEach(k=>by[k].forEach(i=>vis.push(i))); SHOWN=vis;
  _GRIDGRP=[];
  let html='', pos=0;
  order.forEach(k=>{
    const idxs=by[k];
    const solo=(k.indexOf('\u0000solo:')===0);
    const act=(GRP[k]&&GRP[k].action)||'separate';
    const cluster=!solo && (idxs.length>1 || act!=='separate');   // keep the header after a merge so it stays reversible
    if(cluster){
      const gk=_GRIDGRP.length; _GRIDGRP.push(k);
      const tag=act==='merge'?' &rarr; merged into one':act==='split'?' &rarr; split &amp; renamed':'';
      const rec=(idxs.length>1)?RECO[k]:null;   // advice only while undecided candidates exist
      const seg=(v,l)=>`<button class="gseg${act===v?' on':''}${rec&&rec.action===v&&act==='separate'?' rec':''}" onclick="gridGroupSet(${gk},'${v}')">${l}</button>`;
      let recHtml='';
      if(rec&&rec.action){
        const lbl=rec.action==='merge'?'Merge':rec.action==='split'?'Disambiguate':'Keep separate';
        const band=rec.band==='high'?'':'<span class="gband" style="background:#fdecc8;color:#7a4a00">check</span>';
        const src=rec.source==='ai'?'<span class="gband" style="background:#EDE7F6;color:#4527A0">AI</span>':'';
        recHtml=`<span class="grec">Recommended: <b>${lbl}</b>${band}${src} &mdash; ${esc(rec.reason||'')}</span>`;
      }
      html+=`<tr class="gclhead"><td colspan="10"><div class="gclwrap">`
          +`<span class="gclname" title="${esc(k)}">${esc(k)}<span class="gcldup">duplicate</span></span>`
          +`<span class="gclcnt">${idxs.length} candidate${idxs.length!==1?'s':''}${tag}</span>`
          +`<span class="gsegs">${seg('merge','Merge')}${seg('split','Disambiguate')}${seg('separate','Keep separate')}</span>`
          +recHtml
          +`</div></td></tr>`;
    }
    idxs.forEach(i=>{ html+=_rowHtml(ROWS[i], i, pos); pos++; });
  });
  $('rows').innerHTML=html;
}
// Resolve a header's action against the group name captured for this render.
function gridGroupSet(k, action){ const name=_GRIDGRP[k]; if(name!=null) groupSet(name, action); }
function upd(i,k,v){ ROWS[i][k]=v; if(k==='Category')buildCategoryFilter(); }
function useName(i){ const sgg=ROWS[i].Suggested_Name; if(!sgg)return; const old=(ROWS[i].Term||'');
  let n=0; ROWS.forEach(r=>{ if((r.Term||'')===old){ r.Term=sgg; if(r.Suggested_Name) delete r.Suggested_Name; r.LLM_Name='Used'; n++; } });
  applyFilter(); if($('msg')) $('msg').textContent = n>1
    ? `Renamed all ${n} instances of “${old}” → “${sgg}” — kept as one mergeable term.`
    : `Renamed to “${sgg}”.`; }
function useAllNames(){ let n=0; ROWS.forEach(r=>{ if(r.Suggested_Name && r.Suggested_Name!==r.Term){ r.Term=r.Suggested_Name; delete r.Suggested_Name; r.LLM_Name='Used'; n++; } }); if(n){ applyFilter(); $('msg').textContent=`Applied ${n} suggested name${n!==1?'s':''}.`; } }
let SIM=[];
async function findSimilar(){
  const btn=$('simBtn'), thr=parseFloat(($('simThresh')&&$('simThresh').value)||'0.6');
  if($('simList')) $('simList').innerHTML='<p class="msg" style="padding:4px">Scoring…</p>';
  if($('simPanel')) $('simPanel').style.display='';
  try{
    if(btn) btn.disabled=true;
    const d=await (await fetch('/api/similarity',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rows:ROWS,threshold:thr})})).json();
    SIM=d.suggestions||[]; renderSim();
  }catch(e){ if($('simList')) $('simList').innerHTML='<p class="msg">Similarity failed: '+esc(String(e))+'</p>'; }
  finally{ if(btn) btn.disabled=false; }
}
function _simBar(v,c){ return `<div style="flex:0 0 42px;height:7px;background:#e6eef2;border-radius:4px;overflow:hidden;display:inline-block;vertical-align:middle"><div style="height:100%;width:${Math.round((v||0)*100)}%;background:${c}"></div></div>`; }
function renderSim(){
  const el=$('simList'); if(!el) return;
  if(!SIM.length){ el.innerHTML='<p class="msg" style="padding:4px">No same-concept name pairs above the threshold — lower it to widen the net.</p>'; return; }
  el.innerHTML=SIM.map((s,idx)=>{
    const band=s.band==='high'?'<span style="font-size:9.5px;font-weight:700;padding:1px 6px;border-radius:8px;background:#DDF0E4;color:#1B6B45">strong</span>'
      :s.band==='conflict'?'<span style="font-size:9.5px;font-weight:700;padding:1px 6px;border-radius:8px;background:#fdeeee;color:#8a1f1f">different concepts</span>'
      :'<span style="font-size:9.5px;font-weight:700;padding:1px 6px;border-radius:8px;background:#fdecc8;color:#7a4a00">review</span>';
    const evLine=s.evidence_reason?`<div style="margin-top:3px;font-size:10.5px;color:${s.evidence==='different'?'#8a1f1f':'#1B6B45'}">${esc(s.evidence_reason)}${s.evidence==='different'?' \u2014 do not merge; rename with qualifiers if they collide':''}</div>`:'';
    const sg=s.signals||{};
    return `<div style="display:flex;align-items:center;gap:10px;padding:7px 4px;border-top:1px solid #e4eef2">
      <div style="flex:1;min-width:0">
        <div style="font-size:13px;word-break:break-word"><b>${esc(s.keep)}</b> <span style="color:var(--mute)">(${s.keep_count})</span> <span style="color:var(--mute)">&larr; merge</span> <b>${esc(s.drop)}</b> <span style="color:var(--mute)">(${s.drop_count})</span></div>
        <div style="display:flex;align-items:center;gap:12px;margin-top:3px;font-size:10.5px;color:var(--mute);flex-wrap:wrap">
          <span style="font-weight:700;color:${s.score>=0.85?'#1B6B45':'#7a4a00'}">score ${s.score.toFixed(2)}</span> ${band}
          <span>name ${_simBar(sg.lexical,'#1C7293')}</span>
          <span>tokens ${_simBar(sg.token,'#2EC4B6')}</span>
          <span>context ${_simBar(sg.structural,'#14333F')}</span>
        </div>
        ${evLine}
      </div>
      ${s.band==='conflict'?'':`<button class="ghost sm" title="Swap which name is kept" onclick="simFlip(${idx})">&#8646;</button>
      <button class="ghost sm" onclick="simMerge(${idx})" style="border-color:#2EC4B6;color:#0A3D52;font-weight:600">Merge</button>`}
      <button class="ghost sm" onclick="simDismiss(${idx})">Dismiss</button>
    </div>`;
  }).join('');
}
function simFlip(idx){ const s=SIM[idx]; if(!s)return; const k=s.keep,c=s.keep_count; s.keep=s.drop; s.keep_count=s.drop_count; s.drop=k; s.drop_count=c; renderSim(); }
function simMerge(idx){ const s=SIM[idx]; if(!s)return; const keep=s.keep, drop=s.drop;
  let n=0; (ROWS||[]).forEach(r=>{ if((r.Term||'')===drop){ r.Term=keep; if(r.Suggested_Name===keep) delete r.Suggested_Name; n++; } });
  SIM=SIM.filter(x=>x.keep!==drop && x.drop!==drop);
  if(typeof applyFilter==='function') applyFilter();
  renderSim();
  if($('msg')) $('msg').textContent=`Merged “${drop}” into “${keep}” (${n} row${n!==1?'s':''}). Run Merge duplicates to collapse into one row.`;
}
function simDismiss(idx){ SIM.splice(idx,1); renderSim(); }
async function suggestTags(){
  const msg=$('msg'); if(!ROWS.length){ msg.textContent='Nothing to tag yet — scan or load a glossary first.'; return; }
  const btn=$('retagBtn'); if(btn) btn.disabled=true; msg.textContent='Deriving meaningful tags…';
  try{
    const d=await (await fetch('/api/retag',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rows:ROWS})})).json();
    if(d.error) throw new Error(d.error);
    const out=d.rows||[]; let n=0;
    for(let i=0;i<ROWS.length && i<out.length;i++){ const nt=out[i].Suggested_Tags||''; if(nt!==ROWS[i].Suggested_Tags){ ROWS[i].Suggested_Tags=nt; n++; } }
    applyFilter(); updateKeepUI();
    msg.textContent='Re-tagged '+n+' term'+(n===1?'':'s')+' from the controlled vocabulary (category, name, sensitivity, PII and key signals). Table terms keep their table-level tags.';
  }catch(e){ msg.textContent='Suggest tags failed: '+(e.message||e); }
  finally{ if(btn) btn.disabled=false; }
}
