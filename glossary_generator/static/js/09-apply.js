/* 09-apply.js — extracted from templates/index.html. Plain scripts, loaded in
   numbered order; they share one global scope, so load order matters. */
/* ---------- apply to PDC (resolve -> merge -> PATCH) ---------- */
async function getPdcToken(){
  const base=$('pdc_base').value.trim();
  if(!base){ $('tokenInfo').textContent='Enter your PDC base URL first.'; return; }
  if(!$('pdc_user').value || !$('pdc_pass').value){ $('tokenInfo').textContent='Enter username and password to mint a token.'; return; }
  $('tokenBtn').disabled=true; $('tokenInfo').textContent='Authenticating…';
  try{
    const body={base_url:base, version:$('pdc_ver').value, realm:(($('pdc_realm')&&$('pdc_realm').value.trim())||'pdc'), username:$('pdc_user').value,
                password:$('pdc_pass').value, verify_tls:$('pdc_verify').checked};
    const d=await (await fetch('/api/pdc-token',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).json();
    if(d.error){ $('tokenInfo').textContent='Token failed: '+d.error; $('tokenBtn').disabled=false; return; }
    $('pdc_token').value=d.token||'';
    if($('cmp_token')) $('cmp_token').value=d.token||'';
    savePdcConn();
    const c=d.claims||{};
    let exp=''; if(c.expires_in!=null){ const m=Math.floor(c.expires_in/60), s=c.expires_in%60; exp=` · expires in ${m}m ${s}s`; }
    const roleStr=(c.roles||[]).length?(c.roles||[]).slice(0,6).join(', '):'(no realm roles in token)';
    const adminTag=c.is_admin?'<b style="color:#2e7d32">admin ✓</b>':'<b style="color:#C25E00">not an admin role</b>';
    $('tokenInfo').innerHTML=`Token minted and filled into the field above. Signed in as <b>${esc(c.username||'?')}</b> — ${adminTag}${exp}<br><span class="hint">roles: ${esc(roleStr)}</span>`;
  }catch(e){ $('tokenInfo').textContent='Token failed: '+e; }
  $('tokenBtn').disabled=false;
}

function onDryToggle(){
  const dry=$('pdc_dryrun').checked;
  $('pdc_trust').disabled=dry;
  if(dry) $('pdc_trust').checked=false;
  $('applyBtn').textContent=dry?'Preview changes (dry-run)':'Apply to PDC';
}
function statusBadge(s){
  const map={planned:['#1C7293','planned'],applied:['#2e7d32','applied'],
    'file-level':['#0E7C86','files ✓'],
    'not-found':['#C25E00','not found'],error:['#B23A48','error'],pending:['#888','—']};
  const [c,l]=map[s]||['#888',s||'—'];
  return `<span style="display:inline-block;padding:2px 8px;border-radius:11px;font-size:11.5px;font-weight:700;color:#fff;background:${c}">${esc(l)}</span>`;
}
async function applyToPdc(){
  if(!LAST_DE_JSON){ $('applyMsg').textContent='Export the Data Elements JSON first.'; return; }
  const base=$('pdc_base').value.trim();
  if(!base){ $('applyMsg').textContent='Enter your PDC base URL above.'; return; }
  const dry=$('pdc_dryrun').checked;
  const skip=$('pdc_skipunresolved')?$('pdc_skipunresolved').checked:false;
  // a term binds to its glossary only with BOTH id and glossaryId (stamped by Resolve)
  let unresolved=0;
  (LAST_DE_JSON||[]).forEach(el=>((el.attributes||{}).businessTerms||[]).forEach(bt=>{ if(!(bt.id&&bt.glossaryId)) unresolved++; }));
  if(unresolved && !dry){
    const msg = skip
      ? unresolved+" term link(s) aren't resolved to a glossary yet. Apply will try to resolve them against PDC now; any that still can't be found will be SKIPPED (only sensitivity/CDE/lineage/rating get written). The result will show a PDC probe explaining why. Continue?"
      : unresolved+' term link(s) have no glossary id. Apply will try to resolve them now; any it still can\u2019t find attach by NAME ONLY (Glossary shows "\u2014"). Continue?';
    if(!confirm(msg)) return;
  }
  $('applyBtn').disabled=true; $('applyMsg').textContent=dry?'Building dry-run preview…':'Applying to PDC…';
  const total=(LAST_DE_JSON||[]).length;
  const body={json:LAST_DE_JSON, base_url:base, version:$('pdc_ver').value, realm:(($('pdc_realm')&&$('pdc_realm').value.trim())||'pdc'),
              username:$('pdc_user').value, password:$('pdc_pass').value,
              token:$('pdc_token').value.trim(), verify_tls:$('pdc_verify').checked,
              dry_run:dry, calculate_trust:$('pdc_trust').checked,
              apply_table_ratings:$('pdc_rate')?$('pdc_rate').checked:true,
              desc_mode:$('pdc_desc')?$('pdc_desc').value:'fill', rows:ROWS,
              skip_unresolved_terms:skip, glossary_name:$('gname').value};
  try{
    showApplyProg(0,total,dry?'Building dry-run preview…':'Applying to PDC…');
    let d=await applyStream(body,total);          // live SSE progress
    if(d==='__nostream__'){                        // fallback: one-shot call
      d=await (await fetch('/api/apply-to-pdc',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).json();
    }
    hideApplyProg();
    if(!d || d.error){ $('applyMsg').textContent='Apply failed: '+((d&&d.error)||'no response'); $('applyBtn').disabled=false; return; }
    renderApplyResults(d); renderApiCalls(d);
    if(!dry){ APPLIED=true; renderStepper(); }
  }catch(e){ hideApplyProg(); $('applyMsg').textContent='Apply failed: '+e; }
  $('applyBtn').disabled=false;
}
// stream the apply over SSE, updating the progress bar; resolves to the final
// report, or the sentinel '__nostream__' if the server didn't stream (use fallback).
async function applyStream(body,total){
  let resp;
  try{ resp=await fetch('/api/apply-to-pdc-stream',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}); }
  catch(e){ return '__nostream__'; }
  if(!resp.ok || !resp.body || !/text\/event-stream/.test(resp.headers.get('content-type')||'')){
    // server returned JSON error or no stream — try to read JSON, else fallback
    try{ const j=await resp.json(); return j; }catch(e){ return '__nostream__'; }
  }
  const reader=resp.body.getReader(), dec=new TextDecoder(); let buf='', report=null, err=null;
  while(true){
    const {value,done}=await reader.read(); if(done) break;
    buf+=dec.decode(value,{stream:true});
    let idx;
    while((idx=buf.indexOf('\n\n'))>=0){
      const ev=parseSSE(buf.slice(0,idx)); buf=buf.slice(idx+2);
      if(!ev) continue;
      if(ev.event==='progress') onApplyProgress(ev.data,total);
      else if(ev.event==='done') report=ev.data;
      else if(ev.event==='error') err=ev.data;
    }
  }
  return err||report;
}
function parseSSE(chunk){
  let ev='message', data='';
  chunk.split('\n').forEach(line=>{ if(line.startsWith('event:')) ev=line.slice(6).trim(); else if(line.startsWith('data:')) data+=line.slice(5).trim(); });
  if(!data) return null;
  try{ return {event:ev, data:JSON.parse(data)}; }catch(e){ return null; }
}
function showApplyProg(done,total,lbl){ $('applyProg').style.display='flex'; $('applyBar').style.width=(total?Math.round(done/total*100):0)+'%'; $('applyProgLbl').textContent=lbl||'Applying…'; }
function hideApplyProg(){ $('applyProg').style.display='none'; }
function onApplyProgress(ev,total){
  if(ev.phase==='column'){ const t=ev.total||total||1, v=Math.round(ev.done/t*100); $('applyBar').style.width=v+'%';
    $('applyProgLbl').textContent=`Resolving & patching column ${Math.min(ev.done+1,t)} of ${t} (${v}%)`+(ev.column?` \u00b7 ${ev.column}`:''); }
  else if(ev.phase==='columns-done'){ $('applyBar').style.width='100%'; $('applyProgLbl').textContent=`Patched ${ev.total} column(s) \u00b7 finishing\u2026`; }
  else if(ev.phase==='tables'){ $('applyProgLbl').textContent=`Rolling up ${ev.total} table rating(s)\u2026`; }
  else if(ev.phase==='trust'){ $('applyProgLbl').textContent=`Submitting Trust Score over ${ev.total} entity/entities\u2026`; }
}
// "Under the hood": the real PDC public-API choreography, built from the user's
// own connection settings and (after a dry-run) the actual planned PATCH bodies.
let APICALL_RAW=[];
function renderApiCalls(d){
  const base=(($('pdc_base').value.trim())||'https://your-pdc-host').replace(/\/+$/,'');
  const v=$('pdc_ver').value||'v2';
  const realm=(($('pdc_realm')&&$('pdc_realm').value.trim())||'pdc');
  const user=$('pdc_user').value.trim()||'<admin-user>';
  const pub=`${base}/api/public/${v}`;
  const res=(d&&d.results)||[];
  const calls=[];
  calls.push(['POST', `${base}/keycloak/realms/${realm}/protocol/openid-connect/token`,
    {'Content-Type':'application/x-www-form-urlencoded'},
    `grant_type=password&client_id=pdc-client&username=${user}&password=********`, false]);
  const sterm=res.find(r=>(r.merged_terms||[]).length); const termName=(sterm&&sterm.merged_terms[0])||'Customer Account Number';
  calls.push(['POST', `${pub}/search`, {'Authorization':'Bearer ********','Content-Type':'application/json'},
    JSON.stringify({searchTerm:termName, searchFacets:{type:['term']}}, null, 2), false]);
  let fqdn='public.public.customers.customer_account_number';
  const fr=res.find(r=>r.fqdn); if(fr) fqdn=fr.fqdn;
  calls.push(['POST', `${pub}/entities/filter?extended=true&size=500`, {'Authorization':'Bearer ********','Content-Type':'application/json'},
    JSON.stringify({filters:{fqdns:[fqdn]}}, null, 2), false]);
  let patchId='<column-entity-id>', patchBody={attributes:{features:{sensitivity:'HIGH',isCriticalDataElement:true,rating:{value:5}}}};
  const pb=res.find(r=>r.body&&r.id); if(pb){ patchId=pb.id; patchBody=pb.body; }
  calls.push(['PATCH', `${pub}/entities/${patchId}`, {'Authorization':'Bearer ********','Content-Type':'application/json'},
    JSON.stringify(patchBody, null, 2), true]);
  if($('pdc_trust')&&$('pdc_trust').checked){
    const ids=res.filter(r=>r.id).slice(0,3).map(r=>r.id); 
    calls.push(['POST', `${pub}/jobs/execute/calculate-trust-score`, {'Authorization':'Bearer ********','Content-Type':'application/json'},
      JSON.stringify({scope:ids.length?ids:['<entity-id>']}, null, 2), false]);
    calls.push(['GET', `${pub}/jobs/<job-id>/status`, {'Authorization':'Bearer ********'}, null, false]);
  }
  APICALL_RAW=[];
  $('apiCalls').innerHTML=calls.map(([verb,url,headers,body,open],i)=>{
    const h=Object.entries(headers).map(([k,val])=>`${k}: ${val}`).join('\n');
    const raw=`${verb} ${url}\n${h}${body?('\n\n'+body):''}`; APICALL_RAW.push(raw);
    return `<details class="apicall"${open?' open':''}><summary><span class="verb ${verb.toLowerCase()}">${verb}</span> ${apiVerBadge(url)}<span class="u">${esc(url)}</span><span style="flex:1"></span><button class="copybtn" onclick="event.preventDefault();copyText(APICALL_RAW[${i}],this)">Copy</button></summary><pre>${esc(raw)}</pre></details>`;
  }).join('');
  $('apiPeek').style.display='';
}
// ---- Step 4: trigger PDC Data Discovery (profiling) on the document folders ----
// Reuses the resolved Data-Elements payload (LAST_DE_JSON); the backend keeps only the
// object-store records, resolves their folders to entity ids, and starts the job.
let LAST_PROFILE_JOB=null;   // {job_id, base_url, version, verify_tls, ...auth} for status polls
function _pdcAuthBody(){
  // the shared PDC connection fields used by resolve / apply / profiling
  return {base_url:$('pdc_base').value.trim(), version:$('pdc_ver').value,
          realm:(($('pdc_realm')&&$('pdc_realm').value.trim())||'pdc'),
          username:$('pdc_user').value, password:$('pdc_pass').value,
          token:$('pdc_token').value.trim(), verify_tls:$('pdc_verify').checked};
}
async function triggerProfiling(){
  if(!LAST_DE_JSON){ $('profMsg').textContent='Pull the Data Elements first (step 1).'; return; }
  const base=$('pdc_base').value.trim();
  if(!base){ $('profMsg').textContent='Enter your PDC base URL above.'; return; }
  // only document/object records are profilable here
  const docs=(LAST_DE_JSON||[]).filter(r=>['OBJECT','FILE','DIRECTORY'].includes(String(r.type||'').toUpperCase()));
  if(!docs.length){ $('profMsg').textContent='No document/object-store records in this payload — this profiles MinIO files, not database columns.'; return; }
  $('profBtn').disabled=true; $('profMsg').textContent='Resolving document folders and starting Data Discovery…';
  try{
    const body=Object.assign(_pdcAuthBody(), {json:LAST_DE_JSON});
    const d=await (await fetch('/api/trigger-profiling',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).json();
    if(d.error){ $('profMsg').textContent='Profiling failed: '+d.error; $('profBtn').disabled=false; return; }
    LAST_PROFILE_JOB={job_id:d.job_id, ...(_pdcAuthBody())};
    const sc=(d.scope||[]).slice(0,6).join(', ')+((d.scope||[]).length>6?'…':'');
    $('profMsg').innerHTML=`Started Data Discovery on <b>${d.submitted}</b> target(s)${sc?` (${esc(sc)})`:''}`
      + (d.job_id?` · job <code>${esc(String(d.job_id).slice(0,8))}…</code>`:'')
      + (d.activity?` · ${esc(d.activity)}`:'');
    if($('profChk')) $('profChk').innerHTML = renderCheck(d.check);
    $('profStatusBtn').style.display = d.job_id ? '' : 'none';
    // v3's bulk endpoint returns no job id — poll the ENTITIES instead: their
    // profiledAt flips when discovery finishes. Works on every API version.
    if(d.scope_ids&&d.scope_ids.length) await watchDiscovery(d.scope_ids, d.baseline||{});
  }catch(e){ $('profMsg').textContent='Profiling failed: '+e; }
  $('profBtn').disabled=false;
}
async function watchDiscovery(ids, baseline){
  aiProgStart('PDC Data Discovery',ids.length);
  const bodyBase=Object.assign(_pdcAuthBody(),{ids:ids,baseline:baseline});
  const started=Date.now(); let last=0;
  while(!AI_CANCEL && (Date.now()-started)<10*60*1000){
    await new Promise(r=>setTimeout(r,6000));
    if(AI_CANCEL) break;
    try{
      const d=await (await fetch('/api/discovery-progress',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(bodyBase)})).json();
      if(d.error){ $('profMsg').innerHTML+=`<div class="msg">progress check failed: ${esc(d.error)}</div>`; break; }
      last=d.profiled; aiProgUpdate(d.profiled,d.total,'PDC Data Discovery');
      if(d.done){
        aiProgEnd();
        $('profMsg').innerHTML=`<b style="color:#1C7C54">\u2713 Data Discovery complete — ${d.total} of ${d.total} profiled.</b> Re-pull the Data Elements (step 1) or the app-vs-PDC side-by-side to see each file's Data Quality — then re-Apply and recalculate Trust.`;
        return;
      }
    }catch(e){ break; }
  }
  aiProgEnd();
  if(AI_CANCEL){ $('profMsg').innerHTML+=`<div class="msg">Stopped watching — the job keeps running in PDC (Workers page); ${last} profiled so far.</div>`; }
  else { $('profMsg').innerHTML+=`<div class="msg">Still running after 10 min (${last} profiled) — folders sometimes don't report per-entity timestamps; check PDC's Workers page for the job itself.</div>`; }
}
async function checkProfilingJob(){
  if(!LAST_PROFILE_JOB||!LAST_PROFILE_JOB.job_id){ $('profMsg').textContent='No profiling job to check yet.'; return; }
  $('profStatusBtn').disabled=true;
  try{
    const d=await (await fetch('/api/job-status',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(LAST_PROFILE_JOB)})).json();
    if(d.error){ $('profMsg').textContent='Status check failed: '+d.error; }
    else{
      const done=['COMPLETED','SUCCESS','SUCCEEDED','FAILED','ERROR','CANCELLED'].includes(String(d.status||'').toUpperCase());
      $('profMsg').innerHTML=`Job status: <b>${esc(d.status||'unknown')}</b>`
        + (d.activity?` · ${esc(d.activity)}`:'')
        + (d.duration?` · ${Math.round(d.duration)}s`:'')
        + (done?' — when COMPLETED, the files now carry PDC profiling + Data Quality.':' — still running; check again shortly.');
    }
  }catch(e){ $('profMsg').textContent='Status check failed: '+e; }
  $('profStatusBtn').disabled=false;
}
function renderApplyResults(d){
  const verb=d.dry_run?'planned':'written';
  let head=`<b>${d.found}</b>/<b>${d.total}</b> columns resolved · `;
  head+=d.dry_run?`<b>${d.planned}</b> change(s) ${verb}`:`<b>${d.applied}</b> ${verb}`;
  if(d.tables_rated) head+=` · <b>${d.tables_rated}</b> table(s) rated`;
  if(d.objectstore_folders) head+=` · <b>${d.objectstore_folders}</b> object-store folder(s) — files carry Trust Score directly`;
  if(d.terms_resolved_on_apply) head+=` · <b>${d.terms_resolved_on_apply}</b> term link(s) auto-resolved`;
  if(d.not_found) head+=` · <b style="color:#C25E00">${d.not_found}</b> not found`;
  if(d.errors) head+=` · <b style="color:#B23A48">${d.errors}</b> error(s)`;
  if(d.trust){ head+= d.trust.ok?` · trust: ${esc(d.trust.status||'submitted')} (${d.trust.submitted})`
                              : ` · <span style="color:#B23A48">trust: ${esc(d.trust.message||d.trust.status||'unavailable')}</span>`; }
  if(d.unresolved_terms&&d.unresolved_terms.length){
    const verbU=d.unresolved_terms_skipped?'skipped (not written \u2014 no glossary link)':'written by name only (Glossary shows "\u2014")';
    head+=`<div class="msg" style="color:#C25E00;margin-top:4px"><b>${d.unresolved_terms.length}</b> term(s) not resolved to a glossary, ${verbU}: ${esc(d.unresolved_terms.slice(0,8).join(', '))}${d.unresolved_terms.length>8?'…':''}. Import the glossary in PDC, then run Resolve.</div>`;
  }
  if(d.probe&&d.probe.length){
    const anyHit=d.probe.some(p=>(p.search_hits>0)||(p.filter_hits>0));
    const rows=d.probe.map(p=>{
      const st=(p.search_types&&p.search_types.length)?` [${esc(p.search_types.join(', '))}]`:'';
      const ft=(p.filter_types&&p.filter_types.length)?` [${esc(p.filter_types.join(', '))}]`:'';
      return `<div class="prow"><b>${esc(p.name)}</b> · search ${p.search_hits} hit(s)${st}`
        + `${p.search_has_glossaryId?' · glossaryId\u2713':''}${p.bt_match?' · businessTerms\u2713':''}`
        + ` · filter ${p.filter_hits} hit(s)${ft}${p.search_error?(' · search error: '+esc(p.search_error)):''}</div>`;
    }).join('');
    const verdict = anyHit
      ? 'PDC returned matches but none resolved to a glossary term with an id + glossaryId. Confirm the import created <b>terms</b> in the Glossary tree (not just a file), on this same PDC instance/realm. If the type above looks like a term, paste it back and the matcher can be tuned to it.'
      : 'PDC returned nothing for these names — the glossary is not imported (or under a different name/instance). In PDC: <b>Glossary \u2192 Actions \u2192 Import</b> \u2192 drop the JSONL (Generate JSONL) \u2192 Submit, then re-apply.';
    head+=`<details class="nfwrap" open><summary>PDC probe — why term links didn't resolve</summary><div class="probe">${rows}<div class="verdict">${verdict}</div></div></details>`;
  }
  $('applyMsg').innerHTML=head;
  const ratingChip=v=>v?`<span class="rate" title="Suggested rating ${v}/5">★ ${v}</span>`:'';
  const dqChip=v=>(v||v===0)?`<span class="dq" title="Data Quality score ${v}/100">DQ ${v}</span>`:'';
  const rows=(d.results||[]).map(r=>{
    const cur=(r.current_terms||[]); const mer=(r.merged_terms||[]);
    const feat=(((r.body||{}).attributes||{}).features||{});
    const rv=(feat.rating||{}).value; const qv=feat.qualityScore;
    const terms=mer.length?`${cur.length?esc(cur.join(', '))+' → ':''}<b>${esc(mer.join(', '))}</b> ${ratingChip(rv)} ${dqChip(qv)}`:'—';
    const idCell=r.id?`<code title="${esc(r.id)}">${esc(String(r.id).slice(0,8))}…</code>`:'—';
    const body=r.body?`<details><summary class="msg" style="cursor:pointer">view PATCH body</summary><pre style="white-space:pre-wrap;font-size:11.5px;margin:6px 0 0">${esc(JSON.stringify(r.body,null,2))}</pre></details>`:'';
    const note=r.message?`<div class="msg" style="color:#B23A48">${esc(r.message)}</div>`:'';
    const colTitle=esc(r.column||'')+(r.fqdn?' — '+esc(r.fqdn):'');
    return `<tr>
      <td title="${colTitle}"><div class="colname">${esc(r.column)}</div><div class="colfqdn">${esc(r.fqdn||'')}</div></td>
      <td>${statusBadge(r.status)}</td>
      <td>${idCell}</td>
      <td class="termcell">${terms}${body}${note}</td></tr>`;
  }).join('');
  // table-level rollup section
  let tblHtml='';
  if(d.table_results&&d.table_results.length){
    const trows=d.table_results.map(t=>{
      const idCell=t.id?`<code title="${esc(t.id)}">${esc(String(t.id).slice(0,8))}…</code>`:'—';
      const bad=(t.status==='error'||t.status==='not-found');
      const note=t.message?`<div class="msg" style="color:${bad?'#B23A48':'var(--mute)'}">${esc(t.message)}</div>`:'';
      const bits=[];
      if(t.rating!=null) bits.push(`${ratingChip(t.rating)} <span class="msg">mean of ${t.from_columns}</span>`);
      if(t.quality!=null) bits.push(`${dqChip(t.quality)} <span class="msg">mean of ${t.quality_from}</span>`);
      return `<tr>
        <td title="${esc(t.table||'')}"><div class="colname">${esc(t.table)}</div></td>
        <td>${statusBadge(t.status)}</td>
        <td>${idCell}</td>
        <td class="termcell">${bits.join(' &nbsp; ')||'—'}${note}</td></tr>`;
    }).join('');
    tblHtml=`<div class="tablecard" style="margin-top:14px"><div style="overflow:auto"><table class="ptbl applytbl">
      <thead><tr><th>Table</th><th>Status</th><th>Entity</th><th>Rating &amp; DQ → table (feed Trust Score)</th></tr></thead>
      <tbody>${trows}</tbody></table></div></div>`;
  }
  $('applyResults').innerHTML=`<div class="tablecard" style="margin-top:10px"><div style="overflow:auto"><table class="ptbl applytbl">
    <thead><tr><th>Column</th><th>Status</th><th>Entity</th><th>Business terms (current → merged) · rating / PATCH</th></tr></thead>
    <tbody>${rows||'<tr><td colspan="4" class="msg">No columns.</td></tr>'}</tbody></table></div></div>${tblHtml}`;
}

