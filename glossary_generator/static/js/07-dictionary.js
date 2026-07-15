/* 07-dictionary.js — extracted from templates/index.html. Plain scripts, loaded in
   numbered order; they share one global scope, so load order matters. */
/* ---- Tag dictionary (governed vocabulary) ---- */
let TAGDICT=null;
let STEWARD_ACTOR='';
try{ STEWARD_ACTOR=localStorage.getItem('gg_steward')||''; }catch(e){}
function setActor(v){ STEWARD_ACTOR=(v||'').trim(); try{ localStorage.setItem('gg_steward',STEWARD_ACTOR); }catch(e){} }
async function renderAudit(){
  const tb=$('auditRows'); if(!tb) return;
  try{
    const d=await (await fetch('/api/audit?n=100')).json();
    const rows=(d.entries||[]).map(e=>{
      const det=Object.keys(e).filter(k=>!['ts','actor','action'].includes(k)).map(k=>`${k}: ${Array.isArray(e[k])?e[k].join(', '):e[k]}`).join(' · ');
      return `<tr><td style="padding:4px 8px;color:var(--mute);white-space:nowrap">${esc((e.ts||'').replace('T',' ').replace(/(\+00:00|Z)$/,''))}</td>
        <td style="padding:4px 8px;font-weight:600">${esc(e.actor||'')}</td>
        <td style="padding:4px 8px"><code>${esc(e.action||'')}</code></td>
        <td style="padding:4px 8px;color:var(--mute);word-break:break-word">${esc(det)}</td></tr>`;}).join('');
    tb.innerHTML=rows||'<tr><td colspan="4" class="msg" style="padding:8px">No governance actions recorded yet.</td></tr>';
    if($('auditMsg')) $('auditMsg').textContent=(d.summary&&d.summary.count)?`${d.summary.count} entr${d.summary.count===1?'y':'ies'} total.`:'';
  }catch(e){ tb.innerHTML='<tr><td colspan="4" class="msg" style="padding:8px">Failed to load audit: '+esc(String(e))+'</td></tr>'; }
}
async function tdLoad(){
  const msg=$('tdMsg'); if(msg) msg.textContent='';
  if($('td_actor') && !$('td_actor').value) $('td_actor').value=STEWARD_ACTOR;
  try{ TAGDICT=await (await fetch('/api/tagdict')).json(); tdRender(); }
  catch(e){ if($('tdRows')) $('tdRows').innerHTML='<tr><td colspan="4" class="msg" style="padding:8px">Failed to load: '+esc(String(e))+'</td></tr>'; }
}
function tdRender(){
  if(!TAGDICT) return;
  if(typeof renderStepper==='function') renderStepper();   // pending queue drives the Dictionary step
  const pt=TAGDICT.pending_tags||0, pterm=TAGDICT.pending_terms||0;
  $('tdSummary').textContent=`${TAGDICT.domain||'—'} · ${TAGDICT.term_count||0} terms (${TAGDICT.generic_terms||0} generic, ${TAGDICT.governed_terms||0} governed) · ${TAGDICT.tag_count||0} tags (${TAGDICT.generic_tags||0} generic, ${TAGDICT.governed_tags||0} governed) · ${TAGDICT.rule_count||0} rules`+((TAGDICT.sources&&TAGDICT.sources.length)?` · grown from: ${TAGDICT.sources.join(', ')}`:' · not yet grown from a scan');
  tdRenderPending();
  const badge=st=>st==='generic'?'<span style="font-size:9.5px;font-weight:700;padding:1px 6px;border-radius:8px;background:#e6f1f6;color:#065A82">generic</span>':(st==='pending'?'<span style="font-size:9.5px;font-weight:700;padding:1px 6px;border-radius:8px;background:#fdecc8;color:#7a4a00">pending</span>':'<span style="font-size:9.5px;font-weight:700;padding:1px 6px;border-radius:8px;background:#DDF0E4;color:#1B6B45">approved</span>');
  const trows=(TAGDICT.terms||[]).map(t=>`<tr>
    <td style="padding:4px 8px;font-weight:600;word-break:break-word">${esc(t.term)}</td>
    <td style="padding:4px 8px">${badge(t.status)}</td>
    <td style="padding:4px 8px"><span class="sev ${esc(t.sensitivity||'LOW')}" style="font-size:10px">${esc(t.sensitivity||'LOW')}</span></td>
    <td style="padding:4px 8px;color:var(--mute);word-break:break-word">${esc((t.aliases||[]).join('; '))}</td>
    <td style="padding:4px 8px;color:var(--mute);word-break:break-word">${esc((t.tags||[]).join('; '))}</td>
    <td style="padding:4px 8px">${t.count||0}</td></tr>`).join('');
  $('tdTermRows').innerHTML=trows||'<tr><td colspan="6" class="msg" style="padding:8px">No terms yet.</td></tr>';
  const rows=(TAGDICT.tags||[]).map(t=>`<tr>
    <td style="padding:4px 8px;font-weight:600;word-break:break-word">${esc(t.tag)} ${badge(t.status)}</td>
    <td style="padding:4px 8px">${t.sensitivity_floor?`<span class="sev ${esc(t.sensitivity_floor)}" style="font-size:10px">${esc(t.sensitivity_floor)}</span>`:'<span style="color:var(--mute)">—</span>'}</td>
    <td style="padding:4px 8px">${t.count||0}</td>
    <td style="padding:4px 8px;color:var(--mute);word-break:break-word">${esc((t.examples||[]).join(', '))}</td></tr>`).join('');
  $('tdRows').innerHTML=rows||'<tr><td colspan="4" class="msg" style="padding:8px">No tags yet.</td></tr>';
  if($('tdRuleRows')){
    const rrows=(TAGDICT.rules||[]).map(r=>`<tr>
      <td style="padding:4px 8px;word-break:break-all"><code>${esc(r.pattern||'')}</code></td>
      <td style="padding:4px 8px;word-break:break-word">${esc((r.tags||[]).join('; '))}</td>
      <td style="padding:4px 8px">${badge(r.layer==='generic'?'generic':'approved')}</td></tr>`).join('');
    $('tdRuleRows').innerHTML=rrows||'<tr><td colspan="3" class="msg" style="padding:8px">No rules yet — add one below, or seed them from the domain pack.</td></tr>';
  }
  tdRenderFacet();
}
function _lev(a,b){ const m=a.length,n=b.length; if(!m)return n; if(!n)return m; const d=Array.from({length:m+1},(_,i)=>[i,...Array(n).fill(0)]); for(let j=0;j<=n;j++)d[0][j]=j;
  for(let i=1;i<=m;i++)for(let j=1;j<=n;j++)d[i][j]=Math.min(d[i-1][j]+1,d[i][j-1]+1,d[i-1][j-1]+(a[i-1]===b[j-1]?0:1)); return d[m][n]; }
