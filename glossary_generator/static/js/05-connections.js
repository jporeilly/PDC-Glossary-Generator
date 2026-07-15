/* 05-connections.js — extracted from templates/index.html. Plain scripts, loaded in
   numbered order; they share one global scope, so load order matters. */
/* ---------- connections ---------- */
function connTypeFields(){
  const t=$('c_type').value;
  $('cf_db').style.display=t==='db'?'':'none';
  $('cf_minio').style.display=t==='minio'?'':'none';
  $('cf_ddl').style.display=t==='ddl'?'':'none';
}
function syncS3Scheme(from){
  // The endpoint URL's scheme is what boto3 actually uses — an explicit https://
  // beats the TLS tick. Keep the two in lockstep so they can't disagree:
  // typing a scheme sets the tick; toggling the tick rewrites the scheme.
  const ep=$('c_endpoint'), sec=$('c_secure'); if(!ep||!sec) return;
  const v=(ep.value||'').trim();
  if(from==='endpoint'){
    if(/^https:\/\//i.test(v)) sec.checked=true;
    else if(/^http:\/\//i.test(v)) sec.checked=false;
  }else if(/^https?:\/\//i.test(v)){
    ep.value=v.replace(/^https?:\/\//i, sec.checked?'https://':'http://');
  }
}
function formConfig(){
  const t=$('c_type').value;
  if(t==='db') return {engine:$('c_engine').value,host:$('c_host').value,port:$('c_port').value,database:$('c_database').value,schema:$('c_schema').value,user:$('c_user').value,password:$('c_password').value,ssl:$('c_ssl').checked,profile:$('c_profile').checked};
  if(t==='minio') return {endpoint:$('c_endpoint').value,bucket:$('c_bucket').value,access_key:$('c_access').value,secret_key:$('c_secret').value,prefix:$('c_prefix').value,secure:$('c_secure').checked,level:($('c_filelevel')&&$('c_filelevel').checked)?'file':'folder',profile_dq:!!($('c_dq')&&$('c_dq').checked)};
  return {path:$('c_path').value};
}
async function saveConnection(){
  const name=$('c_name').value.trim(); if(!name){ $('connFormMsg').textContent='Name required'; return; }
  const c={id:editId, name, type:$('c_type').value, config:formConfig()};
  const d=await (await fetch('/api/connections',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(c)})).json();
  CONNS=d.connections; renderConns(); resetConnForm(); $('connFormMsg').textContent='Saved.';
}
function resetConnForm(){
  editId=null; $('connFormTitle').textContent='New connection'; $('connCancelBtn').style.display='none';
  $('c_name').value=''; $('c_password').value=''; $('c_secret').value=''; $('connFormMsg').textContent='';
}
function editConn(id){
  const c=CONNS.find(x=>x.id===id); if(!c)return; editId=id;
  $('connFormTitle').textContent='Edit: '+c.name; $('connCancelBtn').style.display='';
  $('c_name').value=c.name; $('c_type').value=c.type; connTypeFields();
  const f=c.config||{};
  if(c.type==='db'){ $('c_engine').value=f.engine||'postgresql'; $('c_host').value=f.host||''; $('c_port').value=f.port||''; $('c_database').value=f.database||''; $('c_schema').value=f.schema||''; $('c_user').value=f.user||''; $('c_password').value=f.password||''; $('c_ssl').checked=!!f.ssl; $('c_profile').checked=f.profile!==false; }
  else if(c.type==='minio'){ $('c_endpoint').value=f.endpoint||''; $('c_bucket').value=f.bucket||''; $('c_access').value=f.access_key||''; $('c_secret').value=f.secret_key||''; $('c_prefix').value=f.prefix||''; $('c_secure').checked=!!f.secure; if($('c_filelevel'))$('c_filelevel').checked=(f.level!=='folder'); if($('c_dq'))$('c_dq').checked=!!f.profile_dq; syncS3Scheme('endpoint'); }
  else $('c_path').value=f.path||'';
  window.scrollTo({top:0,behavior:'smooth'});
}
async function delConn(id){
  const c=CONNS.find(x=>x.id===id);
  if(!confirm(`Delete connection "${c?c.name:id}"? This removes it from the app only — nothing in PDC is touched.`)) return;
  const d=await (await fetch('/api/connections/'+id,{method:'DELETE'})).json();
  CONNS=d.connections; renderConns();
}
async function loadConnections(){
  try{ CONNS=(await (await fetch('/api/connections')).json()).connections||[]; }catch(e){ CONNS=[]; }
  renderConns();
}
function connDetail(c){
  const f=c.config||{};
  if(c.type==='db') return `${f.engine} · ${f.host}:${f.port}/${f.database} · ${f.user}`;
  if(c.type==='minio') return `${f.endpoint}/${f.bucket}${f.prefix?'/'+f.prefix:''}`;
  return f.path||'';
}
function renderConns(){
  if(!CONNS.length){ $('conncards').innerHTML='<div class="note" style="padding:8px">No saved connections yet. Add one above.</div>'; return; }
  const ty={db:'Database',minio:'Document store',ddl:'DDL file'};
  $('conncards').innerHTML=CONNS.map(c=>`
    <div class="conncard">
      <div class="ct"><span class="nm">${esc(c.name)}</span><span class="ty ty-${c.type}">${ty[c.type]||c.type}</span></div>
      <div class="det">${esc(connDetail(c))}</div>
      <div class="acts">
        <button class="primary sm" onclick="scanConn('${c.id}','replace')">Scan</button>
        <button class="ghost sm" onclick="scanConn('${c.id}','add')">Add to glossary</button>
        ${c.type==='db'?`<button class="ghost sm" onclick="discoverConn('${c.id}')">Discover</button><button class="ghost sm" onclick="seedConn('${c.id}')" title="Populate empty/all tables with realistic sample data (writes rows).">Seed data</button>`:''}
        ${c.type==='minio'?`<button class="ghost sm" onclick="discoverDocs('${c.id}')" title="Profile the bucket: file counts, sizes, types and folders.">Discover</button>`:''}
        <button class="ghost sm" onclick="testConn('${c.id}')">Test</button>
        <button class="ghost sm" onclick="editConn('${c.id}')">Edit</button>
        <button class="danger sm" onclick="delConn('${c.id}')">Delete</button>
      </div>
      <div class="st msg" id="st-${c.id}"></div>
      <div id="chk-${c.id}"></div>
    </div>`).join('');
}
function scanBody(c){
  if(c.type==='db') return {source:'db', conn:c.config};
  if(c.type==='minio') return {source:'minio', minio:c.config};
  return {source:'ddl', ddl_path:(c.config||{}).path};
}
async function testConn(id){
  const c=CONNS.find(x=>x.id===id); const el=$('st-'+id); el.textContent='Testing…';
  try{
    let d;
    if(c.type==='minio') d=await (await fetch('/api/test-minio',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({minio:c.config})})).json();
    else if(c.type==='db') d=await (await fetch('/api/test-connection',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({conn:c.config})})).json();
    else { el.textContent='DDL file — scan to validate.'; return; }
    el.textContent=(d.ok?'✓ ':'✗ ')+(d.message||'')+(d.server_version?(' — '+d.server_version):'')+(d.objects!=null?(' · '+d.objects+'+ obj'):'');
    el.style.color=d.ok?'#3C7A57':'#B23A48';
  }catch(e){ el.textContent='✗ '+e; }
}
function testForm(){
  const c={type:$('c_type').value,config:formConfig()}; const m=$('connFormMsg'); m.textContent='Testing…';
  const ep=c.type==='minio'?'/api/test-minio':(c.type==='db'?'/api/test-connection':null);
  if(!ep){ m.textContent='DDL — scan to validate.'; return; }
  const key=c.type==='minio'?'minio':'conn';
  fetch(ep,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({[key]:c.config})}).then(r=>r.json()).then(d=>{
    m.textContent=(d.ok?'✓ ':'✗ ')+(d.message||'')+(d.server_version?(' — '+d.server_version):''); });
}
async function discoverConn(id){
  const c=CONNS.find(x=>x.id===id); if(!c)return; const el=$('st-'+id); el.textContent='Profiling data…';
  try{
    const d=await (await fetch('/api/discover',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({conn:c.config})})).json();
    if(d.error){ el.textContent=d.error; return; }
    renderDiscoveryPanel(d); el.textContent=`Profiled ${d.summary.tables} tables.`;
    $('discpanel').scrollIntoView({behavior:'smooth'});
  }catch(e){ el.textContent='Discover failed: '+e; }
}
function pct(x){ return Math.round((x||0)*100)+'%'; }
function renderDiscoveryPanel(d){
  const s=d.summary;
  $('discpMeta').textContent='— schema '+d.schema;
  const cards=[
    ['Tables',s.tables],['Columns',s.columns],['Total rows',(s.rows||0).toLocaleString()],
    ['Database size',fmtBytes(s.db_bytes||0)],['PII columns',s.pii],['CDE columns',s.cde],
    ['Classified',s.classified!=null?s.classified:'—'],['Avg complete',s.avg_completeness!=null?pct(s.avg_completeness):'—'],
    ['Keys (PK·FK)',`${s.pk_cols||0}·${s.fk_cols||0}`],['Empty tables',s.empty]
  ];
  $('discStats').innerHTML=cards.map(([l,v])=>`<div class="statcard"><div class="v">${v}</div><div class="l">${l}</div></div>`).join('');
  const sev=s.sensitivity||{};
  let sub=`<b>Sensitivity:</b> <span style="color:#B23A48">HIGH ${sev.HIGH||0}</span> · <span style="color:#C25E00">MEDIUM ${sev.MEDIUM||0}</span> · <span style="color:#1C7293">LOW ${sev.LOW||0}</span>`;
  if(s.largest_tables&&s.largest_tables.length)
    sub+=` &nbsp;|&nbsp; <b>Largest:</b> `+s.largest_tables.slice(0,4).map(t=>`${esc(t.name)} (${(t.rows||0).toLocaleString()} rows, ${fmtBytes(t.bytes||0)})`).join(' · ');
  $('discSub').innerHTML=sub;
  const sevColor={HIGH:'#B23A48',MEDIUM:'#C25E00',LOW:'#1C7293'};
  const kindBadge=k=>k?`<span class="kind">${esc(k)}</span>`:'';
  $('discTables').innerHTML=d.tables.map((t,ti)=>`
    <div class="ptbl-wrap">
      <div class="ptbl-hd" onclick="var e=document.getElementById('pt${ti}');e.style.display=e.style.display==='none'?'':'none'">
        <span>${esc(t.name)}</span>${t.empty?'<span class="empty-badge">EMPTY — needs data</span>':''}
        <span class="rc">${(t.rows||0).toLocaleString()} rows · ${t.columns.length} cols${t.bytes?' · '+fmtBytes(t.bytes):''}</span>
      </div>
      <div id="pt${ti}" style="overflow:auto">
        <table class="ptbl">
          <thead><tr><th>Column</th><th>Type</th><th>Complete</th><th>Distinct</th><th>Unique</th><th>Sensitivity</th><th>PII</th><th>CDE</th><th>Detected</th><th>Examples</th></tr></thead>
          <tbody>${t.columns.map(c=>`<tr>
            <td><b>${esc(c.column)}</b>${c.pk?'<span class="pkfk">PK</span>':''}${c.fk?'<span class="pkfk">FK</span>':''}</td>
            <td><code>${esc(c.type)}</code></td>
            <td><span class="mini"><i style="width:${pct(c.completeness)}"></i></span>${pct(c.completeness)}</td>
            <td>${(c.distinct||0).toLocaleString()}</td>
            <td>${pct(c.uniqueness)}</td>
            <td><b style="color:${sevColor[c.sensitivity]||'inherit'}">${c.sensitivity}</b></td>
            <td>${c.pii?`<span class="kind">${esc(c.pii)}</span>`:'—'}</td>
            <td>${c.cde==='Yes'?'✓':'—'}</td>
            <td>${kindBadge(c.kind)}</td>
            <td><code>${esc((c.examples||[]).join(', '))||'—'}</code></td>
          </tr>`).join('')}</tbody>
        </table>
      </div>
    </div>`).join('');
  $('discpanel').style.display='';
  LAST_DISCOVERY=d;
}
let DOC_CONN_ID=null;
async function discoverDocs(id){
  const c=CONNS.find(x=>x.id===id); if(!c)return; const el=$('st-'+id); el.textContent='Scanning bucket…';
  DOC_CONN_ID=id;
  const cfg=Object.assign({}, c.config,
    {include:($('docInclude')&&$('docInclude').value.trim())||'',
     exclude:($('docExclude')&&$('docExclude').value.trim())||''});
  try{
    const d=await (await fetch('/api/discover-docs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({conn:cfg})})).json();
    if(d.error){ el.textContent=d.error; return; }
    renderDocPanel(d); el.textContent=`Scanned ${d.summary.files.toLocaleString()} files.`;
    $('docpanel').scrollIntoView({behavior:'smooth'});
  }catch(e){ el.textContent='Discover failed: '+e; }
}
// Re-run discovery on the same bucket with the current include/exclude patterns.
function reDiscoverDocs(){
  if(!DOC_CONN_ID){ return; }
  discoverDocs(DOC_CONN_ID);
}
// ---- Files-by-type chart: vertical colored bars, one colour per extension ----
const EXT_COLORS={docx:'#93B3EB',doc:'#93B3EB',rtf:'#CE6B6B',pdf:'#E9A23C',csv:'#5FBF99',
  tsv:'#5FBF99',psv:'#5FBF99',json:'#5E6699',jsonl:'#5E6699',avro:'#5E6699',txt:'#CE6B6B',
  xml:'#C58BD0',parquet:'#7FB069',orc:'#7FB069',xlsx:'#4FB0AE',xls:'#4FB0AE'};
const CHART_FALLBACK=['#93B3EB','#E9A23C','#5FBF99','#5E6699','#CE6B6B','#C58BD0','#7FB069',
  '#4FB0AE','#E0B341','#9A8CCB','#6FB1D6','#D98E5A'];
function typeColors(byType){
  const used=new Set(), map={}; let fi=0;
  byType.forEach(t=>{ const e=(t.ext||'').toLowerCase();
    if(EXT_COLORS[e]){ map[e]=EXT_COLORS[e]; used.add(EXT_COLORS[e]); }});
  byType.forEach(t=>{ const e=(t.ext||'').toLowerCase();
    if(map[e])return;
    while(fi<CHART_FALLBACK.length-1 && used.has(CHART_FALLBACK[fi])) fi++;
    map[e]=CHART_FALLBACK[fi]; used.add(CHART_FALLBACK[fi]); fi++; });
  return map;
}
function chartTicks(max){
  let step;
  if(max<=8) step=1;
  else { let s=Math.ceil(max/5); const pow=Math.pow(10,Math.floor(Math.log10(s))); const n=s/pow;
         step=(n<=1?1:n<=2?2:n<=5?5:10)*pow; }
  const top=Math.max(step,Math.ceil(max/step)*step); const out=[];
  for(let v=0; v<=top; v+=step) out.push(v);
  return {top,out};
}
function fileTypeChart(byType){
  if(!byType||!byType.length) return '<div class="msg">none</div>';
  const colors=typeColors(byType);
  const max=Math.max(1,...byType.map(t=>t.count));
  const tk=chartTicks(max), top=tk.out[tk.out.length-1]||1;
  const W=440,H=235,L=34,R=14,T=12,Bm=20;
  const x0=L,x1=W-R,y0=T,y1=H-Bm,pw=x1-x0,ph=y1-y0;
  let grid='';
  tk.out.forEach(v=>{ const y=y1-(v/top)*ph;
    grid+=`<line x1="${x0}" y1="${y.toFixed(1)}" x2="${x1}" y2="${y.toFixed(1)}" stroke="#E8EEF2"/>`;
    grid+=`<text x="${x0-7}" y="${(y+3.6).toFixed(1)}" text-anchor="end" font-size="11" fill="#94A3B8">${v}</text>`;
  });
  const n=byType.length, slot=pw/n, bw=Math.min(56,slot*0.6);
  const bars=byType.map((t,i)=>{ const e=(t.ext||'').toLowerCase();
    const cx=x0+slot*(i+0.5), h=(t.count/top)*ph, x=cx-bw/2, y=y1-h;
    return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(0,h).toFixed(1)}" rx="3" fill="${colors[e]||'#93B3EB'}"><title>${esc(t.ext)}: ${t.count.toLocaleString()} file(s) · ${fmtBytes(t.bytes)}</title></rect>`;
  }).join('');
  const legend=byType.map(t=>{ const e=(t.ext||'').toLowerCase();
    return `<span class="lg"><i style="background:${colors[e]||'#93B3EB'}"></i>${esc(t.ext)}</span>`;}).join('');
  return `<div class="ftlegend">${legend}</div>
    <svg viewBox="0 0 ${W} ${H}" width="100%" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Files by type">
      ${grid}
      <line x1="${x0}" y1="${y1}" x2="${x1}" y2="${y1}" stroke="#CBD5E1"/>
      ${bars}
    </svg>`;
}
function renderDocPanel(d){
  const s=d.summary;
  $('docpMeta').textContent='— bucket '+d.bucket+(d.prefix?(' / '+d.prefix):'');
  // sync the filter inputs with what the backend actually applied, and report drops
  if($('docInclude')) $('docInclude').value=d.include||'';
  if($('docExclude')) $('docExclude').value=d.exclude||'';
  if($('docFilterNote')){
    const f=s.filtered||0;
    $('docFilterNote').textContent=f?`${f.toLocaleString()} object(s) filtered out`:'No filter applied';
  }
  $('docStats').innerHTML=[
    ['Files',(s.files||0).toLocaleString()],['Total size',fmtBytes(s.bytes||0)],
    ['File types',s.types],['Folders',s.folders],['Avg size',fmtBytes(s.avg_bytes||0)]
  ].map(([l,v])=>`<div class="statcard"><div class="v">${v}</div><div class="l">${l}</div></div>`).join('');
  const bar=(n,max)=>`<span class="mini"><i style="width:${max?Math.round(n/max*100):0}%"></i></span>`;
  const fmax=Math.max(1,...d.by_folder.map(f=>f.bytes));
  const folderRows=d.by_folder.map(f=>`<tr><td><b>${esc(f.name)}</b></td><td>${f.count.toLocaleString()}</td><td>${bar(f.bytes,fmax)}</td><td>${fmtBytes(f.bytes)}</td></tr>`).join('');
  const largeRows=d.largest.map(o=>`<tr><td class="kcell" title="${esc(o.key)}"><code>${esc(o.key)}</code></td><td class="szcell">${fmtBytes(o.bytes)}</td></tr>`).join('');
  const newRows=d.newest.map(o=>`<tr><td class="kcell" title="${esc(o.key)}"><code>${esc(o.key)}</code></td><td class="szcell">${esc((o.modified||'').slice(0,10))}</td></tr>`).join('');
  $('docBody').innerHTML=`
    <div class="docgrid">
      <div><h4 class="dh">By file type</h4><div class="ftchart">${fileTypeChart(d.by_type)}</div></div>
      <div><h4 class="dh">By folder</h4><table class="ptbl"><thead><tr><th>Folder</th><th>Files</th><th></th><th>Size</th></tr></thead><tbody>${folderRows||'<tr><td colspan=4 class="msg">none</td></tr>'}</tbody></table></div>
      <div><h4 class="dh">Largest objects</h4><table class="ptbl objtbl"><tbody>${largeRows||'<tr><td class="msg">none</td></tr>'}</tbody></table></div>
      <div><h4 class="dh">Most recent</h4><table class="ptbl objtbl"><tbody>${newRows||'<tr><td class="msg">none</td></tr>'}</tbody></table></div>
    </div>`;
  $('docpanel').style.display='';
}
async function seedConn(id){
  const c=CONNS.find(x=>x.id===id); if(!c)return; const el=$('st-'+id);
  if(!confirm('Seed realistic sample data into this database? This writes rows to empty/under-filled tables.'))return;
  el.textContent='Seeding sample data…';
  try{
    const d=await (await fetch('/api/seed',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({conn:c.config,rows:200})})).json();
    if(d.error){ el.textContent=d.error; return; }
    el.textContent=`Seeded: ${(d.inserted||[]).map(x=>x.table+' +'+x.rows).join(', ')||'nothing (already populated)'}.`;
    discoverConn(id);
  }catch(e){ el.textContent='Seed failed: '+e; }
}
async function scanConn(id, mode){
  const c=CONNS.find(x=>x.id===id); if(!c)return;
  if(c.type==='db') _lastDbConn=c.config;
  const adding=mode==='add'&&ROWS.length>0; const el=$('st-'+id);
  el.textContent=adding?'Scanning to add…':'Scanning…';
  try{
    const d=await (await fetch('/api/scan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(scanBody(c))})).json();
    if(d.error){ el.textContent=d.error; return; }
    if(adding){
      const have=new Set(ROWS.map(x=>x.Category+'|'+(x.Term||'').toLowerCase())); let a=0,dup=0;
      (d.rows||[]).forEach(nr=>{ const k=nr.Category+'|'+(nr.Term||'').toLowerCase(); if(have.has(k)){dup++;return;} have.add(k); ROWS.push(nr); a++; });
      el.textContent=`Added ${a} term(s)${dup?` (${dup} dup)`:''}.`;
      buildCategoryFilter(); applyFilter();
    } else {
      ROWS=d.rows; buildCategoryFilter(); clearFilters(); snapshotScan(); el.textContent=`Scanned — ${ROWS.length} terms.`;
    }
    renderSummary(computeStats(ROWS), adding?null:d.scanned); renderOwnership(d.ownership);
    const chkEl=$('chk-'+id); if(chkEl) chkEl.innerHTML = (adding?'':renderCheck(d.check));
    if(PEOPLE_LOADED) buildCatTable();
    $('enhanceBtn').disabled=!ROWS.length; $('saveGlossBtn').disabled=!ROWS.length; $('filterbar').style.display=''; $('keepbar').style.display='';
    $('glossHint').textContent=''; renderDiscovery(adding?null:d.scanned); llmStatus();
  }catch(e){ el.textContent='Scan failed: '+e; }
}

/* ---------- harvest from PDC (read the catalog the customer already built) ---------- */
function _hvBody(){
  let base=$('hv_base').value.trim();
  if(!base && window.SETTINGS) base=(SETTINGS.pdc_base||'').trim();
  return {base_url:base, username:$('hv_user').value, password:$('hv_pass').value,
          token:($('hv_token')?$('hv_token').value.trim():''),
          version:($('hv_ver').value||'v2').trim(),
          realm:'pdc', verify_tls:$('hv_verify').checked};
}
let HV_SOURCES=[], HV_SEL=new Set();
function _hvMatch(s,q){ return !q || (`${s.name||''} ${s.type||''} ${s.fqdn||''}`.toLowerCase().includes(q)); }
function hvKey(s){ return s.fqdn||s.id; }
async function hvListSources(){
  const b=_hvBody();
  if(!b.base_url){ $('hvMsg').textContent='Enter your PDC base URL.'; return; }
  if(!(b.token || (b.username&&b.password))){ $('hvMsg').textContent='Enter a PDC username and password, or paste a bearer token.'; return; }
  $('hvMsg').textContent='Reading PDC catalog for sources…'; $('hvListBtn').disabled=true;
  try{
    const d=await (await fetch('/api/pdc/data-sources',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)})).json();
    if(d.error){ $('hvMsg').textContent=d.error; return; }
    HV_SOURCES=(d.data_sources||[]); HV_SEL=new Set(); if($('hv_all'))$('hv_all').checked=false; if($('hv_search'))$('hv_search').value='';
    $('hvSourceRow').style.display=(d.count>0)?'':'none';
    hvRenderSources();
    $('hvMsg').textContent=d.count?`PDC has ${d.count} schema/source(s). Filter, tick the ones you want, and harvest — no re-created connections, no secrets.`:'PDC returned no schemas — has the source been scanned/ingested? (An ingest that reported OK but found no tables leaves nothing to harvest.)';
  }catch(e){ $('hvMsg').textContent='Could not read the catalog: '+e; }
  finally{ $('hvListBtn').disabled=false; }
}
function hvRenderSources(){
  const q=($('hv_search')?$('hv_search').value:'').toLowerCase().trim();
  const list=HV_SOURCES.filter(s=>_hvMatch(s,q)), el=$('hvSourceList'); if(!el) return;
  el.innerHTML=list.map((s,i)=>{ const k=hvKey(s), on=HV_SEL.has(k), ek=encodeURIComponent(k), sid='hvst'+i;
    return `<div style="border-bottom:1px solid #eef3f5;padding:6px 10px;font-size:13px">
      <div style="display:flex;align-items:center;gap:8px">
        <input type="checkbox" ${on?'checked':''} onchange="hvPick('${ek}',this.checked)"/>
        <span style="flex:1;word-break:break-word"><b>${esc(s.name||s.id||'(unnamed source)')}</b>${s.type?` <span style="color:var(--mute);font-size:11px">${esc(s.type)}</span>`:''}</span>
        ${s.fqdn?`<span style="color:var(--mute);font-size:11px;word-break:break-all;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(s.fqdn)}">${esc(s.fqdn)}</span>`:''}
        <button class="ghost sm" title="Read-only: what has PDC actually ingested for this source?" onclick="hvTestSource('${ek}','${sid}')">Test</button>
        ${(!s.type||String(s.type).toUpperCase()==='RESOURCE')?`<button class="ghost sm" title="Save this PDC source as an app connection for a direct live scan — prefills everything except the secret" onclick="hvToConn('${ek}','${sid}')">&rarr; Connection</button>`:''}
        <button class="ghost sm" title="Add this source's terms to the glossary" onclick="hvHarvestOne('${ek}','${sid}')">Harvest</button>
      </div>
      <div id="${sid}" style="font-size:11.5px;color:var(--mute);margin:3px 0 0 26px"></div>
    </div>`; }).join('')||'<p class="msg" style="padding:8px">No sources match that filter.</p>';
  if($('hvCount'))$('hvCount').textContent=`${list.length} of ${HV_SOURCES.length} shown`;
  hvSelCount();
}
async function hvTestSource(ek,sid){
  const k=decodeURIComponent(ek), s=HV_SOURCES.find(x=>hvKey(x)===k); if(!s) return;
  const st=$(sid), b=_hvBody(); b.data_source_id=s.fqdn||s.id; b.data_source_name=s.name||s.id;
  if(st){ st.style.color='var(--mute)'; st.textContent='Testing…'; }
  try{
    const d=await (await fetch('/api/pdc/source-test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)})).json();
    if(st){ st.style.color=d.ok?'#1B6B45':'#b4232a'; st.textContent=(d.ok?'✓ ':'⚠ ')+(d.message||d.error||'no response'); }
  }catch(e){ if(st){ st.style.color='#b4232a'; st.textContent='Test failed: '+e; } }
}
function hvScanCard(ps){
  // One line of PDC's own scan & discovery results for a harvested source:
  // ingest (tables/columns/files), Data Identification (sensitivity dist),
  // Trust Score coverage, term links, tags. All read-only, from the harvest call.
  if(!ps) return '';
  const dist=ps.sens_dist||{}, dorder=['HIGH','MEDIUM','LOW'];
  const dtxt=Object.keys(dist).length
    ? ' ('+dorder.filter(k=>dist[k]).map(k=>`${k[0]}:${dist[k]}`).concat(
        Object.keys(dist).filter(k=>!dorder.includes(k)).map(k=>`${k}:${dist[k]}`)).join(' ')+')'
    : '';
  const ent = ps.columns ? `${ps.tables} table(s) · ${ps.columns} column(s)` : `${ps.files} file(s)`;
  const total = ps.columns || ps.files || 0;
  return `<div style="border:1px solid var(--line);border-radius:8px;padding:6px 10px;margin-top:4px;font-size:12px">
    <b>${esc(ps.source||'')}</b> — PDC scan &amp; discovery results:
    ingested <b>${ent}</b> ·
    identified <b>${ps.identified||0}</b>/${total}${esc(dtxt)} ·
    trust-scored <b>${ps.trust_scored||0}</b> ·
    term-linked <b>${ps.term_linked||0}</b> ·
    tagged <b>${ps.tagged||0}</b>
    ${(!ps.identified&&total)?'<span class="hint"> — 0 identified usually means Profiling / Data Identification hasn\u2019t run on this source in PDC yet</span>':''}
  </div>`;
}
async function hvToConn(ek,sid){
  // PDC source -> saved app connection. The public API never returns a usable
  // password/secret, so the record prefills everything else and the user sets the
  // secret once on Connections. Re-adding an existing connection keeps its secret.
  const k=decodeURIComponent(ek), s=HV_SOURCES.find(x=>hvKey(x)===k); if(!s) return;
  // Look up by NAME: the picker's id is a catalog-entity UUID, but the
  // data-sources filter's ids field expects PDC's internal ObjectId (500 otherwise).
  const st=$(sid), b=_hvBody(); b.data_source_name=s.name||s.id;
  if(st){ st.style.color='var(--mute)'; st.textContent='Reading the PDC record…'; }
  try{
    const d=await (await fetch('/api/pdc/source-to-connection',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)})).json();
    if(d.error){ if(st){ st.style.color='#b4232a'; st.textContent=d.error; } return; }
    if(typeof loadConnections==='function') loadConnections();
    const bits=[`✓ ${d.updated?'updated':'saved'} as app connection <b>${esc(d.connection.name)}</b>`];
    if(d.kept_secret) bits.push('kept your saved secret');
    else if(d.needs) bits.push(`set the <b>${esc(d.needs)}</b> on <a href="#" onclick="showPage('connections');return false">Connections</a> — or import your loader CSV there (Bulk loader &rarr; Import), which carries the credentials`);
    if(d.warning) bits.push(`<span style="color:#7a4a00">${esc(d.warning)}</span>`);
    if(st){ st.style.color='#1B6B45'; st.innerHTML=bits.join(' · '); }
  }catch(e){ if(st){ st.style.color='#b4232a'; st.textContent='Failed: '+e; } }
}
async function hvHarvestOne(ek,sid){
  const k=decodeURIComponent(ek), s=HV_SOURCES.find(x=>hvKey(x)===k); if(!s) return;
  const st=$(sid), b=_hvBody(); b.data_source_id=s.fqdn||s.id; b.data_source_name=s.name||s.id;
  const firstLoad=ROWS.length===0;
  if(st){ st.style.color='var(--mute)'; st.textContent='Harvesting…'; }
  try{
    const d=await (await fetch('/api/pdc/harvest',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)})).json();
    if(d.error){ if(st){ st.style.color='#b4232a'; st.textContent=d.error; } return; }
    if(d.pdc_summary && $('hvResults')) $('hvResults').innerHTML=hvScanCard(d.pdc_summary);
    const have=new Set(ROWS.map(x=>x.Category+'|'+(x.Term||'').toLowerCase())); let a=0;
    (d.rows||[]).forEach(nr=>{ const kk=nr.Category+'|'+(nr.Term||'').toLowerCase(); if(have.has(kk))return; have.add(kk); ROWS.push(nr); a++; });
    if(ROWS.length){ buildCategoryFilter(); if(firstLoad){ clearFilters(); snapshotScan(); } else applyFilter();
      renderSummary(computeStats(ROWS), null); if(PEOPLE_LOADED) buildCatTable();
      $('enhanceBtn').disabled=!ROWS.length; $('saveGlossBtn').disabled=!ROWS.length;
      $('filterbar').style.display=''; $('keepbar').style.display=''; $('glossHint').textContent=''; llmStatus(); }
    const govN=(d.scanned&&d.scanned.already_governed)||0;
    if(st){ st.style.color='#1B6B45'; st.innerHTML=`✓ added <b>${a}</b> term(s)${govN?` · ${govN} already governed`:''} · <a href="#" onclick="showPage('glossary');return false">review &rarr;</a>`; }
  }catch(e){ if(st){ st.style.color='#b4232a'; st.textContent='Harvest failed: '+e; } }
}
function hvPick(k,on){ k=decodeURIComponent(k); if(on)HV_SEL.add(k); else HV_SEL.delete(k); hvSelCount(); }
function hvToggleAll(on){ const q=($('hv_search')?$('hv_search').value:'').toLowerCase().trim();
  HV_SOURCES.filter(s=>_hvMatch(s,q)).forEach(s=>{ const k=hvKey(s); if(on)HV_SEL.add(k); else HV_SEL.delete(k); });
  hvRenderSources(); }