/* ---------- app vs PDC profiling compare ---------- */
function _pdcStat(stats, names){
  if(!stats||typeof stats!=='object') return null;
  const lk={}; Object.keys(stats).forEach(k=>lk[k.toLowerCase()]=stats[k]);
  for(const n of names){ const v=lk[n.toLowerCase()]; if(v!=null&&v!=='') return v; }
  return null;
}
function _num(v){ return (typeof v==='number')?v:(v!=null&&!isNaN(parseFloat(v))?parseFloat(v):null); }
async function comparePdcProfiling(){
  if(!LAST_DISCOVERY||!LAST_DISCOVERY.tables){ $('cmpMsg').textContent='Run discovery first.'; return; }
  let base=$('cmp_base').value.trim();
  if(!base && $('pdc_base')) base=$('pdc_base').value.trim();
  if(!base){ $('cmpMsg').textContent='Enter your PDC base URL.'; return; }
  const cols=[];
  LAST_DISCOVERY.tables.forEach(t=>t.columns.forEach(c=>cols.push(
    {schemaName:LAST_DISCOVERY.schema, tableName:t.name, columnName:c.column, type:'COLUMN'})));
  $('cmpBtn').disabled=true; $('cmpMsg').textContent=`Pulling PDC profiling for ${cols.length} columns…`;
  try{
    const body={columns:cols, base_url:base, version:($('cmp_ver').value||'v2'), realm:(($('pdc_realm')&&$('pdc_realm').value.trim())||'pdc'), 
                username:$('cmp_user').value, password:$('cmp_pass').value,
                token:$('cmp_token').value.trim()||($('pdc_token')?$('pdc_token').value.trim():''),
                verify_tls:$('cmp_verify').checked};
    const d=await (await fetch('/api/pdc-profiling',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).json();
    if(d.error){ $('cmpMsg').textContent='Compare failed: '+d.error; $('cmpBtn').disabled=false; return; }
    renderCompare(d.profiles||{});
    $('cmpMsg').innerHTML=`PDC returned profiling for <b>${d.count}</b> of ${d.requested} columns.`;
  }catch(e){ $('cmpMsg').textContent='Compare failed: '+e; }
  $('cmpBtn').disabled=false;
}
function renderCompare(profiles){
  const sch=LAST_DISCOVERY.schema;
  const pctOrDash=v=>v==null?'—':(v<=1?pct(v):v);
  const cell=(a,b)=>`${a}<span class="msg"> / </span>${b==null?'<span class="msg">—</span>':b}`;
  let blocks='';
  LAST_DISCOVERY.tables.forEach(t=>{
    const rows=t.columns.map(c=>{
      const key=`${sch}.${t.name}.${c.column}`;
      const p=profiles[key]; const st=p?(p.stats||{}):null;
      if(!p) return `<tr style="opacity:.55"><td><b>${esc(c.column)}</b></td>
        <td>${pct(c.completeness)}<span class="msg"> / —</span></td>
        <td>${(c.distinct||0).toLocaleString()}<span class="msg"> / —</span></td>
        <td>${pct(c.uniqueness)}<span class="msg"> / —</span></td>
        <td class="msg">not in PDC</td></tr>`;
      const pCard=_num(_pdcStat(st,['cardinality','distinctCount','distinct','distinctValues']));
      const pUniq=_num(_pdcStat(st,['uniqueness','selectivity']));
      const pDens=_num(_pdcStat(st,['density','completeness','nonNullDensity']));
      const pNull=_num(_pdcStat(st,['nulls','nullCount','nullValues']));
      return `<tr>
        <td><b>${esc(c.column)}</b></td>
        <td>${cell(pct(c.completeness), pctOrDash(pDens))}</td>
        <td>${cell((c.distinct||0).toLocaleString(), pCard==null?null:pCard.toLocaleString())}</td>
        <td>${cell(pct(c.uniqueness), pctOrDash(pUniq))}</td>
        <td class="msg">${pNull!=null?('nulls '+pNull):'matched'}</td></tr>`;
    }).join('');
    blocks+=`<div class="ptbl-wrap"><div class="ptbl-hd"><span>${esc(t.name)}</span><span class="rc">app / PDC</span></div>
      <div style="overflow:auto"><table class="ptbl">
        <thead><tr><th>Column</th><th>Complete</th><th>Distinct</th><th>Unique</th><th>PDC</th></tr></thead>
        <tbody>${rows}</tbody></table></div></div>`;
  });
  $('cmpResults').innerHTML=`<h3 style="margin:6px 0 8px">App vs PDC profiling <span class="note" style="font-weight:400">— each cell shows app / PDC</span></h3>${blocks}`;
}
