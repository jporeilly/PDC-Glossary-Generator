/* 10-agents.js — extracted from templates/index.html. Plain scripts, loaded in
   numbered order; they share one global scope, so load order matters. */
/* ---------- enrich + enhance + generate ---------- */
let ENRICH_CANCEL=false;
function cancelEnrich(){ ENRICH_CANCEL=true; $('epCancel').disabled=true; $('epLbl').textContent='Finishing current batch…'; }

/* ---- shared AI progress bar: QA / categorize / AI suggest reuse the enrich bar ---- */
let AI_CANCEL=false;
function aiProgStart(label,total){
  AI_CANCEL=false;
  const c=$('epCancel');
  if(c){ c.disabled=false; c.onclick=()=>{ AI_CANCEL=true; c.disabled=true; $('epLbl').textContent='Finishing current batch…'; }; }
  $('enrichProg').style.display='flex';
  aiProgUpdate(0,total,label);
}
function aiProgUpdate(done,total,label){
  const pct=Math.round(100*done/Math.max(total,1));
  $('epFill').style.width=pct+'%';
  if(!AI_CANCEL) $('epLbl').textContent=`${label} — ${done}/${total} (${pct}%)`;
}
function aiProgEnd(){
  $('enrichProg').style.display='none';
  const c=$('epCancel'); if(c){ c.onclick=cancelEnrich; c.disabled=false; }
}
function epUpdate(done,total,dd,pp){
  const v=total?Math.round(done/total*100):0;
  $('epFill').style.width=v+'%';
  $('epLbl').textContent=`Enriching ${done} of ${total} (${v}%)${(dd||pp)?` \u00b7 ${dd} def, ${pp} purpose`:''} \u00b7 ${COMPUTE.toUpperCase()}`;
}
/* ---- AI QA definitions: linter + agent flags, steward applies ---- */
async function qaDefs(){
  const total=ROWS.length; if(!total) return;
  const btn=$('qaBtn'); btn.disabled=true; $('msg').textContent='';
  aiProgStart('QA-checking definitions',total);
  const CHUNK=6; let offline=false, failed=0;
  for(let s2=0; s2<total && !AI_CANCEL; s2+=CHUNK){
    const idx=[]; for(let i=s2;i<Math.min(s2+CHUNK,total);i++) idx.push(i);
    try{
      const d=await (await fetch('/api/qa-definitions',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({rows:idx.map(i=>ROWS[i]),ai:true,model:currentModel()||null,compute:COMPUTE})})).json();
      if(d.error){ failed+=idx.length; }
      else{
        if(d.llm && d.llm.online===false) offline=true;
        (d.rows||[]).forEach((nr,j)=>{ const i=idx[j]; if(i==null)return;
          const old2=ROWS[i]||{};
          ['_grp','_rid','_res'].forEach(f=>{ if(nr[f]==null&&old2[f]!=null) nr[f]=old2[f]; });
          if(nr.Keep==null&&old2.Keep!=null) nr.Keep=old2.Keep;
          ROWS[i]=nr; });
      }
      aiProgUpdate(Math.min(s2+CHUNK,total),total,'QA-checking definitions');
    }catch(e){ failed+=idx.length; }
  }
  aiProgEnd(); btn.disabled=false; renderQA(offline, failed); applyFilter();
  if(AI_CANCEL && $('msg')) $('msg').textContent+=' (stopped early — rows already checked keep their flags)';
}
function renderQA(offline, failed){
  const flagged=[]; ROWS.forEach((r,i)=>{ if(r&&r.QA_Issues) flagged.push(i); });
  if($('qaPanel')) $('qaPanel').style.display='';
  if($('qaSummary')) $('qaSummary').textContent=flagged.length
    ? `${flagged.length} of ${ROWS.length} definitions flagged`+(offline?' (linter only \u2014 Ollama offline)':'')+(failed?` \u00b7 ${failed} row(s) failed`:'')
    : 'all definitions look sound'+(offline?' (linter only \u2014 Ollama offline)':'');
  if($('msg')) $('msg').textContent=flagged.length?`Definition QA: ${flagged.length} flagged.`:'Definition QA: nothing flagged.';
  if(!$('qaList')) return;
  const bulkbar=flagged.length?`<div style="display:flex;align-items:center;gap:10px;padding:5px 4px 7px;border-bottom:1px solid #cfe0e8">
      <label style="font-size:12px;font-weight:600"><input type="checkbox" id="qaAll" checked onchange="qaToggleAll(this)"> Select / deselect all</label>
      <span style="flex:1"></span>
      <button class="ghost sm" onclick="qaUseSelected()" style="border-color:#2EC4B6;color:#0A3D52;font-weight:600">Use selected suggestions</button>
      <button class="ghost sm" onclick="qaDismissSelected()">Dismiss selected</button>
    </div>`:'';
  $('qaList').innerHTML=flagged.length?bulkbar+flagged.map(i=>{
    const r=ROWS[i];
    const sugg=r.QA_Suggestion?`<div style="margin-top:3px;font-size:12px;color:#1B6B45">Suggestion: ${esc(r.QA_Suggestion)}</div>`:'';
    return `<div style="padding:7px 4px;border-top:1px solid #e4eef2">
      <div style="display:flex;align-items:center;gap:10px">
        <input type="checkbox" class="qasel" data-i="${i}" checked style="flex:0 0 auto" aria-label="select ${esc(r.Term||'')}">
        <div style="flex:1;min-width:0">
          <b style="font-size:13px">${esc(r.Term||'')}</b> <span class="hint">${esc(r.Category||'')}</span>
          <div style="font-size:11px;color:#8a1f1f;margin-top:2px">${esc((r.QA_Issues||'').split(';').join(' \u00b7 '))}</div>
          <div style="font-size:12px;color:var(--mute);margin-top:2px">Current: ${esc(r.Definition||'')}</div>
          ${sugg}
        </div>
        ${r.QA_Suggestion?`<button class="ghost sm" onclick="qaUse(${i})" style="border-color:#2EC4B6;color:#0A3D52;font-weight:600">Use suggestion</button>`:''}
        <button class="ghost sm" onclick="qaDismiss(${i})">Dismiss</button>
      </div>
    </div>`;
  }).join(''):'<p class="msg" style="padding:4px">No issues found.</p>';
}
function qaToggleAll(cb){ document.querySelectorAll('#qaList .qasel').forEach(c=>{ c.checked=cb.checked; }); }
function _qaSelected(){ return [...document.querySelectorAll('#qaList .qasel:checked')].map(c=>parseInt(c.dataset.i,10)).filter(i=>!isNaN(i)); }
function qaUseSelected(){
  let used=0;
  _qaSelected().forEach(i=>{ const r=ROWS[i];
    if(r&&r.QA_Suggestion){ r.Definition=r.QA_Suggestion; delete r.QA_Suggestion; delete r.QA_Issues; used++; } });
  renderQA(); applyFilter();
  if($('msg')) $('msg').textContent=used?`Applied ${used} suggested definition${used!==1?'s':''}.`:'None of the selected rows carried a suggestion \u2014 dismiss or edit them instead.';
}
function qaDismissSelected(){
  let n=0;
  _qaSelected().forEach(i=>{ const r=ROWS[i]; if(r){ delete r.QA_Suggestion; delete r.QA_Issues; n++; } });
  renderQA();
  if($('msg')) $('msg').textContent=`Dismissed ${n} flag${n!==1?'s':''}.`;
}
function qaUse(i){ const r=ROWS[i]; if(!r||!r.QA_Suggestion)return; r.Definition=r.QA_Suggestion; delete r.QA_Suggestion; delete r.QA_Issues; renderQA(); applyFilter(); }
function qaDismiss(i){ const r=ROWS[i]; if(!r)return; delete r.QA_Suggestion; delete r.QA_Issues; renderQA(); }

