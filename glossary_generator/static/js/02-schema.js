/* 02-schema.js — extracted from templates/index.html. Plain scripts, loaded in
   numbered order; they share one global scope, so load order matters. */
/* ---------- schema diagram ---------- */
let SCHEMA=null, SPOS={}, SVIEW={z:1,x:0,y:0}, SSEL=null, SDRAG=null, SPAN=null, TIDX={}, CIDX={};
const SCARD_W=230;
const sclamp=(v,a,b)=>Math.max(a,Math.min(b,v));

function schemaPageInit(){
  schemaStageWire();
  const sel=$('schemaConn'); if(!sel) return;
  const all=(typeof CONNS!=='undefined'?CONNS:[]);
  const opts=all.filter(c=>c.type==='db'||c.type==='ddl');
  const prev=sel.value;
  sel.innerHTML = opts.length
    ? opts.map(c=>`<option value="${esc(c.id)}">${esc(c.name||c.type)}</option>`).join('')
    : `<option value="">No database/DDL connection — add one on Connections</option>`;
  if(prev && opts.some(c=>c.id===prev)) sel.value=prev;
  // Explain the empty state: the diagram is relational-only. A document/object store
  // (S3, MinIO) has no tables, columns or foreign keys, so there is nothing to draw.
  const msg=$('schemaMsg'); const load=$('schemaLoadBtn');
  if(!opts.length){
    const hasObj=all.some(c=>c.type==='s3'||c.type==='minio'||c.type==='object');
    if(msg) msg.innerHTML = hasObj
      ? 'Your object/document store (S3/MinIO) has no relational schema to diagram. '
        + 'Add the <b>database</b> connection (e.g. <code>public</code>) on Connections to see tables &amp; keys '
        + '&mdash; or paste its <b>CREATE TABLE</b> script below. Your harvested documents are reviewed in the <b>Glossary</b>, not here.'
      : 'Add a database or DDL connection on Connections, or paste a CREATE TABLE script below, to draw a schema.';
    if(load) load.disabled=true;
  } else {
    if(msg) msg.textContent='';
    if(load) load.disabled=false;
  }
}