function tdRenderFacet(){
  const list=$('facetList'); if(!list) return;
  const gov=(TAGDICT.tags||[]).filter(t=>t.status==='generic'||t.status==='approved');
  if(!gov.length){ $('facetFlags').innerHTML=''; list.innerHTML='<p class="msg">No governed tags yet.</p>'; $('facetPending').textContent=''; return; }
  const sorted=[...gov].sort((a,b)=>(b.count||0)-(a.count||0));
  const max=Math.max(1,...gov.map(t=>t.count||0));
  list.innerHTML=sorted.map(t=>{ const c=t.count||0, w=Math.round(c/max*100), empty=c===0;
    return `<div style="display:flex;align-items:center;gap:8px;margin:3px 0">
      <div style="flex:0 0 150px;font-size:12.5px;font-weight:600;color:${empty?'var(--mute)':'var(--ink,#1a2730)'};word-break:break-word" title="${esc((t.examples||[]).join(', '))}">${esc(t.tag)}${t.sensitivity_floor?` <span class="sev ${esc(t.sensitivity_floor)}" style="font-size:9px">${esc(t.sensitivity_floor)}</span>`:''}</div>
      <div style="flex:1;height:14px;background:#eef3f5;border-radius:7px;overflow:hidden"><div style="height:100%;width:${empty?2:w}%;background:${empty?'#e0a800':'var(--teal)'};border-radius:7px"></div></div>
      <div style="flex:0 0 74px;font-size:12px;color:var(--mute);text-align:right">${empty?'empty':c+(c===1?' term':' terms')}</div></div>`;
  }).join('');
  // flags: empty governed tags + fragmenting near-duplicates
  const empties=sorted.filter(t=>(t.count||0)===0).map(t=>t.tag);
  const norm=s=>s.toLowerCase().replace(/[^a-z0-9]/g,'');
  const groups={}; gov.forEach(t=>{ const k=norm(t.tag); (groups[k]=groups[k]||[]).push(t.tag); });
  const fragExact=Object.values(groups).filter(g=>g.length>1);
  const names=gov.map(t=>t.tag), fragNear=[], seenPair=new Set();
  for(let i=0;i<names.length;i++)for(let j=i+1;j<names.length;j++){ const a=norm(names[i]),b=norm(names[j]);
    if(a===b) continue; if(Math.abs(a.length-b.length)<=1 && Math.min(a.length,b.length)>=4 && _lev(a,b)===1){ const key=[names[i],names[j]].sort().join('¦'); if(!seenPair.has(key)){seenPair.add(key); fragNear.push([names[i],names[j]]);} } }
  let flags='';
  if(fragExact.length||fragNear.length){
    const parts=[...fragExact.map(g=>g.join(' / ')), ...fragNear.map(p=>p.join(' / '))];
    flags+=`<div style="margin:0 0 8px;padding:8px 10px;border-radius:8px;background:#fff6e6;border:1px solid #f0d9a8;color:#7a4a00;font-size:12.5px"><b>May fragment the facet</b> — these split into separate buckets a single filter won't merge: ${parts.map(p=>`<code>${esc(p)}</code>`).join(', ')}. Consolidate to one tag (add the other as a rule that emits it).</div>`;
  }
  if(empties.length){
    // split by layer: only COMPANY tags can be retired (the generic baseline is protected)
    const layerOf={}; (TAGDICT.tags||[]).forEach(t=>{ layerOf[t.tag]=t.layer; });
    const companyEmpties=empties.filter(t=>layerOf[t]!=='generic');
    const retire=companyEmpties.length?` <button class="ghost sm" style="padding:1px 8px" onclick="tdRetireEmpty(${JSON.stringify(companyEmpties).replace(/"/g,'&quot;')})" title="Remove the ${companyEmpties.length} empty COMPANY-layer tag(s) from the vocabulary. The generic baseline can't be removed. A tag a rule still emits will be re-added with a warning on the next save.">Retire ${companyEmpties.length} empty company tag${companyEmpties.length>1?'s':''}</button>`:'';
    flags+=`<div style="margin:0 0 8px;padding:8px 10px;border-radius:8px;background:#f3f6f8;border:1px solid var(--line);color:var(--mute);font-size:12.5px"><b>${empties.length} governed tag${empties.length>1?'s':''} with no reviewed usage</b> — empty facet bucket${empties.length>1?'s':''}: ${empties.slice(0,12).map(t=>`<code>${esc(t)}</code>`).join(', ')}${empties.length>12?' …':''}.<br>“Usage” here is <b>reviewed usage inside this app</b> (accreted on every scan), not live PDC data — counts reset with a dictionary reseed and rebuild on the next scan+review. All tags empty usually just means “freshly reseeded”. Retire only what stays empty after a full scan of every source.${retire}</div>`;
  }
  if(!flags) flags=`<div style="margin:0 0 4px;color:#1B6B45;font-size:12.5px;font-weight:600">✓ No empty or fragmenting governed tags — the facet looks clean.</div>`;
  $('facetFlags').innerHTML=flags;
  const pt=(TAGDICT.pending_tags||0);
  $('facetPending').innerHTML = pt ? `<b>${pt}</b> pending tag${pt>1?'s':''} ${pt>1?'are':'is'} not in the facet yet — approve above to include ${pt>1?'them':'it'}.` : '';
}
function tdRenderPending(){
  const wrap=$('tdPending'); if(!wrap) return;
  const pterms=(TAGDICT.terms||[]).filter(t=>t.status==='pending').map(t=>t.term);
  const ptags=(TAGDICT.tags||[]).filter(t=>t.status==='pending').map(t=>t.tag);
  if(!pterms.length && !ptags.length){ wrap.style.display='none'; return; }
  wrap.style.display='';
  const chip=(kind,nm)=>`<span style="display:inline-flex;align-items:center;gap:5px;border:1px solid var(--line);border-radius:14px;padding:2px 4px 2px 10px;margin:2px 4px 2px 0;background:#fff">${esc(nm)}<button class="ghost sm" style="padding:1px 7px" title="Approve — starts governing" onclick="tdReview('${kind}','${esc(nm).replace(/'/g,"\\'")}','approve')">✓</button><button class="ghost sm" style="padding:1px 7px" title="Reject — discard" onclick="tdReview('${kind}','${esc(nm).replace(/'/g,"\\'")}','reject')">✕</button></span>`;
  // pending TERMS render as rows with the context a steward decides on:
  // where the scan saw it, the category it carried, sensitivity/conf, tags, definition
  const sensCls={HIGH:'sens-hi',MEDIUM:'sens-md',LOW:'sens-lo'};
  const trow=t=>{
    const meta=[t.category?`category <b>${esc(t.category)}</b>`:'',
                t.sensitivity?`sensitivity <b class="${sensCls[t.sensitivity]||''}">${esc(t.sensitivity)}</b>`:'',
                t.confidence?`conf <b>${esc(t.confidence)}</b>`:'',
                (t.tags&&t.tags.length)?`tags ${t.tags.map(esc).join('; ')}`:'',
                (t.sources&&t.sources.length)?`seen in <code style="font-size:10.5px">${t.sources.map(esc).join('; ')}</code>`:''
               ].filter(Boolean).join(' · ');
    const adv=TD_ADVICE[t.term];
    const advLbl=adv?({approve:'Approve',reject:'Reject',alias:'Alias of '+esc(adv.target||'')})[adv.action]:'';
    const advHtml=adv?`<div style="font-size:11px;margin-top:2px;color:#0A3D52"><span class="gband" style="background:#EDE7F6;color:#4527A0;margin-left:0">AI</span> Recommended: <b>${advLbl}</b> — ${esc(adv.reason||'')}</div>`:'';
    const aliasBtn=(adv&&adv.action==='alias'&&adv.target)?`<button class="ghost sm" style="padding:1px 8px;border-color:#2EC4B6;color:#0A3D52;font-weight:600" title="Fold into '${esc(adv.target)}' as an alias" onclick="tdAlias('${esc(t.term).replace(/'/g,"\\'")}','${esc(adv.target).replace(/'/g,"\\'")}')">→ alias</button>`:'';
    return `<div style="display:flex;align-items:flex-start;gap:8px;padding:5px 2px;border-top:1px solid #efe3c8">
      <div style="flex:1;min-width:0"><b style="font-size:12.5px">${esc(t.term)}</b>
        ${meta?`<span class="hint" style="margin-left:8px">${meta}</span>`:''}
        ${t.definition?`<div class="hint" style="margin-top:1px">${esc(t.definition)}</div>`:''}
        ${advHtml}
      </div>
      ${aliasBtn}
      <button class="ghost sm" style="padding:1px 8px" title="Approve — starts governing" onclick="tdReview('term','${esc(t.term).replace(/'/g,"\\'")}','approve')">✓</button>
      <button class="ghost sm" style="padding:1px 8px" title="Reject — discard" onclick="tdReview('term','${esc(t.term).replace(/'/g,"\\'")}','reject')">✕</button>
    </div>`;
  };
  let html='';
  const ptermObjs=(TAGDICT.terms||[]).filter(t=>t.status==='pending');
  if(pterms.length) html+=`<div><b>Terms (${pterms.length})</b> <button class="ghost sm" onclick="tdReviewAll('term','approve')">Approve all</button> <button class="ghost sm" onclick="tdAiReview()" id="tdAiBtn" ${TD_REVIEWING?'disabled':''} title="Advise per candidate: a deterministic near-duplicate check against the governed vocabulary, then the local AI judges the rest from the captured context (category, definition, sources). Advice only — you still click.">${TD_REVIEWING?'Reviewing…':'AI review'}</button> <span class="hint">approve only what belongs in the company vocabulary — reject scan noise</span><div style="margin-top:4px">${ptermObjs.map(trow).join('')}</div></div>`;
  if(ptags.length) html+=`<div><b>Tags (${ptags.length})</b> <button class="ghost sm" onclick="tdReviewAll('tag','approve')">Approve all</button><div style="margin-top:4px">${ptags.map(n=>chip('tag',n)).join('')}</div></div>`;
  $('tdPendList').innerHTML=html;
}
let TD_ADVICE={}, TD_REVIEWING=false, TD_CANCEL=false;
function tdProgShow(done,total){
  const p=$('tdProg'); if(!p) return;
  p.style.display=total?'flex':'none';
  if(total){
    const pct=Math.round(100*done/total);
    $('tdpFill').style.width=pct+'%';
    $('tdpLbl').textContent=TD_CANCEL?'Finishing current batch…':`AI reviewing pending terms — ${done}/${total} (${pct}%)`;
  }
}
async function tdAiReview(){
  if(TD_REVIEWING) return;
  const names=(TAGDICT.terms||[]).filter(t=>t.status==='pending'&&t.layer!=='generic').map(t=>t.term);
  if(!names.length){ $('tdMsg').textContent='Nothing pending to review.'; return; }
  TD_REVIEWING=true; TD_CANCEL=false; TD_ADVICE={};
  const c=$('tdpCancel'); if(c) c.disabled=false;
  tdRenderPending(); tdProgShow(0,names.length);
  const BATCH=10; let done=0, usedLlm=false;
  try{
    for(let i=0;i<names.length && !TD_CANCEL;i+=BATCH){
      const d=await (await fetch('/api/tagdict/ai-review',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({model:currentModel()||null,compute:COMPUTE,names:names.slice(i,i+BATCH)})})).json();
      if(d.error) throw new Error(d.error);
      Object.assign(TD_ADVICE,d.advice||{});
      usedLlm=usedLlm||!!d.used_llm;
      done=Math.min(i+BATCH,names.length);
      tdProgShow(done,names.length);
      tdRenderPending();  // recommendations appear batch by batch
    }
    const n=Object.keys(TD_ADVICE).length;
    $('tdMsg').textContent=n?`AI reviewed ${done} candidate(s)${TD_CANCEL?' (cancelled early)':''} — ${n} recommendation(s)${usedLlm?'':' (Ollama offline — duplicate check only)'}.`:`Reviewed ${done} candidate(s) — no recommendations${usedLlm?'':' (Ollama offline — duplicate check only)'}.`;
  }catch(e){ $('tdMsg').textContent='AI review failed: '+(e.message||e); }
  finally{ TD_REVIEWING=false; TD_CANCEL=false; tdProgShow(0,0); tdRenderPending(); }
}
async function tdAlias(name,target){
  try{ TAGDICT=await (await fetch('/api/tagdict/review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:'term',names:[name],action:'alias',target:target,actor:STEWARD_ACTOR})})).json(); delete TD_ADVICE[name]; tdRender(); renderAudit(); $('tdMsg').textContent='“'+name+'” folded into “'+target+'” as an alias.'; }
  catch(e){ $('tdMsg').textContent='Alias failed: '+(e.message||e); }
}
async function tdRetireEmpty(names){
  if(!names||!names.length) return;
  if(!confirm('Retire '+names.length+' empty company tag(s) from the governed vocabulary?\n\n'+names.join(', ')+'\n\nThe generic baseline is untouched; a tag still emitted by a rule will be re-added with a warning.')) return;
  try{
    TAGDICT=await (await fetch('/api/tagdict/review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:'tag',names:names,action:'reject',actor:STEWARD_ACTOR})})).json();
    tdRender(); renderAudit();
    $('tdMsg').textContent='Retired '+names.length+' empty company tag(s).';
  }catch(e){ $('tdMsg').textContent='Retire failed: '+(e.message||e); }
}
let PACK_RES={}, PACK_CONF=[];
function packVal(x){ const s=(typeof x==='string')?x:JSON.stringify(x); return s.length>80?s.slice(0,77)+'…':s; }
function packResolve(i,useScan){
  const c=PACK_CONF[i]; if(!c) return;
  PACK_RES[c.key+'::'+c.name]=useScan?'scan':'pack';
  exportPack();  // regenerate so the download link and Apply reflect the choice
}
async function exportPack(apply){
  if(apply && !confirm('Apply the refreshed pack to this app?\n\nThis overwrites the installed domain_pack.json (a timestamped backup is kept) and reseeds the dictionary from it. Approved company terms/tags and company rules SURVIVE the reseed; pending scan-noise is discarded.')) return;
  try{
    const d=await (await fetch('/api/export-pack',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rows:(typeof ROWS!=='undefined'&&ROWS)||[], apply:!!apply, resolutions:PACK_RES})})).json();
    if(d.error){ $('tdMsg').textContent='Pack export failed: '+d.error; return; }
    const url=URL.createObjectURL(new Blob([JSON.stringify(d.pack,null,2)],{type:'application/json'}));
    const rep=Object.entries(d.report||{}).filter(([k,v])=>typeof v==='number'&&v>0&&k!=='scan_overrides').map(([k,v])=>`${k} +${v}`).join(' · ');
    let m=`Domain pack generated${d.merged_over?' (merged over the installed pack)':''}: <b>${d.learned}</b> learned addition(s)${rep?` — ${rep}`:''} · <a class="dl" href="${url}" download="domain_pack.json">download domain_pack.json</a>`;
    if(d.applied){
      m+=`<div class="msg" style="color:#1C7C54">✓ Applied: pack written to <code>${esc(d.pack_path||'')}</code>${d.pack_backup?' (backup kept)':''} and the dictionary reseeded from it. Also commit the file to the scenario's domain_pack/ folder so the next install starts from it.</div>`;
      if(typeof tdLoad==='function') tdLoad();
    } else {
      m+=` · <button class="ghost sm" onclick="exportPack(true)" style="border-color:#2EC4B6;color:#0A3D52;font-weight:600">Apply to this app</button> <span class="hint">writes the pack + reseeds the dictionary (approved items survive)</span>`;
    }
    m+=((typeof ROWS==='undefined'||!ROWS.length)?' <span class="hint">(no scan rows loaded — table mappings and curated seeds need a scanned glossary)</span>':'');
    PACK_CONF=(d.report&&d.report.conflicts)||[];
    if(PACK_CONF.length){
      m+=`<div class="msg" style="margin-top:6px"><b>${PACK_CONF.length} disagreement(s)</b> — the scan proposes a different value than the installed pack. Tick a row to take the scan's value, untick to keep the pack's (curated seeds default to the scan — they're machine-derived evidence, fresher data wins):</div>`;
      m+='<div style="max-height:220px;overflow:auto;border:1px solid var(--line);border-radius:8px;padding:6px 10px;margin-top:4px">'
        +PACK_CONF.map((c,i)=>`<label style="display:flex;gap:8px;align-items:baseline;font-size:12px;padding:2px 0;cursor:pointer"><input type="checkbox" ${c.use==='scan'?'checked':''} onchange="packResolve(${i},this.checked)"><span><code>${esc(c.key)}</code> · <b>${esc(c.name)}</b> — pack: <code>${esc(packVal(c.pack))}</code> → scan: <code>${esc(packVal(c.scan))}</code></span></label>`).join('')
        +'</div>';
    }
    $('tdMsg').innerHTML=m;
  }catch(e){ $('tdMsg').textContent='Pack export failed: '+(e.message||e); }
}
async function tdReview(kind,name,action){
  try{ TAGDICT=await (await fetch('/api/tagdict/review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind,names:[name],action,actor:STEWARD_ACTOR})})).json(); tdRender(); renderAudit(); $('tdMsg').textContent=(action==='approve'?'Approved ':'Rejected ')+kind+' “'+name+'”.'; }
  catch(e){ $('tdMsg').textContent='Review failed: '+(e.message||e); }
}
async function tdReviewAll(kind,action){
  const names=(kind==='term'?(TAGDICT.terms||[]):(TAGDICT.tags||[])).filter(t=>t.status==='pending').map(t=>kind==='term'?t.term:t.tag);
  if(!names.length) return;
  try{ TAGDICT=await (await fetch('/api/tagdict/review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind,names,action,actor:STEWARD_ACTOR})})).json(); tdRender(); renderAudit(); $('tdMsg').textContent='Approved '+names.length+' '+kind+(names.length>1?'s':'')+'.'; }
  catch(e){ $('tdMsg').textContent='Review failed: '+(e.message||e); }
}
function tdWarnShow(ws){
  const el=$('tdWarn'); if(!el) return;
  if(ws&&ws.length){ el.style.display=''; el.innerHTML='<b>Guard-rails applied:</b><br>'+ws.map(w=>'· '+esc(w)).join('<br>'); }
  else { el.style.display='none'; el.innerHTML=''; }
}
function tdAddTerm(){
  if(!TAGDICT) return; const name=($('td_newterm').value||'').trim(); if(!name){ $('tdMsg').textContent='Enter a term.'; return; }
  if((TAGDICT.terms||[]).some(t=>t.term===name)){ $('tdMsg').textContent='Term already exists.'; return; }
  const aliases=($('td_termalias').value||'').split(';').map(s=>s.trim()).filter(Boolean);
  const tags=($('td_termtags').value||'').split(';').map(s=>s.trim()).filter(Boolean);
  (TAGDICT.terms=TAGDICT.terms||[]).push({term:name,layer:'company',status:'approved',sensitivity:$('td_termsens').value||'LOW',aliases,tags,count:0});
  TAGDICT.terms.sort((a,b)=>a.term.localeCompare(b.term)); TAGDICT.term_count=TAGDICT.terms.length;
  $('td_newterm').value=''; $('td_termalias').value=''; $('td_termtags').value=''; tdRender(); $('tdMsg').textContent='Added “'+name+'” — Save to persist.';
}
function tdAddTag(){
  if(!TAGDICT) return; const name=($('td_newtag').value||'').trim(); if(!name){ $('tdMsg').textContent='Enter a tag.'; return; }
  if((TAGDICT.tags||[]).some(t=>t.tag===name)){ $('tdMsg').textContent='Tag already exists.'; return; }
  const floor=$('td_newfloor').value||null;
  (TAGDICT.tags=TAGDICT.tags||[]).push({tag:name,label:name,layer:'company',status:'approved',sensitivity_floor:floor,count:0,examples:[]});
  TAGDICT.tags.sort((a,b)=>a.tag.localeCompare(b.tag)); TAGDICT.tag_count=TAGDICT.tags.length;
  $('td_newtag').value=''; tdRender(); $('tdMsg').textContent='Added "'+name+'" — Save to persist.';
}
function tdAddRule(){
  if(!TAGDICT) return; const pat=($('td_rulepat').value||'').trim();
  const tags=($('td_ruletags').value||'').split(';').map(s=>s.trim()).filter(Boolean);
  if(!pat||!tags.length){ $('tdMsg').textContent='Enter a pattern and at least one tag.'; return; }
  try{ new RegExp(pat,'i'); }catch(e){ $('tdMsg').textContent='Invalid regex.'; return; }
  (TAGDICT.rules=TAGDICT.rules||[]).push({pattern:pat,tags,source:'steward'});
  // ensure the rule's tags exist in the vocabulary
  tags.forEach(t=>{ if(!(TAGDICT.tags||[]).some(x=>x.tag===t)) TAGDICT.tags.push({tag:t,label:t,count:0,examples:[]}); });
  TAGDICT.tags.sort((a,b)=>a.tag.localeCompare(b.tag)); TAGDICT.tag_count=TAGDICT.tags.length; TAGDICT.rule_count=TAGDICT.rules.length;
  $('td_rulepat').value=''; $('td_ruletags').value=''; tdRender(); $('tdMsg').textContent='Added rule — Save to persist.';
}
function tdToDict(){
  const tags={}; (TAGDICT.tags||[]).forEach(t=>{ tags[t.tag]={label:t.label||t.tag, layer:t.layer||'company'}; if(t.layer!=='generic'&&t.status&&t.status!=='generic') tags[t.tag].status=t.status; if(t.sensitivity_floor) tags[t.tag].sensitivity_floor=t.sensitivity_floor; });
  const terms={}; (TAGDICT.terms||[]).forEach(t=>{ terms[t.term]={aliases:t.aliases||[], sensitivity:t.sensitivity||'LOW', tags:t.tags||[], layer:t.layer||'company'}; if(t.layer!=='generic'&&t.status&&t.status!=='generic') terms[t.term].status=t.status; });
  return {schema:TAGDICT.schema, domain:TAGDICT.domain, tags, terms, rules:TAGDICT.rules||[], category_tags:TAGDICT.category_tags||{}};
}
async function tdSave(){
  if(!TAGDICT) return; $('tdMsg').textContent='Saving…';
  try{ const res=await (await fetch('/api/tagdict',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({dictionary:tdToDict(),actor:STEWARD_ACTOR})})).json();
    if(res.error) throw new Error(res.error);
    const ws=res.warnings||[]; TAGDICT=res; tdRender(); tdWarnShow(ws); renderAudit();
    $('tdMsg').textContent = ws.length ? `Saved with ${ws.length} guard-rail note${ws.length>1?'s':''}.` : 'Saved.';
  }catch(e){ $('tdMsg').textContent='Save failed: '+(e.message||e); }
}
async function tdReset(){
  if(!confirm('Reseed the tag dictionary from the domain pack + defaults?\n\nKept: steward-APPROVED company terms/tags and company rules (the governed set).\nDiscarded: PENDING scan-grown items and accreted usage counts.\nA timestamped backup of the current dictionary file is taken first.')) return;
  $('tdMsg').textContent='Reseeding…';
  try{ TAGDICT=await (await fetch('/api/tagdict/reset',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({actor:STEWARD_ACTOR})})).json(); tdRender(); renderAudit();
    const k=TAGDICT.kept||{};
    $('tdMsg').textContent=`Reseeded — preserved ${k.terms||0} approved term(s), ${k.tags||0} tag(s), ${k.rules||0} rule(s).`; }
  catch(e){ $('tdMsg').textContent='Reset failed: '+(e.message||e); }
}
// --- click-to-zoom for squashed cells (currently wired to Source) ---
function openZoom(title, bodyHtml){
  let o=document.getElementById('zoomOv');
  if(!o){
    o=document.createElement('div'); o.id='zoomOv'; o.className='zoomov';
    o.onclick=function(e){ if(e.target===o) closeZoom(); };
    o.innerHTML='<div class="zoompanel"><div class="zoomhd"><b id="zoomTitle"></b>'+
      '<button class="zoomx" aria-label="Close" onclick="closeZoom()">✕</button></div>'+
      '<div id="zoomBody" class="zoombody"></div></div>';
    document.body.appendChild(o);
  }
  o.querySelector('#zoomTitle').textContent=title;
  o.querySelector('#zoomBody').innerHTML=bodyHtml;
  o.style.display='flex';
}
function closeZoom(){ const o=document.getElementById('zoomOv'); if(o) o.style.display='none'; }
document.addEventListener('keydown',function(e){ if(e.key==='Escape') closeZoom(); });
function zoomSource(i){
  const r=ROWS[i]; if(!r) return;
  const parts=String(r.Source_Column||'').split(';').map(s=>s.trim()).filter(Boolean);
  const body = parts.length
    ? parts.map(p=>`<div class="zsrc">${esc(p)}</div>`).join('')
    : '<div class="ztxt">No source recorded for this term.</div>';
  openZoom(`${r.Term||'Source'} — ${parts.length} source${parts.length===1?'':'s'}`, body);
}
