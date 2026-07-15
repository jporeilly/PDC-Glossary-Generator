/* 12-init.js — extracted from templates/index.html. Plain scripts, loaded in
   numbered order; they share one global scope, so load order matters. */
/* ---------- init ---------- */
/* Session persistence — the review grid is authored in memory, so a browser
   reload or accidental navigation used to lose all unsaved review work. Autosave
   a snapshot to sessionStorage (this tab only) every few seconds and on unload,
   and restore it on boot. "Save glossary" remains the durable checkpoint — this
   is refresh/navigation insurance, not a replacement for saving. */
const GRID_SS_KEY='gg_grid_v1';
function persistGrid(){
  try{
    if(!ROWS.length){ sessionStorage.removeItem(GRID_SS_KEY); return; }
    sessionStorage.setItem(GRID_SS_KEY, JSON.stringify({rows:ROWS,
      gloss:(typeof CUR_GLOSS!=='undefined')?(CUR_GLOSS||null):null, t:Date.now()}));
  }catch(e){ /* storage disabled or quota hit — grid stays in-memory only */ }
}
function restoreGrid(){
  try{
    const raw=sessionStorage.getItem(GRID_SS_KEY); if(!raw) return;
    const d=JSON.parse(raw); if(!d||!Array.isArray(d.rows)||!d.rows.length) return;
    ROWS=d.rows; if(typeof CUR_GLOSS!=='undefined' && d.gloss) CUR_GLOSS=d.gloss;
    buildCategoryFilter(); clearFilters(); snapshotScan();
    if(typeof renderSummary==='function'&&typeof computeStats==='function') renderSummary(computeStats(ROWS));
    llmStatus();  // boot's own llmStatus may have raced this restore with ROWS still empty
    if($('msg')) $('msg').textContent=`Restored ${ROWS.length} terms from this browser session — unsaved work; Save glossary to keep it.`;
  }catch(e){ /* corrupt snapshot — start clean */ }
}
setInterval(persistGrid, 3000);
window.addEventListener('beforeunload', persistGrid);
window.addEventListener('beforeunload',e=>{ if(ROSTER_DIRTY){ e.preventDefault(); e.returnValue=''; return ''; } });
loadSettings(); llmStatus(); loadConnections(); loadDrivers(); loadGlossaryList(); restoreGrid();
// auto-resume: if the browser session had nothing to restore, reopen the last
// saved glossary (remembered in settings.json, which survives restarts)
(async function autoResume(){
  try{
    if(typeof ROWS!=='undefined' && ROWS.length) return;   // session snapshot won
    const s=await (await fetch('/api/settings')).json();
    if(!s || !s.last_glossary) return;
    const items=(await (await fetch('/api/glossaries')).json()).glossaries||[];
    if(!items.some(g=>g.id===s.last_glossary)) return;      // deleted since
    await loadGlossary(s.last_glossary, true);
  }catch(e){ /* auto-resume is best-effort — a clean start is fine */ }
})();
fetch('/api/version').then(r=>r.json()).then(d=>{ if(d&&d.version&&$('appver')) $('appver').textContent='v'+d.version; }).catch(()=>{});
function mdLite(s){
  return esc(s)
    .replace(/\*\*([^*\n]+)\*\*/g,'<b>$1</b>')
    .replace(/`([^`\n]+)`/g,'<code>$1</code>')
    .replace(/^### (.+)$/gm,'<b style="display:block;margin:8px 0 2px">$1</b>')
    .replace(/^[-*] /gm,'&bull; ')
    .replace(/\n/g,'<br>');
}
async function whatsNew(){
  const old=document.getElementById('wnPanel');
  if(old){ old.remove(); return; }  // second click on the pill closes it
  const el=document.createElement('div'); el.id='wnPanel';
  el.style.cssText='position:fixed;left:236px;bottom:16px;z-index:1000;width:min(560px,calc(100vw - 260px));max-height:70vh;overflow:auto;background:var(--card,#fff);color:var(--ink,#1c2733);border:1px solid var(--line,#ccc);border-radius:12px;box-shadow:0 12px 40px rgba(0,0,0,.28);padding:14px 16px;font-size:12.5px';
  el.innerHTML='<div class="msg">Loading release notes…</div>';
  document.body.appendChild(el);
  try{
    const d=await (await fetch('/api/whatsnew')).json();
    let h=`<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px"><b style="font-size:14px">What's new — running v${esc(d.version||'?')}</b><span style="flex:1"></span><button class="ghost sm" onclick="document.getElementById('wnPanel').remove()" title="Close">✕</button></div>`;
    if(!d.releases||!d.releases.length){
      h+='<div class="msg">Release notes unavailable in this build (docs/CHANGELOG.md isn’t shipped in e.g. the Docker image) — see CHANGELOG.md on GitHub.</div>';
    }else{
      if(d.releases[0].version!==d.version){
        h+=`<div class="msg" style="color:#B3261E;font-weight:600">⚠ The checkout's changelog leads with v${esc(d.releases[0].version)} but this process is running v${esc(d.version)} — the code was updated without a restart (or the pull didn't complete). Restart the app so they match.</div>`;
      }
      h+=d.releases.map(r=>`<div style="margin-top:10px;border-top:1px solid var(--line,#eee);padding-top:8px"><b>v${esc(r.version)}</b> <span class="hint">${esc(r.date||'')}</span><div style="margin-top:3px;line-height:1.55">${mdLite(r.body||'')}</div></div>`).join('');
    }
    el.innerHTML=h;
  }catch(e){ el.innerHTML='<div class="msg">Failed to load release notes: '+esc(e.message||e)+'</div>'; }
}