/* ---- AI categorize: file uncategorized terms into known categories ---- */
async function aiCategorize(){
  const total=ROWS.length; if(!total) return;
  const btn=$('catBtn'); btn.disabled=true; $('msg').textContent='';
  aiProgStart('AI categorizing',total);
  const CHUNK=6; let updated=0, offline=false, failed=0;
  // whole-glossary category list travels with every chunk so each slice chooses
  // from the SAME known set, not just its own categories
  const cats=[...new Set(ROWS.map(r=>(r.Category||'').trim()).filter(Boolean))];
  for(let s2=0; s2<total && !AI_CANCEL; s2+=CHUNK){
    const idx=[]; for(let i=s2;i<Math.min(s2+CHUNK,total);i++) idx.push(i);
    try{
      const d=await (await fetch('/api/ai-categorize',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({rows:idx.map(i=>ROWS[i]),categories:cats,only_blank:true,model:currentModel()||null,compute:COMPUTE})})).json();
      if(d.error){ failed+=idx.length; }
      else if(d.llm && d.llm.online===false){ offline=true; break; }
      else{
        (d.rows||[]).forEach((nr,j2)=>{ const i=idx[j2]; if(i==null)return; const old2=ROWS[i]||{};
          ['_grp','_rid','_res'].forEach(f=>{ if(nr[f]==null&&old2[f]!=null) nr[f]=old2[f]; });
          if(nr.Keep==null&&old2.Keep!=null) nr.Keep=old2.Keep;
          ROWS[i]=nr; });
        updated+=d.updated||0;
      }
      aiProgUpdate(Math.min(s2+CHUNK,total),total,'AI categorizing');
    }catch(e){ failed+=idx.length; }
  }
  aiProgEnd(); btn.disabled=false; buildCategoryFilter(); applyFilter();
  $('msg').textContent = offline ? 'Ollama offline — categorization needs the local model.'
    : `AI filed ${updated} term(s) into categories`+(AI_CANCEL?' (stopped early)':'')+(failed?` · ${failed} row(s) failed`:'')+(updated?'.':' — all rows already have categories.');
}

