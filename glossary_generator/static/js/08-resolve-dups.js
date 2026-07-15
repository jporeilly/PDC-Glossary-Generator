/* 08-resolve-dups.js — extracted from templates/index.html. Plain scripts, loaded in
   numbered order; they share one global scope, so load order matters. */
/* ---------- keep ---------- */
function setKeep(i,on){ if(!on && isTableTerm(ROWS[i])) return;   // table terms are always kept
  ROWS[i].Keep=on?'Y':'N'; const tr=$('r'+i); if(tr){tr.className=(on?'':'drop')+(isTableTerm(ROWS[i])?' tterm':''); const cb=tr.querySelector('input[type=checkbox]'); if(cb&&!cb.disabled)cb.checked=on;} }
function keepClick(e,i,pos,el){ const on=el.checked;
  if(e.shiftKey&&lastShownPos!=null){ const a=Math.min(lastShownPos,pos),b=Math.max(lastShownPos,pos); for(let p=a;p<=b;p++)setKeep(SHOWN[p],on); } else setKeep(i,on);
  lastShownPos=pos; updateKeepUI(); }
function masterToggle(el){ SHOWN.forEach(i=>setKeep(i,el.checked)); lastShownPos=null; RVW.hm=false; HM_SNAP=null; updateKeepUI(); refreshToggleUI(); }
/* ===== reversible review controls (applied-state + revert + Reset all) ===== */
let SCAN_SNAPSHOT=null, TXN=null, HM_SNAP=null, _ridSeq=1, GRP={}, PANEL_GROUPS=[], _GRIDGRP=[], PRE_ENRICH=null;
let RVW={hm:false,merge:false,disambig:false};
function _deep(a){ return JSON.parse(JSON.stringify(a)); }
function _ensureRids(){ (ROWS||[]).forEach(r=>{ if(r && r._rid==null) r._rid='r'+(_ridSeq++); }); }
function snapshotScan(){ _ensureRids(); (ROWS||[]).forEach(r=>{ if(r&&r._grp==null) r._grp = isTableTerm(r) ? ((r.Term||'').trim()+'\u0000'+(r._rid||'')) : (r.Term||'').trim(); }); GRP={}; SCAN_SNAPSHOT=_deep(ROWS); TXN=null; HM_SNAP=null; RVW={hm:false,merge:false,disambig:false}; PRE_ENRICH=null; if(typeof updateRevertEnrichUI==='function') updateRevertEnrichUI(); refreshToggleUI(); if(typeof renderGroupResolve==='function') renderGroupResolve(); }
function refreshToggleUI(){
  const set=(id,on)=>{ const b=document.getElementById(id); if(b) b.classList.toggle('applied',!!on); };
  set('hmBtn',RVW.hm); set('mergeDupBtn',RVW.merge); set('disambigBtn',RVW.disambig); set('aiAdviseBtn',RVW.merge||RVW.disambig);
  const rb=document.getElementById('resetAllBtn'); if(rb) rb.disabled=!SCAN_SNAPSHOT;
  if(typeof renderGroupResolve==='function') renderGroupResolve();
}
// Keep High+Med conf: toggle. Snapshots the shown rows it flips (by _rid) for exact revert; table terms are exempt.
function toggleHM(){
  if(RVW.hm){
    if(HM_SNAP){ const m=new Map(HM_SNAP.map(v=>[v.rid,v.keep])); (ROWS||[]).forEach(r=>{ if(r&&m.has(r._rid)) r.Keep=m.get(r._rid); }); }
    HM_SNAP=null; RVW.hm=false;
  } else {
    _ensureRids(); HM_SNAP=[];
    SHOWN.forEach(i=>{ const r=ROWS[i]; if(!r) return; HM_SNAP.push({rid:r._rid,keep:r.Keep});
      if(!isTableTerm(r)) r.Keep=(r.Confidence==='High'||r.Confidence==='Medium')?'Y':'N'; });
    RVW.hm=true;
  }
  lastShownPos=null; applyFilter(); updateKeepUI(); refreshToggleUI();
}
function _revertTxn(){
  if(TXN){ ROWS=_deep(TXN); }
  TXN=null; RVW.merge=false; RVW.disambig=false;
  buildCategoryFilter(); applyFilter(); if(typeof renderSummary==='function') renderSummary(computeStats(ROWS));
  updateKeepUI(); if(typeof syncDupPanel==='function') syncDupPanel(); refreshToggleUI();
}
// Merge duplicates / Auto-disambiguate: drive the per-group model across ALL duplicate groups.
function _grpAll(action){ Object.keys(GRP).forEach(n=>{ if(GRP[n].action!==action) groupSet(n,action,true); }); }
function toggleMerge(){
  if(RVW.merge){ _grpAll('separate'); RVW.merge=false; _grpRerender('Reverted merge.'); return; }
  const gs=_allDupGroups(); if(!gs.length){ $('msg').textContent='No duplicate term names to merge.'; return; }
  RVW.disambig=false; gs.forEach(n=>groupSet(n,'merge',true)); RVW.merge=true;
  _grpRerender('Merged '+gs.length+' duplicate group'+(gs.length!==1?'s':'')+'.');
}
function toggleDisambig(){
  if(RVW.disambig){ _grpAll('separate'); RVW.disambig=false; _grpRerender('Reverted disambiguation.'); return; }
  const gs=_allDupGroups(); if(!gs.length){ $('msg').textContent='No duplicate term names to disambiguate.'; return; }
  RVW.merge=false; gs.forEach(n=>groupSet(n,'split',true)); RVW.disambig=true;
  _grpRerender('Disambiguated '+gs.length+' group'+(gs.length!==1?'s':'')+'.');
}
// Reset all: back to the raw scan (undoes filters, keeps, edits, merge/disambiguate).
function resetAll(){
  if(!SCAN_SNAPSHOT) return;
  ROWS=_deep(SCAN_SNAPSHOT); TXN=null; HM_SNAP=null; GRP={}; RVW={hm:false,merge:false,disambig:false}; PRE_ENRICH=null; if(typeof updateRevertEnrichUI==='function') updateRevertEnrichUI();
  buildCategoryFilter(); clearFilters(); if(typeof renderSummary==='function') renderSummary(computeStats(ROWS));
  updateKeepUI(); if(typeof syncDupPanel==='function') syncDupPanel(); refreshToggleUI();
  $('msg').textContent='Reset to the raw scan.';
}
/* ---- per-group resolution: Merge / Disambiguate / Keep separate, each reversible ---- */
function _grpEnsureBase(name){
  // Base = the group's LIVE members at first action (not the raw-scan snapshot):
  // works for renamed-into-collision and harvest-appended rows whose keys the
  // snapshot never saw, and makes revert restore exactly what you had — edits and
  // LLM enrichment included. A cached-but-empty base (from a click that failed
  // before this fix) is recaptured rather than reused.
  const live=(ROWS||[]).filter(r=>r&&r._grp===name);
  if(!GRP[name] || !(GRP[name].base && GRP[name].base.length)){
    GRP[name]={action:(GRP[name]&&GRP[name].action)||'separate', base:_deep(live)};
  }
  return GRP[name];
}
function _mergeMembers(g){
  const base=Object.assign({}, g.slice().sort((a,b)=>{
    const al=(a.LLM_Definition==='Yes'||a.LLM_Enriched==='Yes')?1:0, bl=(b.LLM_Definition==='Yes'||b.LLM_Enriched==='Yes')?1:0;
    if(al!==bl)return bl-al;
    const ad=(a.Definition||'').length, bd=(b.Definition||'').length; if(ad!==bd)return bd-ad;
    return _confRank(b.Confidence)-_confRank(a.Confidence);
  })[0]);
  const tags=new Set(); g.forEach(r=>(r.Suggested_Tags||'').split(';').map(x=>x.trim()).filter(Boolean).forEach(x=>tags.add(x)));
  base.Suggested_Tags=[...tags].join(';');
  base.Sensitivity=g.reduce((m,r)=>_sevRank(r.Sensitivity)>_sevRank(m)?r.Sensitivity:m,g[0].Sensitivity);
  base.Critical_Data_Element=g.some(r=>r.Critical_Data_Element==='Yes')?'Yes':'No';
  base.Confidence=g.reduce((m,r)=>_confRank(r.Confidence)>_confRank(m)?r.Confidence:m,g[0].Confidence);
  base.Suggested_Rating=g.reduce((m,r)=>Math.max(m,parseInt(r.Suggested_Rating||0)||0),0);
  const cols=[], seen=new Set();
  g.forEach(r=>String(r.Source_Column||'').split(';').map(s=>s.trim()).filter(Boolean).forEach(s=>{ if(!seen.has(s)){seen.add(s);cols.push(s);} }));
  base.Source_Column=cols.join('; ');
  base.Source_Ratings=Object.assign({},...g.map(r=>r.Source_Ratings||{}));
  base.Source_Quality_Dims=Object.assign({},...g.map(r=>r.Source_Quality_Dims||{}));
  base.Keep='Y';
  return base;
}
function _splitMembersUnique(g){
  const taken=new Set((ROWS||[]).filter(r=>r&&r._grp!==g[0]._grp).map(r=>(r.Term||'').trim()));
  const t=(g[0].Term||'').trim();
  return g.map(r=>{
    const tbl=_pretty(_tableOf(r.Source_Column))||_pretty(r.Category);
    let cand=`${t} (${tbl||r.Category||'1'})`;
    if(taken.has(cand)) cand=`${t} (${_pretty(r.Category)})`;
    let k=2; while(taken.has(cand)) cand=`${t} (${tbl||r.Category} ${k++})`;
    taken.add(cand); const nr=Object.assign({}, r); nr.Term=cand; return nr;
  });
}
function _regroupByName(){
  // Detection is DYNAMIC: a row's group follows its CURRENT name, so two terms
  // renamed into the same name (e.g. via applied LLM suggestions) become mergeable.
  // Rows inside an ACTIVE resolution keep their frozen key — that's what makes a
  // merge/disambiguate survive later renames and enrich passes. Table terms keep
  // their unique never-groupable key.
  const active=new Set(Object.keys(GRP).filter(n=>GRP[n]&&GRP[n].action&&GRP[n].action!=='separate'));
  (ROWS||[]).forEach(r=>{
    if(!r||isTableTerm(r)) return;
    if(active.has(r._grp)) return;
    r._grp=(r.Term||'').trim();
  });
}
function _allDupGroups(){ _regroupByName(); const c={}; (ROWS||[]).forEach(r=>{ if(r&&truthy(r.Keep)){ const g=r._grp||(r.Term||'').trim(); if(!g) return; c[g]=(c[g]||0)+1; } }); return Object.keys(c).filter(g=>c[g]>1); }
function _panelGroups(){
  const s=new Set(_allDupGroups());
  Object.keys(GRP).forEach(n=>{ if(GRP[n].action!=='separate') s.add(n); });
  return [...s].sort((a,b)=>a.localeCompare(b));
}
// Apply an action to ONE group; rebuild ROWS in place (order preserved). batch=true suppresses re-render.
function groupSet(name, action, batch){
  const g=_grpEnsureBase(name);
  if(!g.base || !g.base.length){ if($('msg')) $('msg').textContent=`Nothing to resolve for “${name}” — the group has no members on the grid.`; return; }
  if(!batch && g.action===action) action='separate';   // click the active choice to revert it
  const base=_deep(g.base);
  const derived = action==='merge' ? [_mergeMembers(base)] : action==='split' ? _splitMembersUnique(base) : base;
  let out=[], inserted=false;
  (ROWS||[]).forEach(r=>{ if(r&&r._grp===name){ if(!inserted){ derived.forEach(d=>out.push(d)); inserted=true; } } else out.push(r); });
  if(!inserted) derived.forEach(d=>out.push(d));
  ROWS=out; g.action=action;
  if(!batch){ RVW.merge=false; RVW.disambig=false; _grpRerender(); }
}
function groupSetIdx(k, action){ const name=PANEL_GROUPS[k]; if(name!=null) groupSet(name, action); }
function _grpRerender(msg){
  _ensureRids(); applyFilter(); if(typeof renderSummary==='function') renderSummary(computeStats(ROWS));
  updateKeepUI(); refreshToggleUI(); if(msg) $('msg').textContent=msg;
}
// The duplicate-resolution control now renders inline in the review grid (see drawRows /
// tr.gclhead), so the old detached panel is retired. Kept as a hide-only shim because a few
// call sites (snapshotScan, _revertTxn) still invoke it; PANEL_GROUPS stays maintained for
// the bulk Merge-all / Auto-disambiguate toggles.
function renderGroupResolve(){
  PANEL_GROUPS=_panelGroups();
  const box=document.getElementById('grpResolve'); if(!box) return;
  box.style.display='none'; box.innerHTML='';
}
/* A table-level term is conceptual (no Source_Column) and its name ends in "Record";
   it carries no column-match Confidence, so the confidence cull must never drop it. (1.5.6) */
