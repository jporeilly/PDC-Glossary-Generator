/* 01-core.js — extracted from templates/index.html. Plain scripts, loaded in
   numbered order; they share one global scope, so load order matters. */
const $ = id => document.getElementById(id);
const esc = s => String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
// Reusable "result + verdict" panel for actions (Generate, Scan, Discovery) —
// same shape as the PDC Resolve probe: key facts, findings, plain-English verdict.
function renderCheck(c){
  if(!c) return '';
  const icon = c.tone==='bad'?'\u2715':(c.tone==='warn'?'\u26a0':'\u2713');
  const kf = (c.rows||[]).map(r=>{
    let v=esc(r.value);
    if(/sensitivity/i.test(r.label)){
      v=v.replace(/HIGH (\d+)/,'HIGH <b class="sens-hi">$1</b>')
         .replace(/MED (\d+)/,'MED <b class="sens-md">$1</b>')
         .replace(/LOW (\d+)/,'LOW <b class="sens-lo">$1</b>');
    }
    return `<span class="kf"><b>${esc(r.label)}:</b> ${v}</span>`;
  }).join('');
  const iss = (c.issues||[]).map(i=>{
    // each flagged term is a chip — click to jump to the grid filtered to it
    const chips=(i.terms||[]).map(t=>`<button class="chkterm" onclick="chkJump(decodeURIComponent('${encodeURIComponent(t.q||t.label||'')}'))" title="Open in the review grid">${esc(t.label||t.q||'')}</button>`).join('');
    return `<div class="chkissue ${i.tone==='bad'?'bad':'warn'}">${esc(i.text)}${chips?`<div class="chkterms">${chips}</div>`:''}</div>`;
  }).join('');
  return `<details class="nfwrap" open><summary>${icon} ${esc(c.title||'Check')}</summary>`
    + `<div class="chk ${c.tone||'ok'}"><div class="chkrows">${kf}</div>${iss}`
    + `<div class="verdict">${esc(c.verdict||'')}</div></div></details>`;
}
// jump from a check chip to the review grid, filtered to that term
function chkJump(q){
  if(typeof showPage==='function') showPage('glossary');
  const el=$('q'); if(el){ el.value=q; }
  if(typeof applyFilter==='function') applyFilter();
  const tbl=$('tbl'); if(tbl&&tbl.scrollIntoView) tbl.scrollIntoView({behavior:'smooth',block:'start'});
}
const truthy = v => ["y","yes","true","1"].includes(String(v).toLowerCase());
// copy text to clipboard with a brief "Copied" confirmation on the button
function copyText(t,btn){
  const ok=()=>{ if(btn){ const o=btn.textContent; btn.textContent='Copied \u2713'; setTimeout(()=>btn.textContent=o,1400); } };
  if(navigator.clipboard&&navigator.clipboard.writeText){ navigator.clipboard.writeText(t).then(ok,()=>fallbackCopy(t,ok)); }
  else fallbackCopy(t,ok);
}
function fallbackCopy(t,ok){ const ta=document.createElement('textarea'); ta.value=t; ta.style.position='fixed'; ta.style.opacity='0'; document.body.appendChild(ta); ta.select(); try{document.execCommand('copy');ok&&ok();}catch(e){} document.body.removeChild(ta); }
// ---- reusable "Under the hood" panel: API/SQL calls + viewable source ----
// Tag an API call with its PDC public-API version (v1/v2/v3) parsed from the URL,
// so the developer can see at a glance which version a call targets. Keycloak token
// calls get a 'keycloak' tag; non-PDC/internal calls get nothing.
function apiVerBadge(url){
  const m=String(url||'').match(/\/api\/public\/(v\d+)\b/i);
  if(m){ const v=m[1].toLowerCase(); return `<span class="apiver ${v}" title="PDC public API ${v}">${v}</span> `; }
  if(/\/keycloak\//i.test(url||'')) return '<span class="apiver kc" title="Keycloak (auth, not the PDC public API)">keycloak</span> ';
  return '';
}
function _hoodBlocks(calls, rawName){
  window[rawName]=[]; const arr=window[rawName];
  return calls.map((c,i)=>{
    const h=Object.entries(c.headers||{}).map(([k,v])=>`${k}: ${v}`).join('\n');
    const body=c.body==null?'':(typeof c.body==='string'?c.body:JSON.stringify(c.body,null,2));
    const raw=`${c.verb} ${c.url}\n${h}${body?('\n\n'+body):''}`; arr.push(raw);
    const vl=String(c.verb).toLowerCase().replace(/[^a-z]/g,'')||'post';
    return `<details class="apicall"${c.open?' open':''}><summary><span class="verb ${vl}">${esc(c.verb)}</span> ${apiVerBadge(c.url)}<span class="u">${esc(c.url)}</span><span style="flex:1"></span><button class="copybtn" onclick="event.preventDefault();copyText(${rawName}[${i}],this)">Copy</button></summary><pre>${esc(raw)}</pre></details>`;
  }).join('');
}
function _hoodScripts(files){
  if(!files||!files.length) return '';
  return '<div class="lbl">Scripts that run this</div>'+files.map(f=>{
    const fn=typeof f==='string'?f:f.file, note=(typeof f==='object'&&f.note)?` <span class="hint">${esc(f.note)}</span>`:'';
    return `<div class="srcfile"><code>${esc(fn)}</code>${note}<span style="flex:1"></span><button class="copybtn" onclick="viewSource('${esc(fn)}',this)">View source</button></div>`;
  }).join('');
}
function renderHood(containerId, spec){
  const el=$(containerId); if(!el) return;
  const rawName=('HOOD_'+containerId).replace(/[^A-Za-z0-9_]/g,'_');
  let html='';
  if(spec.intro) html+=`<p class="note" style="margin:4px 0 8px">${spec.intro}</p>`;
  if(spec.calls&&spec.calls.length){ html+='<div class="lbl">Calls executed</div><div class="apicalls">'+_hoodBlocks(spec.calls,rawName)+'</div>'; }
  html+=_hoodScripts(spec.scripts);
  el.innerHTML=html;
}
async function viewSource(file, btn){
  const row=btn.closest('.srcfile'); let pre=row.nextElementSibling;
  if(pre&&pre.classList.contains('srcpre')){ pre.remove(); btn.textContent='View source'; return; }
  btn.textContent='Loading\u2026';
  try{
    const d=await (await fetch('/api/source?file='+encodeURIComponent(file))).json();
    pre=document.createElement('pre'); pre.className='srcpre';
    pre.textContent=d.content||('('+(d.error||'unavailable')+')'); row.after(pre); btn.textContent='Hide source';
  }catch(e){ btn.textContent='View source'; }
}
// ---- per-stage "Under the hood" panels (built from the real calls each runs) ----
function _firstSchema(){ const c=(typeof CONNS!=='undefined'&&CONNS||[]).find(x=>x.schema); return (c&&c.schema)||'public'; }
function renderHoodScan(){
  const sch=_firstSchema();
  renderHood('hoodScan',{
    intro:'A database scan is <b>read-only</b> introspection plus optional sampling &mdash; nothing is written. It connects as a least-privilege user (CONNECT/USAGE/SELECT), which is good governance from step one.',
    calls:[
      {verb:'SQL',url:'information_schema.columns \u2014 tables, columns, types',headers:{},open:true,
       body:`SELECT table_name, column_name, data_type, ordinal_position,\n       is_nullable, column_default\nFROM information_schema.columns\nWHERE table_schema = '${sch}'\nORDER BY table_name, ordinal_position;`},
      {verb:'SQL',url:'pg_catalog \u2014 primary & foreign keys (drives PK/FK + lineage)',
       body:"-- primary keys\nSELECT c.relname, a.attname\nFROM pg_constraint con\nJOIN pg_class c     ON c.oid = con.conrelid\nJOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = ANY(con.conkey)\nWHERE con.contype = 'p';\n-- foreign keys also read con.confrelid for the referenced table/column"},
      {verb:'SQL',url:'pg_description \u2014 column comments (reused as definitions)',
       body:"SELECT c.relname, a.attname, d.description\nFROM pg_description d\nJOIN pg_class c     ON c.oid = d.objoid\nJOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = d.objsubid;"},
      {verb:'SQL',url:'sample rows \u2014 only when \u201cSample values\u201d is on (profiling)',
       body:`SELECT * FROM "${sch}"."customers" LIMIT 80;   -- per table, for DQ + pattern hints`}
    ],
    scripts:[{file:'dbconn.py',note:'opens the connection with the right driver'},
             {file:'suggester.py',note:'harvest_live + profile_live + suggest'},
             {file:'app.py',note:'/api/scan dispatches by source type'}]
  });
}
function renderHoodFiles(){
  renderHood('hoodFiles',{
    intro:'Document stores are browsed over the <b>S3 API</b> against MinIO. The endpoint must be an IP/host (not &ldquo;localhost&rdquo;) so the SDK uses path-style addressing, which MinIO requires.',
    calls:[
      {verb:'S3',url:'ListObjectsV2 \u2014 one folder level (Delimiter \u201c/\u201d)',headers:{},open:true,
       body:'s3.list_objects_v2(\n    Bucket="documents",\n    Prefix="compliance/",\n    Delimiter="/")'},
      {verb:'S3',url:'GetObject \u2014 read a file to preview or profile its content',
       body:'s3.get_object(\n    Bucket="documents",\n    Key="compliance/epa_compliance_sedona_2026Q1.pdf")'}
    ],
    scripts:[{file:'suggester.py',note:'harvest_minio / harvest_files / list_objects'},
             {file:'app.py',note:'/api/list-objects, /api/object-bytes'}]
  });
}
function renderHoodGloss(){
  renderHood('hoodGloss',{
    intro:'The term fields are built <b>locally at scan time</b> (see &ldquo;How terms are defined &amp; built&rdquo; above) &mdash; no calls are needed for that. The calls below are the optional actions this page offers; the only <b>outbound</b> one is LLM enrichment, to your own local Ollama, never the cloud. <b>Note:</b> the JSONL is <i>not</i> generated here &mdash; that&rsquo;s on the Govern page. (Ollama&rsquo;s text endpoint is also called <code>/api/generate</code>; it generates a <i>sentence</i>, not the glossary file.)',
    calls:[
      {verb:'LLM',url:'POST http://localhost:11434/api/generate \u2014 Ollama text generation (rewrite one definition)',headers:{'Content-Type':'application/json'},open:true,
       body:JSON.stringify({model:'llama3.2:3b',prompt:'Write a one-sentence business definition for column \u201cservice_address\u201d on table customers\u2026',stream:false},null,2)},
      {verb:'GET',url:'http://localhost:11434/api/tags \u2014 is the model available?',headers:{}},
      {verb:'POST',url:location.origin+'/api/enhance-glossary \u2014 overlay a real export\u2019s definitions/tags onto matches',headers:{'Content-Type':'application/json'}},
      {verb:'POST',url:location.origin+'/api/retag \u2014 re-derive governed tags for the shown terms ("Suggest tags")',headers:{'Content-Type':'application/json'}},
      {verb:'POST',url:location.origin+'/api/recommend-resolutions \u2014 advise Merge / Disambiguate / Keep separate per duplicate group (evidence \u2192 live value probe \u2192 AI agent)',headers:{'Content-Type':'application/json'}},
      {verb:'POST',url:location.origin+'/api/qa-definitions \u2014 lint + AI-judge definitions (QA_Issues / QA_Suggestion)',headers:{'Content-Type':'application/json'}},
      {verb:'POST',url:location.origin+'/api/ai-categorize \u2014 AI files uncategorized terms into known categories',headers:{'Content-Type':'application/json'}},
      {verb:'POST',url:location.origin+'/api/draft-policies \u2014 draft PDC pattern/dictionary rules from detection seeds (format=zip to download)',headers:{'Content-Type':'application/json'}},
      {verb:'POST',url:location.origin+'/api/similarity \u2014 score shown terms pairwise; suggest same-concept merges ("Find similar")',headers:{'Content-Type':'application/json'}},
      {verb:'POST',url:location.origin+'/api/load-glossary \u2014 open an existing export for review (round-trip)',headers:{'Content-Type':'application/json'}}
    ],
    scripts:[{file:'similarity.py',note:'score_pair 2192 suggest_merges (lexical + token/abbrev + structural)'},{file:'llm.py',note:'local Ollama client (enrich, /api/tags, /api/ps)'},
             {file:'suggester.py',note:'suggest() built these terms during the scan'},
             {file:'app.py',note:'/api/enrich, /api/enhance-glossary, /api/load-glossary'}]
  });
}
function renderHoodGen(){
  const gname=($('gname')&&$('gname').value)||'Business Glossary';
  renderHood('hoodGen',{
    intro:'Generating runs locally too. It serialises your kept terms <b>plus the stewardship and ratings set above</b> into PDC import-ready JSONL &mdash; one line per glossary, category and term &mdash; which you then import in PDC. It also <b>authors the Registry</b> (<code>registries/registry.&lt;id&gt;.json</code>) with the governed tag/term vocabulary embedded, for the Policy Generator.',
    calls:[
      {verb:'POST',url:location.origin+'/api/generate \u2014 build import-ready JSONL + author the Registry',headers:{'Content-Type':'application/json'},open:true,
       body:JSON.stringify({rows:'[\u2026kept terms\u2026]',glossary_name:gname,governance:'{default:{businessSteward,owner,custodian,rating\u2026}, categories:{\u2026per-category overrides\u2026}}'},null,2)}
    ],
    scripts:[{file:'suggester.py',note:'to_jsonl_records builds the glossary + categories + terms'},
             {file:'registry/bridge.py',note:'build_registry \u2014 one concept per term + embedded tag_vocabulary'},
             {file:'app.py',note:'/api/generate endpoint'}]
  });
}
function renderHoodGov(){
  const kb=(($('k_base')&&$('k_base').value.trim())||'<server>/keycloak').replace(/\/+$/,'');
  const realm=(($('k_realm')&&$('k_realm').value.trim())||'pdc');
  renderHood('hoodGov',{
    intro:'Stewards bind to PDC accounts by <b>Keycloak UUID</b>. Fetching the roster live guarantees the ids match the target instance &mdash; the admin token comes from the <code>master</code> realm, users are listed from the <code>'+esc(realm)+'</code> realm.',
    calls:[
      {verb:'POST',url:kb+'/realms/master/protocol/openid-connect/token \u2014 admin token',headers:{'Content-Type':'application/x-www-form-urlencoded'},open:true,
       body:'grant_type=password&client_id=admin-cli&username=<admin>&password=********'},
      {verb:'GET',url:kb+'/admin/realms/'+realm+'/users?max=2000 \u2014 list users',headers:{'Authorization':'Bearer ********'}},
      {verb:'GET',url:kb+'/admin/realms/'+realm+'/users/{id}/role-mappings/realm \u2014 realm roles (role-based assign)',headers:{'Authorization':'Bearer ********'}},
      {verb:'GET',url:location.origin+'/api/people \u2014 the saved roster (people.json)',headers:{}}
    ],
    scripts:[{file:'app.py',note:'/api/keycloak-users \u2014 token, users, role-mappings'}]
  });
}
function renderHoodBulk(){
  const base=(($('bl_base')&&$('bl_base').value.trim())||'https://<pdc-host>').replace(/\/+$/,'');
  const ver=(($('bl_ver')&&$('bl_ver').value.trim())||'v2');
  renderHood('hoodBulk',{
    intro:'For each CSV row the app runs the <b>Connect + Ingest</b> steps against the PDC Public API: it <b>creates</b> the data source, triggers the <b>initial metadata ingest</b> scoped to it, then <b>polls</b> the job \u2014 the steps that precede profiling, identification and the glossary. Secrets are sent to PDC only; the app never stores them.',
    calls:[
      {verb:'POST',url:base+'/api/public/'+ver+'/data-sources \u2014 create the data source',headers:{'Content-Type':'application/json','Authorization':'Bearer ********'},open:true,
       body:JSON.stringify({resourceName:'CopperState_Core_Banking',databaseType:'POSTGRES',configMethod:'credentials',host:'\u2026',port:'5432',databaseName:'cscu_core',userName:'\u2026',password:'********',schemaNames:['cscu_core']},null,2)},
      {verb:'POST',url:base+'/api/public/'+ver+'/jobs/execute/metadata/ingest \u2014 initial ingest ("Ingest Schemas or Scan")',headers:{'Content-Type':'application/json','Authorization':'Bearer ********'},
       body:'// the same config body + the created resourceId (+ fqdnId).\n// NOT metadata/re-ingest \u2014 that refresh job wants entity UUIDs; a new\n// source id isn\u2019t a UUID, so re-ingest 400s: /scope/0 must match format "uuid".'},
      {verb:'GET',url:base+'/api/public/'+ver+'/jobs/{jobId}/status \u2014 poll until COMPLETED',headers:{'Authorization':'Bearer ********'}},
      {verb:'POST',url:base+'/api/public/'+ver+'/data-sources/filter \u2014 list existing (PDC-side export)',headers:{'Content-Type':'application/json','Authorization':'Bearer ********'},
       body:JSON.stringify({filters:{resourceNames:['*']}},null,2)},
      {verb:'GET',url:location.origin+'/api/connections/export.csv \u2014 export your saved connections to a loader CSV (local; includes secrets)',headers:{}}
    ],
    scripts:[{file:'pdc_api.py',note:'bulk_load_one \u2192 create_data_source \u2192 run_job(metadata/ingest) \u2192 wait_job'},
             {file:'app.py',note:'/api/pdc/bulk-load, /api/connections/export.csv'}]
  });
}
function renderHoodDict(){
  renderHood('hoodDict',{
    intro:'The Term &amp; Tag dictionary is a <b>persisted per-company artifact</b> (<code>tag_dictionary.json</code>) &mdash; a generic baseline plus a company layer grown from scans. Tagging reads it live, and it&rsquo;s <b>embedded in the Registry</b> at export so the Policy Generator draws Assign-Tags from the same allow-list. Edits are guard-railed; new scanned items are <b>pending</b> until a steward approves them.',
    calls:[
      {verb:'GET',url:location.origin+'/api/tagdict \u2014 load the dictionary (terms, tags, rules, counts, pending)',headers:{},open:true},
      {verb:'POST',url:location.origin+'/api/tagdict \u2014 steward save (guard-railed; returns warnings)',headers:{'Content-Type':'application/json'},
       body:JSON.stringify({dictionary:{terms:'{\u2026}',tags:'{\u2026}',rules:'[\u2026]'}},null,2)},
      {verb:'POST',url:location.origin+'/api/tagdict/review \u2014 approve / reject pending items',headers:{'Content-Type':'application/json'},
       body:JSON.stringify({kind:'tag',names:['\u2026'],action:'approve'},null,2)},
      {verb:'POST',url:location.origin+'/api/tagdict/reset \u2014 reseed from domain + baseline',headers:{}},
      {verb:'GET',url:location.origin+'/api/tagdict/export.json \u2014 download the governance artifact',headers:{}},
      {verb:'POST',url:location.origin+'/api/scan \u2014 every scan accretes used tags/terms as pending',headers:{'Content-Type':'application/json'}},
      {verb:'GET',url:location.origin+'/api/audit \u2014 recent governance actions (who/what/when)',headers:{}},
      {verb:'GET',url:location.origin+'/api/audit/export.json \u2014 full audit trail (ships alongside the Registry)',headers:{}},
      {verb:'GET',url:location.origin+'/api/governance-summary \u2014 one payload for the Viz app: vocabulary health + audit + drift (CORS-enabled)',headers:{}}
    ],
    scripts:[{file:'tagdict.py',note:'seed \u2192 accrete (pending) \u2192 review \u2192 _guardrail/replace \u2192 lift_sensitivity \u2192 canonical_name \u2192 summary'},
             {file:'audit.py',note:'append-only steward trail; summary() is embedded in the Registry'},
             {file:'registry/bridge.py',note:'_tag_vocabulary + _audit_summary embed the governed vocabulary + provenance'},
             {file:'app.py',note:'/api/tagdict, /review, /reset, /export.json, /retag, /api/audit'}]
  });
}
let ROWS=[], SHOWN=[], lastShownPos=null, COMPUTE='auto';
let PEOPLE=[], PEOPLE_LOADED=false, CONNS=[], SETTINGS={}, editId=null;
let LAST_DISCOVERY=null, CUR_GLOSS=null, LAST_DE_JSON=null, LAST_JSONL='';

function showPage(p){
  CUR_PAGE=p;
  document.querySelectorAll('.page').forEach(s=>s.classList.toggle('on', s.id==='page-'+p));
  document.querySelectorAll('.nav button').forEach(b=>b.classList.toggle('on', b.dataset.page===p));
  const fl=$('flow'); if(fl) fl.style.display=(p==='home'||p==='settings')?'none':'flex';
  renderStepper();
  if(p==='govern' && !PEOPLE_LOADED) loadPeople();
  if(p==='govern'){ initGovDefaults(); }
  if(p==='govern' && ROWS.length) updateKeepUI();
  if(p==='schema') schemaPageInit();
  if(p==='dictionary'){ if(typeof tdLoad==='function' && !TAGDICT) tdLoad(); renderHoodDict(); renderAudit(); }
  if(p==='files'){ filesPageInit(); renderHoodFiles(); }
  if(p==='connections'){ renderHoodScan(); renderHoodHarvest(); renderHoodBulk();
    if($('hv_base') && !$('hv_base').value && window.SETTINGS && SETTINGS.pdc_base) $('hv_base').value=SETTINGS.pdc_base; }
  if(p==='glossary') renderHoodGloss();
  if(p==='govern'){ renderHoodGov(); renderHoodGen(); }
  if(p==='apply' && $('apiCalls') && !$('apiCalls').innerHTML.trim()) renderApiCalls(null);
}
// ---- persistent workflow stepper (Connect → Review → Govern → Generate → Apply) ----
// persistent workflow stepper — each stage maps to a nav page:
// Connect→Connections, Review→Glossary, Govern→Govern, Resolve→Resolve Term IDs.
// (Generate is an action on the Govern page, not its own destination.)
const FLOW=[{k:'connect',label:'Connect',page:'connections',hint:'Add sources & scan'},
  {k:'review',label:'Review',page:'glossary',hint:'Scan + review the candidate terms'},
  {k:'dictionary',label:'Dictionary',page:'dictionary',hint:'Approve scan-grown pending terms/tags — only governed vocabulary reaches the Registry'},
  {k:'govern',label:'Govern',page:'govern',hint:'Stewardship + export the glossary'},
  {k:'apply',label:'Resolve',page:'apply',hint:'Resolve term IDs & apply to PDC'}];
let GENERATED=false, APPLIED=false, CUR_PAGE='home';
let LAST_REGISTRY=null, GLOSSARY_SAVED=false;
function renderReady(){
  const card=$('readyCard'); if(!card) return;
  if(!GENERATED && !GLOSSARY_SAVED){ card.style.display='none'; return; }
  card.style.display='';
  const line=(ok,txt)=>`<div><span style="color:${ok?'#16a34a':'#9ca3af'};font-weight:800">${ok?'\u2713':'\u25CB'}</span> ${txt}</div>`;
  const regOk=!!LAST_REGISTRY;
  $('readyList').innerHTML =
    line(GLOSSARY_SAVED, GLOSSARY_SAVED?`Glossary saved${CUR_GLOSS&&CUR_GLOSS.name?` as <b>${esc(CUR_GLOSS.name)}</b>`:''} — reloadable for review`:'Glossary not saved yet (optional — <b>Save glossary</b> on the Glossary page to reload later)')
    + line(GENERATED, GENERATED?'Glossary JSONL generated — import it in PDC (Business Glossary \u2192 Import)':'Glossary JSONL not generated yet')
    + line(regOk, regOk?`Registry written: <code>${esc(LAST_REGISTRY)}</code>`:'Registry not written (generate the glossary to author it)');
  $('readyHint').innerHTML = (GENERATED&&regOk)
    ? 'The <b>Registry</b> is the hand-off artifact. Point the <b>Policy Generator</b> at it to build the Data Identification policy — its Assign-Tags are held to this glossary\u2019s governed vocabulary. Term ids fill in after you import the glossary and run <b>Resolve Term IDs</b>.'
    : 'Generate the glossary to author the Registry the Policy Generator reads.';
}
function flowState(){
  const conns=(typeof CONNS!=='undefined'&&CONNS)?CONNS.length:0;
  const governed=ROWS.length>0 && PEOPLE_LOADED && !!($('g_steward')&&$('g_steward').value);
  // Dictionary is "done" once we've scanned and the pending queue is clear. Until the
  // dictionary has been loaded at least once (TAGDICT null) we can't know — show not-done.
  const dictDone=ROWS.length>0 && (typeof TAGDICT!=='undefined') && !!TAGDICT &&
    (((TAGDICT.pending_tags||0)+(TAGDICT.pending_terms||0))===0);
  return {connect:conns>0||ROWS.length>0, review:ROWS.length>0, dictionary:dictDone, govern:governed, apply:APPLIED};
}
function activeStage(p){ return ({connections:'connect',schema:'connect',files:'connect',glossary:'review',dictionary:'dictionary',govern:'govern',apply:'apply'})[p]||''; }
function renderStepper(){
  const f=$('flow'); if(!f) return;
  const st=flowState(), act=activeStage(CUR_PAGE);
  f.innerHTML=FLOW.map((s,i)=>{
    const active=(s.k===act), done=st[s.k];
    const cls='fstep'+(active?' active':(done?' done':''));
    const mark=(done&&!active)?'\u2713':(i+1);
    return (i?'<span class="fsep">\u203a</span>':'')+`<button class="${cls}" onclick="showPage('${s.page}')" title="${s.hint||('Go to '+s.label)}"><span class="fn">${mark}</span>${s.label}</button>`;
  }).join('');
}