async function aiSuggest(){
  const total=ROWS.length; if(!total) return;
  const idx=ROWS.map((_,i)=>i);
  $('aiSuggestBtn').disabled=true; $('msg').textContent='';
  aiProgStart('AI suggesting from scan evidence',total);
  const CHUNK=6; let done=0, cn={names:0,tags:0,sensitivity:0,category:0}, offline=false, failed=0;
  for(let s2=0; s2<idx.length && !AI_CANCEL; s2+=CHUNK){
    const slice=idx.slice(s2,s2+CHUNK);
    const payload=slice.map(i=>ROWS[i]);
    try{
      const d=await (await fetch('/api/ai-suggest',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({rows:payload,model:currentModel()||null,compute:COMPUTE})})).json();
      if(d.error){ failed+=slice.length; }
      else if(d.llm && d.llm.online===false){ offline=true; break; }
      else{
        (d.rows||[]).forEach((nr,j)=>{ const i=slice[j]; if(i==null) return;
          const old=ROWS[i]||{};
          ['_grp','_rid','_res'].forEach(f=>{ if(nr[f]==null && old[f]!=null) nr[f]=old[f]; });
          if(nr.Keep==null && old.Keep!=null) nr.Keep=old.Keep;
          ROWS[i]=nr; });
        const u=d.updated||{}; cn.names+=u.names||0; cn.tags+=u.tags||0;
        cn.sensitivity+=u.sensitivity||0; cn.category+=u.category||0;
      }
    }catch(e){ failed+=slice.length; }
    done+=slice.length;
    aiProgUpdate(done,total,'AI suggesting from scan evidence');
    applyFilter(); renderSummary(computeStats(ROWS));
    await new Promise(r=>requestAnimationFrame(r));
  }
  aiProgEnd(); $('aiSuggestBtn').disabled=false;
  if(AI_CANCEL && !offline){ const any0=cn.names+cn.tags+cn.sensitivity+cn.category; $('msg').textContent=`Stopped early — ${any0} change(s) applied so far.`; return; }
  if(offline){ $('msg').textContent='LLM offline \u2014 start Ollama and pull a model, then try again.'; return; }
  const any=cn.names+cn.tags+cn.sensitivity+cn.category;
  $('msg').textContent=any?`AI(evidence): suggested ${cn.names} name${cn.names!==1?'s':''} (\u2192 chips), added governed tags on ${cn.tags} row${cn.tags!==1?'s':''}, tightened sensitivity on ${cn.sensitivity}, moved ${cn.category} categor${cn.category!==1?'ies':'y'}${failed?` (${failed} skipped)`:''}.`:'AI made no changes \u2014 the scan evidence already agrees with the suggestions.';
}
async function enrich(){
  const total=ROWS.length; if(!total) return;
  // snapshot before enriching so trying a different model is non-destructive
  PRE_ENRICH={rows:_deep(ROWS), model:(currentModel()||'default'), at:Date.now()};
  if(typeof updateRevertEnrichUI==='function') updateRevertEnrichUI();
  const idx=ROWS.map((_,i)=>i);                 // map results back even while filtered
  ENRICH_CANCEL=false; $('enrichBtn').disabled=true; if($('aiSuggestBtn')) $('aiSuggestBtn').disabled=$('enrichBtn').disabled; $('epCancel').disabled=false;
  $('enrichProg').style.display='flex'; epUpdate(0,total,0,0); $('msg').textContent='';
  const CHUNK=6; let done=0, dd=0, pp=0, nn=0, offline=false, failed=0;
  for(let s=0; s<idx.length && !ENRICH_CANCEL; s+=CHUNK){
    const slice=idx.slice(s,s+CHUNK);
    const payload=slice.map(i=>ROWS[i]);
    try{
      const d=await (await fetch('/api/enrich',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({rows:payload,model:currentModel()||null,compute:COMPUTE})})).json();
      if(d.error){ failed+=slice.length; }
      else if(d.llm && d.llm.online===false){ offline=true; break; }
      else{
        // Preserve client-side identity across the round-trip: group key, row id,
        // resolution tag, keep state. The server usually echoes them, but group
        // integrity must not depend on what the LLM endpoint returns.
        (d.rows||[]).forEach((nr,j)=>{ const i=slice[j]; if(i==null) return;
          const old=ROWS[i]||{};
          ['_grp','_rid','_res'].forEach(f=>{ if(nr[f]==null && old[f]!=null) nr[f]=old[f]; });
          if(nr.Keep==null && old.Keep!=null) nr.Keep=old.Keep;
          ROWS[i]=nr; });
        dd+=d.definitions||0; pp+=d.purposes||0; nn+=d.names||0;
      }
    }catch(e){ failed+=slice.length; }
    done+=slice.length;
    epUpdate(done,total,dd,pp);
    applyFilter(); renderSummary(computeStats(ROWS));   // live: watch terms fill in
    await new Promise(r=>requestAnimationFrame(r));      // let the UI paint
  }
  $('enrichProg').style.display='none'; $('enrichBtn').disabled=false; if($('aiSuggestBtn')) $('aiSuggestBtn').disabled=$('enrichBtn').disabled;
  if(offline){ $('msg').textContent='LLM offline — start Ollama and pull a model, then try again.'; }
  else if(ENRICH_CANCEL){ $('msg').textContent=`Stopped — improved ${dd} definition${dd!==1?'s':''} and ${pp} purpose${pp!==1?'s':''} so far.`; }
  else{ const nm=nn?` and suggested ${nn} name${nn!==1?'s':''} (click a → chip to apply)`:''; const mdl=(PRE_ENRICH&&PRE_ENRICH.model)?` with ${esc(PRE_ENRICH.model)}`:''; $('msg').textContent=(dd||pp||nn)?`Improved ${dd} definition${dd!==1?'s':''} and ${pp} purpose${pp!==1?'s':''}${nm}${mdl}${failed?` (${failed} skipped)`:''}.`:'LLM made no changes.'; }
  if(typeof updateRevertEnrichUI==='function') updateRevertEnrichUI();
}
function updateRevertEnrichUI(){
  const b=document.getElementById('revertEnrichBtn'); if(!b) return;
  b.style.display = PRE_ENRICH ? '' : 'none';
  if(PRE_ENRICH) b.title = 'Undo the last Enrich run (from '+(PRE_ENRICH.model||'default')+') and restore the definitions/purposes from just before it. Keeps your prune/merge/edits.';
}
function revertEnrich(){
  if(!PRE_ENRICH) return;
  ROWS=_deep(PRE_ENRICH.rows);
  const was=PRE_ENRICH.model||'default';
  PRE_ENRICH=null;
  applyFilter(); renderSummary(computeStats(ROWS)); if(PEOPLE_LOADED&&typeof buildCatTable==='function') buildCatTable();
  updateRevertEnrichUI();
  if($('msg')) $('msg').textContent=`Reverted the “${esc(was)}” enrichment — try another model, or Enrich again.`;
}
/* ---------- saved glossary workspaces ---------- */
async function loadGlossaryList(){
  try{
    const items=(await (await fetch('/api/glossaries')).json()).glossaries||[];
    const sel=$('loadSel'); sel.innerHTML='<option value="">Load saved…</option>'+items.map(g=>`<option value="${g.id}">${esc(g.name||g.glossary_name)} (${g.terms})</option>`).join('');
    $('savedRows').innerHTML=items.length?items.map(g=>`<tr>
      <td><b>${esc(g.name||'(unnamed)')}</b></td><td>${esc(g.glossary_name||'')}</td>
      <td>${g.terms}</td><td>${g.kept}</td><td>${g.has_discovery?'✓':'—'}</td>
      <td class="msg">${esc((g.savedAt||'').replace('T',' '))}</td>
      <td><button class="ghost sm" onclick="loadGlossary('${g.id}')">Load</button> <button class="danger sm" onclick="delGlossary('${g.id}')">Delete</button></td>
    </tr>`).join(''):'<tr><td colspan="7" class="msg">No saved glossaries yet.</td></tr>';
  }catch(e){}
}
async function saveGlossary(){
  if(!ROWS.length){ return; }
  const def=CUR_GLOSS?(CUR_GLOSS.name||''):$('gname').value;
  const name=prompt('Save glossary as:', def||'Business Glossary'); if(name===null) return;
  const body={id:CUR_GLOSS?CUR_GLOSS.id:null, name, glossary_name:$('gname').value,
              rows:ROWS, governance:(PEOPLE_LOADED?buildGovernance():null),
              discovery:LAST_DISCOVERY, summary:computeStats(ROWS)};
  try{
    const d=await (await fetch('/api/glossaries',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).json();
    CUR_GLOSS={id:d.id,name:d.name}; GLOSSARY_SAVED=true; rememberGloss(d.id); loadGlossaryList(); renderReady();
    $('msg').innerHTML=`Saved as <b>${esc(d.name)}</b> at ${esc((d.savedAt||'').replace('T',' '))}.`;
  }catch(e){ $('msg').textContent='Save failed: '+e; }
}
function rememberGloss(id){
  // the app auto-resumes this glossary on next start (settings.json survives restarts)
  try{ fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({last_glossary:id})}); }catch(e){}
}
async function loadGlossary(id,quiet){
  try{
    const d=await (await fetch('/api/glossaries/'+id)).json();
    if(d.error){ $('msg').textContent=d.error; return; }
    rememberGloss(id);
    ROWS=d.rows||[]; CUR_GLOSS={id:d.id,name:d.name}; snapshotScan();
    if(d.glossary_name) $('gname').value=d.glossary_name;
    buildCategoryFilter(); clearFilters(); renderSummary(computeStats(ROWS));
    $('enhanceBtn').disabled=!ROWS.length; $('saveGlossBtn').disabled=!ROWS.length;
    $('filterbar').style.display=''; $('keepbar').style.display=''; $('glossHint').textContent='';
    if(d.discovery){ LAST_DISCOVERY=d.discovery; renderDiscoveryPanel(d.discovery); }
    if(!PEOPLE_LOADED) await loadPeople();
    if(ROWS.length) buildCatTable();
    applyGovernance(d.governance);
    if(!quiet) showPage('glossary');
    $('msg').innerHTML=`${quiet?'Auto-resumed':'Loaded'} <b>${esc(d.name||d.glossary_name)}</b> — ${ROWS.length} terms${d.discovery?', with discovery':''}${d.governance?', governance restored':''}${quiet?' <span class="hint">(your last saved glossary — Load saved… to open a different one)</span>':''}.`;
  }catch(e){ $('msg').textContent='Load failed: '+e; }
}
async function delGlossary(id){
  if(!confirm('Delete this saved glossary?')) return;
  await fetch('/api/glossaries/'+id,{method:'DELETE'}); if(CUR_GLOSS&&CUR_GLOSS.id===id)CUR_GLOSS=null; loadGlossaryList();
}
function applyGovernance(gov){
  if(!gov) return;
  if(gov.status) $('g_status').value=gov.status;
  if(gov.domain && $('g_domain')) $('g_domain').value=gov.domain;
  if(gov.ratingMode==='auto') { $('g_rating').value='auto'; onGlobalRatingChange(); }
  else if(gov.rating!=null) $('g_rating').value=String(gov.rating);
  if(gov.reviewedAt) $('g_reviewed').value=gov.reviewedAt;
  $('g_applycats').checked=gov.applyToCategories!==false;
  const d=gov.default||{};
  if(d.businessSteward) $('g_steward').value=d.businessSteward;
  if(d.owner) $('g_owner').value=d.owner;
  if(d.custodian) $('g_custodian').value=d.custodian;
  (d.stakeholders||[]).forEach(s=>{ const cb=document.querySelector('#g_stakeholders .stk[value="'+s.id+'"]'); if(cb)cb.checked=true; });
  SAVED_CAT_OV=gov.categories||{};
  document.querySelectorAll('#g_catcards .catcard').forEach(card=>{ ccApply(card,SAVED_CAT_OV[card.dataset.cat]); ccUpdate(card); });
}