function isTableTerm(r){
  if(!r) return false;
  const noCol  = !String(r.Source_Column||'').trim();
  const tagged = /(^|;)\s*table-level\s*(;|$)/i.test(r.Suggested_Tags||'');
  const record = /\bRecord$/.test((r.Term||'').trim());
  return noCol && (tagged || record);
}
function bulkKeep(m){ SHOWN.forEach(i=>{ const r=ROWS[i];
  if(m==='all')setKeep(i,true);
  else if(m==='none')setKeep(i,false);
  else if(m==='invert')setKeep(i,!truthy(r.Keep));
  else if(m==='hm')setKeep(i, isTableTerm(r) ? true : (r.Confidence==='High'||r.Confidence==='Medium')); });
  lastShownPos=null; RVW.hm=false; HM_SNAP=null; updateKeepUI(); refreshToggleUI(); }

/* ---------- duplicate-term resolution (for the steward) ---------- */
function _sevRank(s){ return ({HIGH:3,MEDIUM:2,LOW:1})[String(s||'').toUpperCase()]||0; }
function _confRank(c){ return ({High:3,Medium:2,Low:1})[c]||0; }
function _dupGroups(){ const g={}; ROWS.forEach(r=>{ if(!truthy(r.Keep))return; const t=r.Term||''; (g[t]=g[t]||[]).push(r); });
  return Object.keys(g).filter(t=>g[t].length>1).map(t=>[t,g[t]]); }