function hvSelCount(){ if($('hvSelCount'))$('hvSelCount').textContent=HV_SEL.size?`${HV_SEL.size} selected`:'none selected'; }
async function hvHarvest(){
  if(!HV_SEL.size){ $('hvMsg').textContent='Tick one or more sources to harvest.'; return; }
  const chosen=HV_SOURCES.filter(s=>HV_SEL.has(hvKey(s)));
  const firstLoad=ROWS.length===0; let added=0, gov=0, done=0; const failed=[], cards=[];
  $('hvHarvestBtn').disabled=true;
  for(const s of chosen){
    const b=_hvBody(); b.data_source_id=s.fqdn||s.id; b.data_source_name=s.name||s.id;
    $('hvMsg').textContent=`Harvesting “${b.data_source_name}” (${done+1}/${chosen.length})…`;
    try{
      const d=await (await fetch('/api/pdc/harvest',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)})).json();
      if(d.error){ failed.push(`${b.data_source_name}: ${d.error}`); done++; continue; }
      if(d.pdc_summary) cards.push(hvScanCard(d.pdc_summary));
      const have=new Set(ROWS.map(x=>x.Category+'|'+(x.Term||'').toLowerCase()));
      (d.rows||[]).forEach(nr=>{ const k=nr.Category+'|'+(nr.Term||'').toLowerCase(); if(have.has(k))return; have.add(k); ROWS.push(nr); added++; });
      gov+=(d.scanned&&d.scanned.already_governed)||0;
    }catch(e){ failed.push(`${s.name||s.id}: ${e}`); }
    done++;
  }
  if(ROWS.length){ buildCategoryFilter(); if(firstLoad){ clearFilters(); snapshotScan(); } else applyFilter();
    renderSummary(computeStats(ROWS), null); if(PEOPLE_LOADED) buildCatTable();
    $('enhanceBtn').disabled=!ROWS.length; $('saveGlossBtn').disabled=!ROWS.length;
    $('filterbar').style.display=''; $('keepbar').style.display=''; $('glossHint').textContent=''; llmStatus(); }
  $('hvHarvestBtn').disabled=false;
  if($('hvResults')) $('hvResults').innerHTML=cards.join('');
  $('hvMsg').innerHTML=`Harvested <b>${added}</b> new term(s) from <b>${chosen.length-failed.length}</b> source(s)${gov?` · <b>${gov}</b> already governed in PDC`:''}.`+
    (failed.length?` <span style="color:#b4232a">${failed.length} failed:</span> ${esc(failed.join('; ').slice(0,300))}`:'')+
    ` <a href="#" onclick="showPage('glossary');return false">Review in Glossary &rarr;</a>`;
}
function renderHoodHarvest(){
  const hv=(($('hv_ver')&&$('hv_ver').value.trim())||'v2');
  renderHood('hoodHarvest',{
    intro:'Harvesting reads PDC&rsquo;s catalog instead of your database. The public API has no &ldquo;list all data sources&rdquo; call, so the picker and the harvest both use <code>POST /entities/filter</code> &mdash; the same endpoint Resolve and Apply use. Every call carries <code>Authorization: Bearer &lt;token&gt;</code>; the token is minted from your username/password (or the one you paste). No database password is involved.',
    calls:[
      {verb:'POST',url:'<pdc>/keycloak/realms/pdc/protocol/openid-connect/token \u2014 mint the bearer token',headers:{'Content-Type':'application/x-www-form-urlencoded'}},
      {verb:'POST',url:'<pdc>/api/public/'+hv+'/entities/filter?extended=true \u2014 list schemas / sources for the picker',headers:{'Content-Type':'application/json','Authorization':'Bearer <token>'},open:true,
       body:JSON.stringify({filters:{types:['SCHEMA','DATA_SOURCE','RESOURCE']}},null,2)},
      {verb:'POST',url:'<pdc>/api/public/'+hv+'/entities/filter?extended=true \u2014 COLUMN entities for the chosen source',headers:{'Content-Type':'application/json','Authorization':'Bearer <token>'},
       body:JSON.stringify({filters:{types:['COLUMN']}},null,2)},
      {verb:'POST',url:'<pdc>/api/public/'+hv+'/data-sources/filter \u2014 \u2192 Connection: read the full source record (host/port/db/user \u2014 never the secret) to prefill an app connection',headers:{'Content-Type':'application/json','Authorization':'Bearer <token>'},
       body:JSON.stringify({filters:{resourceNames:['<source name>']}},null,2)}
    ],
    scripts:[{file:'pdc_api.py',note:'list_data_sources, harvest_from_catalog (reads metadata.column / attributes.features)'},
             {file:'app.py',note:'/api/pdc/data-sources, /api/pdc/harvest'},
             {file:'suggester.py',note:'suggest() turns PDC columns into candidate terms'}]
  });
}