async function loadGlossaryForReview(input){
  const f=input.files&&input.files[0]; if(!f)return;
  $('glossHint').textContent='Loading '+f.name+'…';
  try{ const text=await f.text();
    const d=await (await fetch('/api/load-glossary',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({glossary:text})})).json();
    if(d.error){$('glossHint').textContent=d.error;input.value='';return;}
    ROWS=d.rows; buildCategoryFilter(); clearFilters(); renderSummary(computeStats(ROWS)); renderOwnership(null); snapshotScan();
    if(PEOPLE_LOADED)buildCatTable(); renderDiscovery();
    $('enhanceBtn').disabled=!ROWS.length; $('saveGlossBtn').disabled=!ROWS.length; $('filterbar').style.display=''; $('keepbar').style.display=''; $('glossHint').textContent='';
    const rp=d.report||{}; $('msg').innerHTML=`Loaded <b>${rp.terms||0}</b> terms from <b>${esc(rp.glossary||f.name)}</b> for review.`;
  }catch(e){ $('glossHint').textContent='Load failed: '+e; } input.value='';
}

async function enhanceFromGlossary(input){
  const f=input.files&&input.files[0]; if(!f||!ROWS.length){input.value='';return;}
  $('msg').textContent='Reading '+f.name+'…';
  try{ const text=await f.text();
    const d=await (await fetch('/api/enhance-glossary',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rows:ROWS,glossary:text,append_missing:true})})).json();
    if(d.error){$('msg').textContent=d.error;input.value='';return;}
    ROWS=d.rows; buildCategoryFilter(); applyFilter(); renderSummary(computeStats(ROWS)); if(PEOPLE_LOADED)buildCatTable(); snapshotScan();
    const rp=d.report||{}; $('msg').innerHTML=`Enhanced from <b>${esc(rp.glossary||f.name)}</b>: <b>${rp.matched||0}</b> matched, <b>${rp.added||0}</b> added.`;
  }catch(e){ $('msg').textContent='Enhance failed: '+e; } input.value='';
}
/* ---- policy drafter: detection seeds -> PDC pattern/dictionary rule files ---- */
async function draftPolicies(){
  const M=$('govGenMsg')||$('msg');
  if(!ROWS.length){ M.textContent='Scan and review terms first \u2014 there are no detection seeds to draft from yet.'; return; }
  const btn=$('draftPolBtn'); if(btn){ btn.disabled=true; btn.textContent='Drafting\u2026'; }
  try{
    const body={rows:ROWS, glossary_name:$('gname')?$('gname').value:'', ai:true, model:currentModel()||null, compute:COMPUTE};
    const d=await (await fetch('/api/draft-policies',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).json();
    const np=(d.patterns||[]).length, nd=(d.dictionaries||[]).length, ns=(d.skipped||[]).length;
    if(!np&&!nd){ M.textContent=`No detection seeds found \u2014 ${ns} term(s) skipped. Scan a live connection so profiling can induce value formats / reference lists first.`; return; }
    const zr=await fetch('/api/draft-policies',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.assign({},body,{format:'zip'}))});
    const url=URL.createObjectURL(await zr.blob());
    const list=[...(d.patterns||[]).map(x=>`<li><b>${esc(x.name)}</b> <span class="hint">pattern${x.seed==='canonical'?" (canonical shape)":''} \u00b7 ${esc(x.filename)}</span></li>`),
                ...(d.dictionaries||[]).map(x=>`<li><b>${esc(x.name)}</b> <span class="hint">dictionary \u00b7 ${esc(x.filename)} + ${esc(x.values)}</span></li>`)].join('');
    const skiplist=ns?`<details style="margin-top:6px"><summary style="cursor:pointer;font-size:12px;color:var(--mute)">${ns} term(s) skipped \u2014 why?</summary><ul style="margin:4px 0 0 18px;font-size:11.5px;color:var(--mute)">${(d.skipped||[]).map(x=>`<li><b>${esc(x.term)}</b> \u2014 ${esc(x.why)}</li>`).join('')}</ul></details>`:'';
    M.innerHTML=`Drafted <b>${np}</b> pattern(s) + <b>${nd}</b> dictionar${nd===1?'y':'ies'}${d.used_llm?' · AI-polished':''}<div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:10px 0 6px"><a class="dlbig" href="${url}" download="drafted-policies.zip">&#11015; Download drafted policies (zip)</a><span class="hint">Patterns/ + Dictionaries/ + INDEX.csv</span></div><div class="nextsteps">&#9888;&#65039; These ARE the draft Data Identification policies: <b>1.</b> Download &rarr; <b>2.</b> review each rule &rarr; <b>3.</b> PDC: <b>Management &rarr; Data Identification &rarr; Patterns / Dictionaries &rarr; Import</b> &rarr; <b>4.</b> run identification on your sources</div><ul style="margin:8px 0 0 18px;font-size:12px">${list}</ul>${skiplist}<span class="hint">Skipped terms are normal: free text, names and amounts have no stable shape — identify those with dictionaries or business rules.</span>`;
  }catch(e){ M.textContent='Draft failed: '+(e.message||e); }
  finally{ if(btn){ btn.disabled=false; btn.innerHTML='Draft policies (AI) &rarr;'; } }
}
async function generate(msgId){
  const M=$(msgId)||$('msg');
  if(!ROWS.length){ M.textContent='Scan and review terms first \u2014 there\u2019s nothing to export yet.'; return; }
  if($('genBtn'))$('genBtn').disabled=true; if($('govGenBtn'))$('govGenBtn').disabled=true;
  M.textContent='Generating\u2026'; const governance=buildGovernance(); saveSettings();
  try{ const d=await (await fetch('/api/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rows:ROWS,glossary_name:$('gname').value,governance})})).json();
    const url=URL.createObjectURL(new Blob([d.jsonl],{type:'application/json'})); const s=d.stats;
    let gov=''; if(governance&&(governance.default.businessSteward||Object.keys(governance.categories).length)){ const n=Object.keys(governance.categories).length; gov=` · ${governance.status}`+(n?`, ${n} per-cat steward${n>1?'s':''}`:''); }
    LAST_JSONL=d.jsonl;
    M.innerHTML=`Generated <b>${s.terms}</b> terms + <b>${s.categories}</b> categories (${s.kept} kept)${gov}
      <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:10px 0 6px">
        <a class="dlbig" href="${url}" download="Suggested-Glossary.json">&#11015; Download glossary JSONL</a>
        <button class="copybtn" onclick="copyText(LAST_JSONL,this)">Copy JSONL</button>
        <span class="hint">(.json file, JSON Lines content)</span>
      </div>
      <div class="nextsteps">&#9888;&#65039; The import is what mints the term ids — nothing binds without it:
        <b>1.</b> Download &rarr; <b>2.</b> PDC: <b>Business Glossary &rarr; Actions &rarr; Import</b> &rarr; <b>3.</b> <b>Resolve Term IDs</b> here &rarr; <b>4.</b> Apply to PDC</div>`
      + renderCheck(d.check);
    GENERATED=true; LAST_REGISTRY=d.registry||null; renderStepper(); syncDupPanel(); renderReady();
  }catch(e){ M.textContent='Generate failed: '+e; } updateKeepUI();
}