function _tableOf(sc){ const f=String(sc||'').split(';')[0].trim().split('.'); return f.length>=2?f[f.length-2]:''; }
function _pretty(s){ return String(s||'').replace(/_+/g,' ').replace(/\b\w/g,c=>c.toUpperCase()).trim(); }
function _afterDupFix(noun,n,extra){
  applyFilter(); renderSummary(computeStats(ROWS)); updateKeepUI();
  $('glossHint').textContent=`${noun} ${n} duplicate name${n!==1?'s':''}${extra||''}.`;
}
// One canonical term per repeated name, linked to ALL its columns (PDC's one-term-many-data-elements model).
function mergeDuplicateTerms(){
  const dups=_dupGroups();
  if(!dups.length){ $('msg').textContent='No duplicate term names to merge.'; return; }
  const dupSet=new Set(dups.map(([t])=>t));
  const merged={};
  dups.forEach(([t,g])=>{
    // representative = best definition (LLM-enriched, then longest, then highest confidence)
    const base=Object.assign({}, g.slice().sort((a,b)=>{
      const al=(a.LLM_Definition==='Yes'||a.LLM_Enriched==='Yes')?1:0, bl=(b.LLM_Definition==='Yes'||b.LLM_Enriched==='Yes')?1:0;
      if(al!==bl)return bl-al;
      const ad=(a.Definition||'').length, bd=(b.Definition||'').length; if(ad!==bd)return bd-ad;
      return _confRank(b.Confidence)-_confRank(a.Confidence);
    })[0]);
    const tags=new Set(); g.forEach(r=>(r.Suggested_Tags||'').split(';').map(x=>x.trim()).filter(Boolean).forEach(x=>tags.add(x)));
    base.Suggested_Tags=[...tags].join(';');
    base.Sensitivity=g.reduce((m,r)=>_sevRank(r.Sensitivity)>_sevRank(m)?r.Sensitivity:m,g[0].Sensitivity);
    base.Critical_Data_Element=g.some(r=>r.Critical_Data_Element==='Yes')?'Yes':'No';
    base.Confidence=g.reduce((m,r)=>_confRank(r.Confidence)>_confRank(m)?r.Confidence:m,g[0].Confidence);
    base.Suggested_Rating=g.reduce((m,r)=>Math.max(m,parseInt(r.Suggested_Rating||0)||0),0);
    const cols=[], seen=new Set();
    g.forEach(r=>String(r.Source_Column||'').split(';').map(s=>s.trim()).filter(Boolean).forEach(s=>{ if(!seen.has(s)){seen.add(s);cols.push(s);} }));
    base.Source_Column=cols.join('; ');
    base.Source_Ratings=Object.assign({},...g.map(r=>r.Source_Ratings||{}));
    base.Source_Quality_Dims=Object.assign({},...g.map(r=>r.Source_Quality_Dims||{}));
    base.Keep='Y';
    merged[t]=base;
  });
  const before=ROWS.length, out=[], used=new Set();
  ROWS.forEach(r=>{ const t=r.Term||'';
    if(truthy(r.Keep)&&dupSet.has(t)){ if(!used.has(t)){used.add(t);out.push(merged[t]);} }
    else out.push(r); });
  ROWS=out;
  _afterDupFix('Merged',dups.length,` into single terms (${before} → ${ROWS.length} rows); each now links to all its columns`);
}
// Keep terms separate but make every name unique by appending its source table.
function disambiguateDuplicateTerms(){
  const dups=_dupGroups();
  if(!dups.length){ $('msg').textContent='No duplicate term names to disambiguate.'; return; }
  const allNames=new Set(ROWS.map(r=>r.Term||'')); let renamed=0;
  dups.forEach(([t,g])=>{
    g.forEach(r=>{
      allNames.delete(r.Term);
      const tbl=_pretty(_tableOf(r.Source_Column))||_pretty(r.Category);
      let cand=`${t} (${tbl||r.Category||'1'})`;
      if(allNames.has(cand)) cand=`${t} (${_pretty(r.Category)})`;
      let k=2; while(allNames.has(cand)) cand=`${t} (${tbl||r.Category} ${k++})`;
      r.Term=cand; allNames.add(cand); renamed++;
    });
  });
  _afterDupFix('Disambiguated',dups.length,` — renamed ${renamed} terms by appending their source table`);
}
/* ---------- duplicate-term review panel (Generate page) ---------- */
function _keptTermCounts(){ const c={}; ROWS.forEach(r=>{ if(truthy(r.Keep)){ const t=(r.Term||'').trim(); c[t]=(c[t]||0)+1; } }); return c; }
function _dupGroupsIdx(){ const g={}; ROWS.forEach((r,i)=>{ if(!truthy(r.Keep))return; const t=(r.Term||'').trim(); (g[t]=g[t]||[]).push(i); });
  return Object.keys(g).filter(t=>g[t].length>1).sort((a,b)=>a.localeCompare(b)).map(t=>[t,g[t]]); }
