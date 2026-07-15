/* 03-files.js — extracted from templates/index.html. Plain scripts, loaded in
   numbered order; they share one global scope, so load order matters. */
/* ---------- file browser ---------- */
let FILESDATA=null, FILESPFX='';
function filesConnCfg(){ const sel=$('filesConn'); const id=sel&&sel.value; const c=(typeof CONNS!=='undefined'?CONNS:[]).find(x=>x.id===id); return c; }
function filesPageInit(){
  const sel=$('filesConn'); if(!sel) return;
  const opts=(typeof CONNS!=='undefined'?CONNS:[]).filter(c=>c.type==='minio');
  const prev=sel.value;
  sel.innerHTML = opts.length
    ? opts.map(c=>`<option value="${esc(c.id)}">${esc(c.name||'MinIO')} \u2014 ${esc((c.config||{}).bucket||'')}</option>`).join('')
    : `<option value="">No MinIO/S3 connection \u2014 add one on Connections</option>`;
  if(prev && opts.some(c=>c.id===prev)) sel.value=prev;
}
function fmtSize(b){ if(b==null) return ''; const u=['B','KB','MB','GB','TB']; let i=0,n=b; while(n>=1024&&i<u.length-1){n/=1024;i++;} return (i?n.toFixed(n<10?1:0):n)+'\u00a0'+u[i]; }
function fmtDate(iso){ if(!iso) return ''; try{ const d=new Date(iso); if(isNaN(d)) return ''; return d.toLocaleDateString(undefined,{year:'numeric',month:'short',day:'numeric'})+', '+d.toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit'}); }catch(e){ return ''; } }
function fileIcon(ext){ const m={pdf:'\ud83d\udcd5',csv:'\ud83d\udcca',tsv:'\ud83d\udcca',xlsx:'\ud83d\udcc8',xls:'\ud83d\udcc8',parquet:'\ud83e\uddf1',json:'\ud83e\uddfe',jsonl:'\ud83e\uddfe',ndjson:'\ud83e\uddfe',xml:'\ud83e\uddfe',txt:'\ud83d\udcc4',md:'\ud83d\udcdd',log:'\ud83d\udcc4',sql:'\ud83d\uddc4\ufe0f',html:'\ud83c\udf10',htm:'\ud83c\udf10',png:'\ud83d\uddbc\ufe0f',jpg:'\ud83d\uddbc\ufe0f',jpeg:'\ud83d\uddbc\ufe0f',gif:'\ud83d\uddbc\ufe0f',svg:'\ud83d\uddbc\ufe0f',zip:'\ud83d\udddc\ufe0f',gz:'\ud83d\udddc\ufe0f'}; return m[ext]||'\ud83d\udcc4'; }
async function browseFiles(prefix){
  const c=filesConnCfg();
  if(!c){ $('filesMsg').textContent='Add a MinIO/S3 connection on the Connections page first.'; return; }
  $('filesMsg').textContent='Loading\u2026'; $('filesBrowseBtn').disabled=true;
  try{
    const d=await (await fetch('/api/list-objects',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({minio:c.config,prefix:prefix||''})})).json();
    if(d.error){ $('filesMsg').textContent=d.error; $('filesBrowseBtn').disabled=false; return; }
    FILESDATA=d; FILESPFX=d.prefix||''; $('filesMsg').textContent='';
    $('filesPanel').style.display=''; renderFiles(d);
  }catch(e){ $('filesMsg').textContent='Could not list objects: '+e; }
  $('filesBrowseBtn').disabled=false;
}
function gotoCrumb(i){ const parts=FILESPFX?FILESPFX.split('/'):[]; browseFiles(i<0?'':parts.slice(0,i+1).join('/')); }
function browseFolder(i){ const f=FILESDATA.folders[i]; if(f) browseFiles(f.prefix); }
function renderFiles(d){
  const bucket=d.bucket||'bucket';
  const parts=d.prefix?d.prefix.split('/'):[];
  let crumbs=`<a onclick="gotoCrumb(-1)">\ud83e\udea3 ${esc(bucket)}</a>`;
  parts.forEach((p,i)=>{ crumbs+=`<span class="sep">/</span>`+ (i===parts.length-1?`<span class="cur">${esc(p)}</span>`:`<a onclick="gotoCrumb(${i})">${esc(p)}</a>`); });
  $('filesCrumbs').innerHTML=crumbs;
  $('filesStat').textContent=`${d.folder_count} folder${d.folder_count!==1?'s':''} \u00b7 ${d.file_count} file${d.file_count!==1?'s':''} \u00b7 ${fmtSize(d.total_bytes)}`+(d.truncated?' \u00b7 truncated':'');
  let html=`<div class="fb-row head"><span></span><span>Name</span><span class="fb-type">Type</span><span class="fb-sz">Size</span><span class="fb-md">Modified</span></div>`;
  if(!d.folders.length && !d.files.length){ html+=`<div class="fb-empty">This folder is empty.</div>`; }
  d.folders.forEach((f,i)=>{ html+=`<div class="fb-row dir" onclick="browseFolder(${i})"><span class="fb-ico">\ud83d\udcc1</span><span class="fb-name"><span class="nm">${esc(f.name)}</span></span><span class="fb-type">folder</span><span class="fb-sz"></span><span class="fb-md"></span></div>`; });
  d.files.forEach((f,i)=>{ html+=`<div class="fb-row file"><span class="fb-ico">${fileIcon(f.ext)}</span><span class="fb-name"><span class="nm" onclick="openFile(${i})" title="${esc(f.name)}">${esc(f.name)}</span></span><span class="fb-type">${esc(f.ext||'\u2014')}</span><span class="fb-sz">${fmtSize(f.size)}</span><span class="fb-md">${esc(fmtDate(f.modified))}</span></div>`; });
  $('filesList').innerHTML=html;
}
async function objectBlobUrl(c, key){
  const r=await fetch('/api/object-bytes',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({minio:c.config,key})});
  if(!r.ok){ let m='Could not load file'; try{ m=(await r.json()).error||m; }catch(e){} throw new Error(m); }
  return URL.createObjectURL(await r.blob());
}
function closeFileModal(){ const m=$('fileModal'); if(m){ if(m._url) URL.revokeObjectURL(m._url); m.remove(); } }
async function openFile(i){
  const f=FILESDATA.files[i]; if(!f) return; const c=filesConnCfg(); if(!c) return;
  const bg=document.createElement('div'); bg.className='schema-modal-bg'; bg.id='fileModal';
  bg.onclick=e=>{ if(e.target===bg) closeFileModal(); };
  const wide=['pdf','docx'].includes((f.ext||'').toLowerCase())||['png','jpg','jpeg','gif','webp','bmp','svg'].includes((f.ext||'').toLowerCase());
  bg.innerHTML=`<div class="schema-modal${wide?' wide':''}"><h3>${fileIcon(f.ext)} ${esc(f.name)}</h3><div class="fb-loading">Loading\u2026</div></div>`;
  document.body.appendChild(bg);
  try{
    const d=await (await fetch('/api/object',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({minio:c.config,key:f.key})})).json();
    const box=bg.querySelector('.schema-modal');
    if(d.error){ box.querySelector('.fb-loading').innerHTML=esc(d.error); return; }
    let h=`<div class="fb-meta"><b>Size</b> ${fmtSize(d.size)} \u00b7 <b>Type</b> ${esc(d.content_type||f.ext||'\u2014')} \u00b7 <b>Modified</b> ${esc(fmtDate(d.modified))}</div>`;
    h+=`<div class="fb-meta" style="word-break:break-all"><b>Key</b> ${esc(d.key)}</div>`;
    const tags=(d.tags||[]).concat(Object.entries(d.metadata||{}).map(([k,v])=>({key:k,value:v})));
    if(tags.length){ h+=`<div class="fb-tags">`+tags.map(t=>`<span class="fb-tag">${esc(t.key)}: ${esc(t.value)}</span>`).join('')+`</div>`; }
    const kind=d.preview_kind||'none';
    // action buttons (download for everything; open-in-tab for pdf/image)
    h+=`<div class="fb-actions">`
      +`<button class="ghost sm" onclick="downloadObject('${esc(f.key)}','${esc(f.name)}')">Download</button>`
      +(['pdf','image'].includes(kind)?`<button class="ghost sm" onclick="openObjectTab('${esc(f.key)}')">Open in new tab</button>`:'')
      +`</div>`;
    box.innerHTML=`<h3>${fileIcon(f.ext)} ${esc(f.name)}</h3>`+h+`<div class="fb-loading" id="fbView">Rendering\u2026</div>`;
    const view=box.querySelector('#fbView');
    if(kind==='pdf'){
      try{ const u=await objectBlobUrl(c,f.key); bg._url=u;
        view.outerHTML=`<iframe class="fb-doc" src="${u}" title="${esc(f.name)}"></iframe>`; }
      catch(e){ view.outerHTML=`<div class="fb-meta" style="padding-bottom:16px;color:#C25E00">${esc(String(e.message||e))}</div>`; }
    } else if(kind==='image'){
      try{ const u=await objectBlobUrl(c,f.key); bg._url=u;
        view.outerHTML=`<img class="fb-img" src="${u}" alt="${esc(f.name)}">`; }
      catch(e){ view.outerHTML=`<div class="fb-meta" style="padding-bottom:16px;color:#C25E00">${esc(String(e.message||e))}</div>`; }
    } else if(kind==='docx'){
      if(d.html){ view.outerHTML=`<div class="fb-docx">${d.html}</div>`; }
      else { view.outerHTML=`<div class="fb-meta" style="padding-bottom:16px">Couldn\u2019t render this Word document${d.docx_error?': '+esc(d.docx_error):' (install <code>mammoth</code> for best results)'}. Use Download.</div>`; }
    } else if(kind==='text' && d.preview!=null){
      view.outerHTML=`<div class="fb-preview">${esc(d.preview)}</div>`+(d.preview_truncated?`<div class="fb-meta" style="margin-top:-6px">\u2026 preview truncated</div>`:'');
    } else {
      view.outerHTML=`<div class="fb-meta" style="padding-bottom:16px">No inline preview for this file type \u2014 use Download.</div>`;
    }
  }catch(e){ const m=bg.querySelector('.fb-loading'); if(m) m.innerHTML='Could not read object: '+esc(String(e)); }
}
async function downloadObject(key,name){
  try{ const c=filesConnCfg(); if(!c) return; const u=await objectBlobUrl(c,key);
    const a=document.createElement('a'); a.href=u; a.download=name||key.split('/').pop(); document.body.appendChild(a); a.click(); a.remove();
    setTimeout(()=>URL.revokeObjectURL(u),4000);
  }catch(e){ alert('Download failed: '+(e.message||e)); }
}
async function openObjectTab(key){
  try{ const c=filesConnCfg(); if(!c) return; const u=await objectBlobUrl(c,key); window.open(u,'_blank'); setTimeout(()=>URL.revokeObjectURL(u),60000); }
  catch(e){ alert('Could not open: '+(e.message||e)); }
}
document.addEventListener('keydown',e=>{ if(e.key==='Escape'){ closeFileModal(); }});