async function checkGlossaryExists(){
  const name=($('gname').value||'').trim();
  if(!name){ $('gnameCheckMsg').textContent='Enter a glossary name first.'; return; }
  // reuse the shared PDC connection (Resolve page); fall back to the Harvest card / settings
  let b=(typeof _pdcAuthBody==='function')?_pdcAuthBody():{base_url:''};
  if(!b.base_url){
    b={base_url:($('hv_base')?$('hv_base').value.trim():'')||((window.SETTINGS&&SETTINGS.pdc_base)||''),
       username:($('hv_user')?$('hv_user').value:''), password:($('hv_pass')?$('hv_pass').value:''),
       token:'', version:'v2', realm:'pdc', verify_tls:($('hv_verify')?$('hv_verify').checked:false)};
  }
  if(!b.base_url || !(b.token || (b.username&&b.password))){
    $('gnameCheckMsg').innerHTML='Set up your PDC connection first (Resolve Term IDs page or the Harvest card).'; return; }
  b.glossary_name=name;
  $('gnameCheckMsg').textContent='Checking PDC…'; $('gnameCheckBtn').disabled=true;
  try{
    const d=await (await fetch('/api/pdc/glossary-exists',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)})).json();
    if(d.error){ $('gnameCheckMsg').textContent=d.error; return; }
    if(d.exact) $('gnameCheckMsg').innerHTML=`&#9888; A glossary named “${esc(d.name)}” already exists in PDC — importing creates a duplicate. Update it in place instead.`;
    else if(d.exists) $('gnameCheckMsg').innerHTML=`A similar glossary exists in PDC: “${esc(d.name)}”. Your name differs, so import will create a new one.`;
    else $('gnameCheckMsg').innerHTML=`&#10003; No glossary named “${esc(name)}” in PDC — import will create it fresh.`;
  }catch(e){ $('gnameCheckMsg').textContent='Check failed: '+e; }
  finally{ $('gnameCheckBtn').disabled=false; }
}