function syncDupPanel(){
  const wrap=$('dupWrap'); if(!wrap) return;
  const groups=_dupGroupsIdx();
  if(!groups.length){ wrap.style.display='none'; wrap.open=false; return; }
  wrap.style.display='';
  $('dupSummary').innerHTML=`&#9888; Review duplicate term names (${groups.length})`;
  renderDupPanel();
}
function renderDupPanel(){
  const box=$('dupPanel'); if(!box) return;
  const groups=_dupGroupsIdx();
  if(!groups.length){ box.innerHTML='<div class="dupok">&#10003; All term names are now unique across categories — name-based Resolve will link the right column.</div>'; return; }
  let html=`<div class="dupbar">
    <button class="ghost sm" onclick="dupQualifyAll()" title="Append each duplicate's category to its name, e.g. Account Number (Billing & Rates)">&#9889; Qualify all by category</button>
    <button class="ghost sm" onclick="dupMergeAll()" title="Collapse each repeated name into ONE term linked to all its columns (PDC's one-term-many-columns model)">Merge all into one each</button>
    <span class="grow note">Edit a name, or qualify/merge. Names must be unique for Resolve to link the correct column.</span>
  </div>`;
  groups.forEach(([t,idxs])=>{
    const tEsc=esc(t).replace(/'/g,"\\'");
    const ncat=new Set(idxs.map(i=>ROWS[i].Category)).size;
    html+=`<div class="dupgrp"><div class="dupgrp-h"><span class="gname">${esc(t)}</span><span class="hint">${idxs.length} occurrences · ${ncat} categor${ncat>1?'ies':'y'}</span>`
      +`<button class="ghost sm" onclick="dupQualifyGroup('${tEsc}')">Qualify by category</button></div>`;
    idxs.forEach(i=>{ const r=ROWS[i]; const tbl=_pretty(_tableOf(r.Source_Column));
      html+=`<div class="duprow"><span class="dupcat">${esc(r.Category||'\u2014')}</span><span class="duptbl" title="source table">${esc(tbl||'')}</span><input class="dupinp" type="text" value="${esc(r.Term||'')}" oninput="dupRename(${i},this.value)"/></div>`;
    });
    html+='</div>';
  });
  box.innerHTML=html; _markClashes();
}
function _markClashes(){
  const counts=_keptTermCounts();
  document.querySelectorAll('#dupPanel .dupinp').forEach(inp=>{
    const t=(inp.value||'').trim();
    inp.classList.toggle('clash', t==='' || (counts[t]||0)>1);
  });
}
function dupRename(i,v){ if(ROWS[i]){ ROWS[i].Term=v; _markClashes(); } }
function _qualifyName(t,r,taken){
  let cand=`${t} (${_pretty(r.Category)||'?'})`;
  if(taken.has(cand)){ const tbl=_pretty(_tableOf(r.Source_Column)); if(tbl) cand=`${t} (${_pretty(r.Category)} \u00b7 ${tbl})`; }
  let k=2; while(taken.has(cand)) cand=`${t} (${_pretty(r.Category)} ${k++})`;
  return cand;
}
function dupQualifyGroup(t){
  const taken=new Set(ROWS.map(r=>(r.Term||'').trim()));
  ROWS.forEach(r=>{ if(truthy(r.Keep)&&(r.Term||'').trim()===t){ taken.delete(r.Term); const c=_qualifyName(t,r,taken); r.Term=c; taken.add(c); } });
  afterDupPanelAction();
}
function dupQualifyAll(){
  _dupGroupsIdx().forEach(([t])=>{
    const taken=new Set(ROWS.map(r=>(r.Term||'').trim()));
    ROWS.forEach(r=>{ if(truthy(r.Keep)&&(r.Term||'').trim()===t){ taken.delete(r.Term); const c=_qualifyName(t,r,taken); r.Term=c; taken.add(c); } });
  });
  afterDupPanelAction();
}
function dupMergeAll(){ mergeDuplicateTerms(); afterDupPanelAction(); }
function afterDupPanelAction(){
  if(typeof applyFilter==='function') applyFilter();
  if(typeof updateKeepUI==='function') updateKeepUI();
  syncDupPanel();
  if(GENERATED) generate('govGenMsg');   // refresh the build check against the fixed names
}
function updateKeepUI(){
  const total=ROWS.length, kept=ROWS.reduce((n,r)=>n+(truthy(r.Keep)?1:0),0), sk=SHOWN.reduce((n,i)=>n+(truthy(ROWS[i].Keep)?1:0),0);
  $('keepcount').innerHTML=`<b>${kept}</b> of <b>${total}</b> kept`+(SHOWN.length!==total?` · ${SHOWN.length} shown`:'');
  const mk=$('masterkeep'); if(!SHOWN.length){mk.checked=false;mk.indeterminate=false;} else if(sk===0){mk.checked=false;mk.indeterminate=false;} else if(sk===SHOWN.length){mk.checked=true;mk.indeterminate=false;} else {mk.checked=false;mk.indeterminate=true;}
  const gg=$('govGenBtn'); if(gg){ gg.disabled=kept===0; gg.innerHTML=(kept?`Generate JSONL (${kept})`:'Generate JSONL')+' &rarr;'; gg.title=kept?'Export the kept terms with the governance set above':'Keep at least one term on the Glossary page first'; }
  const tg=$('toGovernBtn'); if(tg){ tg.disabled=kept===0; tg.title=kept?'Set stewardship, then generate on the Govern page':'Keep at least one term first (tick a Keep box, or use “Keep High+Med conf”)'; }
  renderStepper();
}

function goToApply(){
  showPage('apply');
  exportDataElements();
}
async function exportDataElements(){
  const m=$('deMsg')||$('msg');
  m.textContent='Building Data Element links\u2026';
  const rating=globalRatingInt();  // "Auto" -> 0 here, so each column keeps its own DQ-derived scan rating
  const wt=id=>{const v=$(id)?parseFloat($(id).value):NaN; return isNaN(v)?undefined:v;};
  const quality_weights={completeness:wt('dq_wc'),uniqueness:wt('dq_wu'),validity:wt('dq_wv')};
  const quality=$('dq_on')?$('dq_on').checked:true;
  const pol=$('mapPolicy')?$('mapPolicy').value:'default';
  const map_policy = pol==='strict' ? {min_confidence:'high'} : pol==='all' ? {mode:'all'} : null;
  const renderSkip=(d)=>{const sk=$('deSkip'); if(!sk) return;
    const held=d.skipped_terms||0;
    if(held && d.breakdown && d.breakdown.skipped && d.breakdown.skipped.length){
      const items=d.breakdown.skipped.slice(0,300).map(x=>`<li><b>${x.term}</b> <span class="hint">(${x.category||'\u2014'})</span> &mdash; ${x.reason}</li>`).join('');
      sk.style.display='block';
      sk.innerHTML=`<b>${held} term(s) held back</b> &mdash; not linked to a data element. Set <b>Map</b> = Y on the Glossary page to force any of these:<ul style="margin:6px 0 0 18px">${items}</ul>`;
    } else { sk.style.display='none'; sk.innerHTML=''; }};
  try{
    const d=await (await fetch('/api/data-elements',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rows:ROWS,glossary_name:$('gname').value,lineage_verified:true,rating,quality,quality_weights,map_policy})})).json();
    if(!d.count){
      const held=d.skipped_terms||0;
      m.innerHTML = held
        ? `No links \u2014 all <b>${held}</b> kept term(s) were held back by the mapping policy. Loosen the policy, or set <b>Map</b> = Y on the rows you want linked.`
        : 'No linkable columns in the kept terms \u2014 keep some terms on the Glossary page first.';
      renderSkip(d); return;
    }
    LAST_DE_JSON=d.json;
    const csvUrl=URL.createObjectURL(new Blob([d.csv],{type:'text/csv'}));
    const jsonUrl=URL.createObjectURL(new Blob([JSON.stringify(d.json,null,2)],{type:'application/json'}));
    const dq=(quality&&d.quality_scored)?` \u00b7 <b>${d.quality_scored}</b> with DQ score`:'';
    const held=(d.skipped_terms)?` \u00b7 <b>${d.skipped_terms}</b> held back`:'';
    m.innerHTML=`<b>${d.mapped_terms!=null?d.mapped_terms:d.terms}</b> terms mapped${held} \u00b7 <b>${d.count}</b> links \u00b7 <b>${d.elements}</b> data elements across <b>${d.tables}</b> tables${dq} \u2014 `+
      `<a class="dl" href="${csvUrl}" download="Data-Element-Links.csv">CSV (bulk assign)</a> \u00b7 `+
      `<a class="dl" href="${jsonUrl}" download="Data-Elements-API.json">JSON (Trust-ready, API)</a>`;
    renderSkip(d);
  }catch(e){ m.textContent='Data Elements failed: '+e; }
}