async function loadSchema(){
  const sel=$('schemaConn'); const id=sel&&sel.value; const c=(typeof CONNS!=='undefined'?CONNS:[]).find(x=>x.id===id);
  if(!c){ $('schemaMsg').textContent='Add a database or DDL connection on the Connections page first.'; return; }
  $('schemaMsg').textContent='Scanning schema\u2026'; $('schemaLoadBtn').disabled=true;
  try{
    const d=await (await fetch('/api/schema',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(scanBody(c))})).json();
    if(d.error){ $('schemaMsg').textContent=d.error; } else { applySchema(d); }
  }catch(e){ $('schemaMsg').textContent='Schema load failed: '+e; }
  $('schemaLoadBtn').disabled=false;
}
async function loadSchemaFromSql(){
  const sql=($('schemaDdl').value||'').trim();
  if(!sql){ $('schemaMsg').textContent='Paste a CREATE TABLE script first.'; return; }
  $('schemaMsg').textContent='Parsing SQL\u2026';
  try{
    const d=await (await fetch('/api/schema',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source:'ddl',ddl_text:sql})})).json();
    if(d.error){ $('schemaMsg').textContent=d.error; } else { applySchema(d); }
  }catch(e){ $('schemaMsg').textContent='Could not parse SQL: '+e; }
}
// ----- write PK/FK constraints to the live database -----
let KEYS_TARGET=null;
function schemaTargetConn(){ const sel=$('schemaConn'); const id=sel&&sel.value; const c=(typeof CONNS!=='undefined'?CONNS:[]).find(x=>x.id===id); return (c&&c.type==='db')?c:null; }
async function previewKeys(){
  const c=schemaTargetConn();
  if(!c){ $('schemaKeysOut').innerHTML='<div class="msg" style="color:#C25E00">Select a <b>database</b> connection in the dropdown above — that\u2019s the database the keys get written to.</div>'; return; }
  const ddl=($('schemaDdl').value||'').trim();
  const body={conn:c.config, dry_run:true}; if(ddl) body.ddl_text=ddl;
  $('schemaKeysOut').innerHTML='<div class="msg">Checking which keys are missing\u2026</div>';
  try{
    const d=await (await fetch('/api/apply-keys',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).json();
    if(d.error){ $('schemaKeysOut').innerHTML=`<div class="msg" style="color:#B23A48">${esc(d.error)}</div>`; return; }
    KEYS_TARGET=c; renderKeysPlan(d);
  }catch(e){ $('schemaKeysOut').innerHTML='<div class="msg">Failed: '+esc(String(e))+'</div>'; }
}
function keyStmtRow(s){ return `<div class="keystmt"><span class="badge-k ${s.kind}">${s.kind.toUpperCase()}</span><code title="${esc(s.sql)}">${esc(s.sql)}</code>${s.status&&s.status!=='pending'?`<span class="kstat ${s.status}">${esc(s.status)}${s.message?': '+esc(s.message):''}</span>`:''}</div>`; }
function renderKeysPlan(d){
  if(!d.pending){
    $('schemaKeysOut').innerHTML=renderCheck({title:'Keys in database',tone:'ok',
      rows:[{label:'Schema',value:d.schema},{label:'Already set',value:`${d.skipped_pk} PK \u00b7 ${d.skipped_fk} FK`}],
      issues:[],verdict:'Every key from the script is already present in the database \u2014 nothing to add.'});
    return;
  }
  const list=d.statements.map(keyStmtRow).join('');
  $('schemaKeysOut').innerHTML=renderCheck({title:'Keys to add',tone:'warn',
      rows:[{label:'Schema',value:d.schema},{label:'To add',value:`${d.pk_planned} PK \u00b7 ${d.fk_planned} FK`},{label:'Already set',value:`${d.skipped_pk} PK \u00b7 ${d.skipped_fk} FK`}],
      issues:[],verdict:'Review the statements below, then apply. This writes constraints only \u2014 no rows are changed.'})
    + `<div class="keylist">${list}</div>`
    + `<button class="primary sm" style="margin-top:8px" onclick="applyKeys()">Apply ${d.pending} change${d.pending>1?'s':''} to the database</button>`;
}
async function applyKeys(){
  const c=KEYS_TARGET||schemaTargetConn(); if(!c) return;
  const ddl=($('schemaDdl').value||'').trim();
  const body={conn:c.config, dry_run:false}; if(ddl) body.ddl_text=ddl;
  $('schemaKeysOut').innerHTML='<div class="msg">Writing constraints to the database\u2026</div>';
  try{
    const d=await (await fetch('/api/apply-keys',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).json();
    if(d.error){ $('schemaKeysOut').innerHTML=`<div class="msg" style="color:#B23A48">${esc(d.error)}</div>`; return; }
    const errs=d.statements.filter(s=>s.status==='error');
    const list=d.statements.map(keyStmtRow).join('');
    $('schemaKeysOut').innerHTML=renderCheck({title:'Keys written',tone:errs.length?'warn':'ok',
        rows:[{label:'Schema',value:d.schema},{label:'Applied',value:String(d.applied)},{label:'Errors',value:String(d.errors)}],
        issues: errs.length?[{tone:'warn',text:`${errs.length} statement(s) failed \u2014 usually orphan values that violate a foreign key. See the rows below.`}]:[],
        verdict: errs.length?'Some keys were added. Fix the flagged rows and re-run for the rest, then re-ingest the source in PDC.':'All keys written. Re-run Metadata Ingest on this source in PDC so it reads the new primary and foreign keys.'})
      + `<div class="keylist">${list}</div>`;
  }catch(e){ $('schemaKeysOut').innerHTML='<div class="msg">Failed: '+esc(String(e))+'</div>'; }
}
function applySchema(d){
  SCHEMA=d; SSEL=null; SPOS={}; SVIEW={z:1,x:0,y:0}; $('schemaMsg').textContent='';
  renderSchemaSummary(d);
  ['schemaStage','schemaFitBtn','schemaRelayoutBtn','schemaKeysOnlyWrap'].forEach(x=>$(x).style.display='');
  schemaRender();
  requestAnimationFrame(()=>schemaRelayout());
}

function renderSchemaSummary(d){
  const cols=d.tables.reduce((a,t)=>a+t.col_count,0);
  const pks=d.tables.reduce((a,t)=>a+t.pk_count,0);
  const fks=d.tables.reduce((a,t)=>a+t.fk_count,0);
  const unresolved=d.relationships.filter(r=>!r.resolved).length;
  const noKeys = d.table_count>0 && pks===0 && fks===0;
  const issues=[];
  if(noKeys){
    issues.push({tone:'bad',text:"No primary or foreign keys were found in the live catalog. The constraints may exist but be invisible to this connection's user — or the tables were created without them. Paste the CREATE TABLE script below to diagram the keys straight from the SQL, or connect with an owner/superuser and reload."});
  } else if(unresolved){
    issues.push({tone:'warn',text:`${unresolved} foreign key(s) reference a table outside this scan — those edges aren't drawn.`});
  }
  const c={title:'Schema',tone:noKeys?'bad':(unresolved?'warn':'ok'),
    rows:[{label:'Schema',value:d.schema_name||'\u2014'},
          {label:'Tables',value:String(d.table_count)},
          {label:'Columns',value:String(cols)},
          {label:'Keys',value:`${pks} PK \u00b7 ${fks} FK`},
          {label:'Relationships',value:String(d.rel_count)}],
    issues,
    verdict: noKeys ? 'Diagram drawn, but without keys there are no relationships to show.'
           : (d.table_count? 'Drag tables to arrange, scroll to zoom, click a table to see all columns with PK/FK.' : 'No tables found in this source.')};
  const host=$('schemaSummary'); host.style.display=''; host.innerHTML=renderCheck(c);
}

function schemaRender(){
  if(!SCHEMA) return;
  TIDX={}; CIDX={};
  SCHEMA.tables.forEach((t,ti)=>{ TIDX[t.name]=ti; CIDX[t.name]={}; t.columns.forEach((c,ci)=>CIDX[t.name][c.name]=ci); });
  const keysOnly=$('schemaKeysOnly').checked;
  let html='';
  SCHEMA.tables.forEach((t,ti)=>{
    const cols = keysOnly ? t.columns.filter(c=>c.pk||c.fk) : t.columns;
    const rows = cols.map(c=>{
      const ci=CIDX[t.name][c.name];
      const badge = c.pk?'<span class="badge-k pk">PK</span>':(c.fk?'<span class="badge-k fk">FK</span>':'<span class="badge-k sp"></span>');
      return `<div class="schema-col${(c.pk||c.fk)?' k':''}" id="sc_${ti}_${ci}">${badge}<span class="cn">${esc(c.name)}</span><span class="ct">${esc(c.type||'')}</span></div>`;
    }).join('');
    const p=SPOS[t.name]||{x:20+ti*20,y:20+ti*12};
    html += `<div class="schema-table" id="st_${ti}" style="left:${p.x}px;top:${p.y}px" onmousedown="schemaTableDown(event,${ti})">`
      + `<div class="th"><span class="tn">${esc(t.name)}</span><span class="kc">${t.pk_count}PK\u00b7${t.fk_count}FK\u00b7${t.col_count}c</span><span class="zi">\u2315</span></div>`
      + rows + `</div>`;
  });
  $('schemaTables').innerHTML=html;
  $('schemaEdges').innerHTML='<defs><marker id="sa" markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6" fill="none" stroke="#94a3b8" stroke-width="1.4"/></marker></defs>';
  schemaApplyView(); schemaDrawEdges();
}

function schemaApplyPositions(){
  SCHEMA.tables.forEach((t,ti)=>{ const el=$('st_'+ti); const p=SPOS[t.name]; if(el&&p){ el.style.left=p.x+'px'; el.style.top=p.y+'px'; } });
}

function schemaRelayout(){
  if(!SCHEMA) return;
  const stage=$('schemaStage'); const sw=stage.clientWidth||900; const gap=46;
  const K=Math.max(1, Math.min(SCHEMA.tables.length, Math.floor(sw/(SCARD_W+gap))||1));
  const colH=new Array(K).fill(0);
  SCHEMA.tables.forEach((t,ti)=>{
    const el=$('st_'+ti); const h=el?el.offsetHeight:120;
    let k=0; for(let i=1;i<K;i++) if(colH[i]<colH[k]) k=i;
    SPOS[t.name]={x:k*(SCARD_W+gap)+24, y:colH[k]+24};
    colH[k]+=h+gap;
  });
  schemaApplyPositions(); schemaDrawEdges(); schemaFit();
}

function schemaDrawEdges(){
  const svg=$('schemaEdges'); if(!svg||!SCHEMA) return;
  const defs=svg.querySelector('defs'); let body='';
  SCHEMA.relationships.forEach(r=>{
    if(!r.resolved) return;
    const fi=TIDX[r.from], ti=TIDX[r.to]; if(fi==null||ti==null) return;
    const fc=$('st_'+fi), tc=$('st_'+ti); const fp=SPOS[r.from], tp=SPOS[r.to]; if(!fc||!tc||!fp||!tp) return;
    const fw=fc.offsetWidth, tw=tc.offsetWidth;
    const frow=document.getElementById('sc_'+fi+'_'+CIDX[r.from][r.from_col]);
    const trow=(r.to_col!=null&&CIDX[r.to]&&CIDX[r.to][r.to_col]!=null)?document.getElementById('sc_'+ti+'_'+CIDX[r.to][r.to_col]):null;
    const fcy=fp.y+(frow?frow.offsetTop+frow.offsetHeight/2:fc.offsetHeight/2);
    const tcy=tp.y+(trow?trow.offsetTop+trow.offsetHeight/2:tc.offsetHeight/2);
    const fromLeft=(fp.x+fw/2)<=(tp.x+tw/2);
    const x1=fromLeft?fp.x+fw:fp.x, x2=fromLeft?tp.x:tp.x+tw;
    const dx=Math.max(36,Math.abs(x2-x1)*0.4);
    const c1=fromLeft?x1+dx:x1-dx, c2=fromLeft?x2-dx:x2+dx;
    const hot=SSEL&&(SSEL===r.from||SSEL===r.to)?' hot':'';
    const dim=SSEL&&!(SSEL===r.from||SSEL===r.to)?' dim':'';
    body+=`<path class="edge${hot}${dim}" marker-end="url(#sa)" d="M${x1},${fcy} C${c1},${fcy} ${c2},${tcy} ${x2},${tcy}"/>`;
  });
  svg.innerHTML=(defs?defs.outerHTML:'')+body;
}

function schemaApplyView(){
  $('schemaWorld').style.transform=`translate(${SVIEW.x}px,${SVIEW.y}px) scale(${SVIEW.z})`;
  $('schemaZoomLbl').textContent=Math.round(SVIEW.z*100)+'%';
}
function schemaZoomAt(f,mx,my){
  const nz=sclamp(SVIEW.z*f,0.2,2.5), k=nz/SVIEW.z;
  SVIEW.x=mx-(mx-SVIEW.x)*k; SVIEW.y=my-(my-SVIEW.y)*k; SVIEW.z=nz; schemaApplyView();
}
function schemaZoom(f){ const s=$('schemaStage'); schemaZoomAt(f,s.clientWidth/2,s.clientHeight/2); }
function schemaFit(){
  if(!SCHEMA||!SCHEMA.tables.length) return;
  const stage=$('schemaStage'); const sw=stage.clientWidth, sh=stage.clientHeight;
  let minx=1e9,miny=1e9,maxx=-1e9,maxy=-1e9;
  SCHEMA.tables.forEach((t,ti)=>{ const el=$('st_'+ti); const p=SPOS[t.name]; if(!p) return;
    minx=Math.min(minx,p.x); miny=Math.min(miny,p.y);
    maxx=Math.max(maxx,p.x+(el?el.offsetWidth:SCARD_W)); maxy=Math.max(maxy,p.y+(el?el.offsetHeight:120)); });
  const bw=Math.max(1,maxx-minx), bh=Math.max(1,maxy-miny);
  const z=sclamp(Math.min((sw-48)/bw,(sh-48)/bh,1.2),0.2,1.2);
  SVIEW.z=z; SVIEW.x=(sw-bw*z)/2-minx*z; SVIEW.y=(sh-bh*z)/2-miny*z; schemaApplyView();
}

function schemaTableDown(e,ti){
  if(e.button!==0) return; e.stopPropagation();
  const tname=SCHEMA.tables[ti].name;
  SDRAG={ti,tname,sx:e.clientX,sy:e.clientY,ox:(SPOS[tname]||{x:0}).x,oy:(SPOS[tname]||{y:0}).y,moved:false};
  if(SSEL!==tname){ SSEL=tname; schemaHighlight(); }
}
function schemaHighlight(){
  SCHEMA.tables.forEach((t,ti)=>{ const el=$('st_'+ti); if(!el) return;
    el.classList.toggle('sel',SSEL===t.name);
    el.classList.toggle('dim',!!SSEL&&SSEL!==t.name&&!schemaRelated(t.name)); });
  schemaDrawEdges();
}
function schemaRelated(name){
  if(!SSEL) return true;
  return SCHEMA.relationships.some(r=>r.resolved&&((r.from===SSEL&&r.to===name)||(r.to===SSEL&&r.from===name)));
}
function schemaOpenTable(ti){
  const t=SCHEMA.tables[ti];
  const rows=t.columns.map(c=>{
    const k=c.pk?'<span class="badge-k pk">PK</span>':(c.fk?'<span class="badge-k fk">FK</span>':'');
    const ref=(c.fk&&c.ref_table)?`${esc(c.ref_table)}.${esc(c.ref_col||'')}`:'';
    return `<tr><td>${k} ${esc(c.name)}</td><td>${esc(c.type||'')}</td><td>${c.notnull?'NOT NULL':''}</td><td>${ref}</td></tr>`;
  }).join('');
  const bg=document.createElement('div'); bg.className='schema-modal-bg'; bg.id='schemaModal';
  bg.onclick=e=>{ if(e.target===bg) bg.remove(); };
  bg.innerHTML=`<div class="schema-modal"><h3>${esc(t.name)} <span class="hint" style="font-weight:400">${t.col_count} columns \u00b7 ${t.pk_count} PK \u00b7 ${t.fk_count} FK</span></h3>`
    +`<table><thead><tr><th>Column</th><th>Type</th><th>Null</th><th>References</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  document.body.appendChild(bg);
}
// global drag / pan / zoom wiring (once)
document.addEventListener('mousemove',e=>{
  if(SDRAG){
    const dx=(e.clientX-SDRAG.sx)/SVIEW.z, dy=(e.clientY-SDRAG.sy)/SVIEW.z;
    if(Math.abs(e.clientX-SDRAG.sx)+Math.abs(e.clientY-SDRAG.sy)>3) SDRAG.moved=true;
    SPOS[SDRAG.tname]={x:SDRAG.ox+dx,y:SDRAG.oy+dy};
    const el=$('st_'+SDRAG.ti); if(el){ el.style.left=SPOS[SDRAG.tname].x+'px'; el.style.top=SPOS[SDRAG.tname].y+'px'; }
    schemaDrawEdges();
  } else if(SPAN){
    SVIEW.x=SPAN.ox+(e.clientX-SPAN.sx); SVIEW.y=SPAN.oy+(e.clientY-SPAN.sy); schemaApplyView();
  }
});
document.addEventListener('mouseup',e=>{
  if(SDRAG){ if(!SDRAG.moved) schemaOpenTable(SDRAG.ti); SDRAG=null; }
  SPAN=null;
});
document.addEventListener('keydown',e=>{ if(e.key==='Escape'){ const m=$('schemaModal'); if(m) m.remove(); else if(SSEL){ SSEL=null; schemaHighlight(); } }});
function schemaStageWire(){
  const stage=$('schemaStage'); if(!stage||stage._wired) return; stage._wired=true;
  stage.addEventListener('mousedown',e=>{ if(e.target.closest('.schema-table'))return; SPAN={sx:e.clientX,sy:e.clientY,ox:SVIEW.x,oy:SVIEW.y}; if(SSEL){SSEL=null;schemaHighlight();} });
  stage.addEventListener('wheel',e=>{ e.preventDefault(); const r=stage.getBoundingClientRect(); schemaZoomAt(e.deltaY<0?1.1:1/1.1,e.clientX-r.left,e.clientY-r.top); },{passive:false});
}