/* ---- AI match for outstanding term names (renamed after import) ---- */
let RESOLVE_UNRESOLVED=[], FUZZY={};
async function resolveFuzzy(){
  const btn=$('fuzzyBtn'); if(!RESOLVE_UNRESOLVED.length) return;
  if(btn){ btn.disabled=true; btn.textContent='Matching…'; }
  try{
    const defs={}; (ROWS||[]).forEach(r=>{ if(r&&r.Term&&r.Definition&&!defs[r.Term]) defs[r.Term]=r.Definition; });
    const body={names:RESOLVE_UNRESOLVED, definitions:defs,
                base_url:$('pdc_base').value.trim(), version:$('pdc_ver').value,
                realm:(($('pdc_realm')&&$('pdc_realm').value.trim())||'pdc'),
                username:$('pdc_user').value, password:$('pdc_pass').value,
                token:$('pdc_token').value.trim(), verify_tls:$('pdc_verify').checked,
                glossary_name:$('gname').value, model:currentModel()||null, compute:COMPUTE};
    const d=await (await fetch('/api/resolve-fuzzy',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).json();
    if(d.error){ if($('fuzzyList')) $('fuzzyList').innerHTML=`<div class="msg">${esc(d.error)}</div>`; return; }
    FUZZY=d.matches||{};
    renderFuzzy(d.used_llm);
  }catch(e){ if($('fuzzyList')) $('fuzzyList').innerHTML=`<div class="msg">AI match failed: ${esc(String(e.message||e))}</div>`; }
  finally{ if(btn){ btn.disabled=false; btn.textContent='AI match in PDC'; } }
}
function renderFuzzy(usedLlm){
  const el=$('fuzzyList'); if(!el) return;
  const names=Object.keys(FUZZY);
  const matched=names.filter(n=>FUZZY[n]&&FUZZY[n].match);
  const rows=names.map(n=>{
    const f=FUZZY[n]||{};
    if(!f.match) return `<div class="prow"><b>${esc(n)}</b> — <span style="color:var(--mute)">${esc(f.reason||'no match')}</span></div>`;
    const src=f.source==='ai'?'<span class="gband" style="background:#EDE7F6;color:#4527A0">AI</span>':`<span class="gband" style="background:#DDF0E4;color:#1B6B45">${esc(f.reason||'match')}</span>`;
    return `<div class="prow"><b>${esc(n)}</b> &rarr; <b>${esc(f.match)}</b> ${src} ${f.source==='ai'?`<span class="hint">${esc(f.reason||'')}</span>`:''} <button class="ghost sm" style="padding:1px 8px;border-color:#2EC4B6;color:#0A3D52;font-weight:600" onclick="bindFuzzy('${esc(n).replace(/'/g,"&#39;")}')">Bind id</button></div>`;
  }).join('');
  const all=matched.length>1?`<button class="ghost sm" onclick="bindFuzzyAll()" style="margin:4px 0;border-color:#2EC4B6;color:#0A3D52;font-weight:600">Bind all ${matched.length} matches</button>`:'';
  el.innerHTML=`<div class="probe" style="margin-top:6px">${rows}${all}<div class="hint" style="margin-top:4px">Binding stamps the PDC term's id + glossaryId into these links (your local name stays). ${usedLlm?'':'Ollama offline — similarity matches only. '}Then re-download the POST-ready JSON or go straight to Apply.</div></div>`;
}
function bindFuzzy(name){
  const f=FUZZY[name]; if(!f||!f.match||!f.id||!LAST_DE_JSON) return 0;
  let n=0;
  LAST_DE_JSON.forEach(el=>{ ((el.attributes||{}).businessTerms||[]).forEach(bt=>{
    if((bt.name||'')===name){ bt.id=f.id; if(f.glossaryId) bt.glossaryId=f.glossaryId; n++; } }); });
  delete FUZZY[name];
  RESOLVE_UNRESOLVED=RESOLVE_UNRESOLVED.filter(x=>x!==name);
  renderFuzzy(true);
  if($('resolveMsg')&&n) $('resolveMsg').insertAdjacentHTML('beforeend',
    `<div class="msg" style="color:#1C7C54">Bound “${esc(name)}” &rarr; “${esc(f.match)}” on ${n} link(s).</div>`);
  return n;
}
function bindFuzzyAll(){
  let total=0;
  Object.keys(FUZZY).forEach(n=>{ if(FUZZY[n]&&FUZZY[n].match) total+=bindFuzzy(n); });
  if($('resolveMsg')) $('resolveMsg').insertAdjacentHTML('beforeend',
    `<div class="msg" style="color:#1C7C54">All matches bound (${total} link(s)) — the links are ready to Apply.</div>`);
}
async function resolveTermIds(){
  if(!LAST_DE_JSON){ $('resolveMsg').textContent='Export the Data Elements JSON first.'; return; }
  const base=$('pdc_base').value.trim();
  if(!base){ $('resolveMsg').textContent='Enter your PDC base URL.'; return; }
  $('resolveBtn').disabled=true; $('resolveMsg').textContent='Authenticating and resolving terms…';
  try{
    const body={base_url:base, version:$('pdc_ver').value, realm:(($('pdc_realm')&&$('pdc_realm').value.trim())||'pdc'), username:$('pdc_user').value,
                password:$('pdc_pass').value, token:$('pdc_token').value.trim(),
                verify_tls:$('pdc_verify').checked, glossary_name:$('gname').value, json:LAST_DE_JSON};
    const d=await (await fetch('/api/resolve-terms',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).json();
    if(d.error){ $('resolveMsg').textContent='Resolve failed: '+d.error; $('resolveBtn').disabled=false; return; }
    LAST_DE_JSON=d.json;
    const url=URL.createObjectURL(new Blob([JSON.stringify(d.json,null,2)],{type:'application/json'}));
    const allLinked=d.linked===d.links;
    let m=`${allLinked?'<b style="color:#1C7C54">\u2713 All '+d.linked+' term links are bound (id + glossaryId) — ready to Apply.</b>':'Fully linked <b>'+d.linked+'</b> of '+d.links+' term links (id + glossaryId).'} \u00b7 <b>${d.matched_with_glossary}</b> of ${d.terms} terms confirmed by PDC by name — <a class="dl" href="${url}" download="Data-Elements-API-resolved.json">download POST-ready JSON</a>`;
    if(d.linked && d.glossary_id && d.matched_with_glossary < d.matched){
      m+=`<div class="msg" style="color:#1C7C54;margin-top:4px">PDC's API doesn't return a term's glossaryId, so it was filled deterministically from the glossary you imported (<code>${esc(d.glossary_id)}</code>). These links are ready to Apply.</div>`;
    }
    if(d.id_only&&d.id_only.length){
      const chips=d.id_only.map(n=>`<span>${esc(n)}</span>`).join('');
      m+=`<details class="nfwrap" open><summary style="color:#C25E00">\u26a0 ${d.id_only.length} term(s) matched an id but PDC returned NO glossaryId — these will NOT link to a glossary (Apply treats them as unresolved)</summary>`
       + `<div class="nflist">${chips}</div></details>`;
    }
    if(d.unresolved&&d.unresolved.length){
      RESOLVE_UNRESOLVED=d.unresolved.slice();
      const chips=d.unresolved.map(n=>`<span>${esc(n)}</span>`).join('');
      m+=`<details class="nfwrap" open><summary>${d.unresolved.length} term(s) not found in PDC by name — renamed locally after import? <button class="ghost sm" style="margin-left:8px" onclick="resolveFuzzy()" id="fuzzyBtn" title="Match each outstanding name against the terms that actually exist in PDC — name similarity first, then the local AI judging with the term's definition. Proposals only; you bind each match.">AI match in PDC</button></summary>`
       + `<div class="nflist">${chips}</div><div id="fuzzyList"></div></details>`;
    } else { RESOLVE_UNRESOLVED=[]; }
    const unconf=(d.unconfirmed||[]).filter(n=>!(d.unresolved||[]).includes(n));
    if(unconf.length){
      RESOLVE_UNRESOLVED=RESOLVE_UNRESOLVED.concat(unconf);
      const chips=unconf.map(n=>`<span>${esc(n)}</span>`).join('');
      m+=`<details class="nfwrap" open><summary style="color:#C25E00">\u26a0 ${unconf.length} term(s) could not be CONFIRMED in PDC by name — their links fall back to the deterministic import ids, which only exist if the term kept its name since import (renamed terms would Apply a dead id) <button class="ghost sm" style="margin-left:8px" onclick="resolveFuzzy()" id="fuzzyBtn" title="Match each unconfirmed name against the terms that actually exist in PDC — name similarity first, then the local AI judging with the term's definition. Binding replaces the deterministic id with PDC's real one.">AI match in PDC</button></summary>`
       + `<div class="nflist">${chips}</div><div id="fuzzyList"></div></details>`;
    }
    if(d.probe&&d.probe.length){
      const anyHit=d.probe.some(p=>(p.search_hits>0)||(p.filter_hits>0));
      const anyGid=d.probe.some(p=>p.search_has_glossaryId);
      const rows=d.probe.map(p=>{
        const st=(p.search_types&&p.search_types.length)?` [${esc(p.search_types.join(', '))}]`:'';
        const ft=(p.filter_types&&p.filter_types.length)?` [${esc(p.filter_types.join(', '))}]`:'';
        return `<div class="prow"><b>${esc(p.name)}</b> · search ${p.search_hits} hit(s)${st}`
          + `${p.search_has_glossaryId?' · glossaryId✓':' · glossaryId✗'}${p.bt_match?' · businessTerms✓':''}`
          + ` · filter ${p.filter_hits} hit(s)${ft}${p.search_error?(' · search error: '+esc(p.search_error)):''}</div>`;
      }).join('');
      const verdict = !anyHit
        ? 'PDC returned nothing for these names — either the glossary is not imported (In PDC: <b>Glossary → Actions → Import</b> → drop the JSONL → Submit, then re-resolve), or these terms were RENAMED locally after import — use <b>AI match in PDC</b> above to bind them without re-importing.'
        : (anyGid
          ? 'PDC has these terms WITH a glossaryId, so they should link. If Apply still skips them, send me this probe — the field the glossaryId lands in may differ.'
          : 'PDC found these terms but exposes NO glossaryId on them (only an id). The term may be imported as a stand-alone/Unassigned term (no parent glossary). Re-import the JSONL so each term sits under the business glossary, or send me this probe and a sample term\u2019s API JSON so the matcher can read its glossary from another field.');
      m+=`<details class="nfwrap"><summary>PDC probe — confirmation diagnostics for the first ${d.probe.length} unconfirmed name(s)</summary><div class="probe">${rows}<div class="verdict">${verdict}</div></div></details>`;
    }
    $('resolveMsg').innerHTML=m;
  }catch(e){ $('resolveMsg').textContent='Resolve failed: '+e; }
  $('resolveBtn').disabled=false;
}
